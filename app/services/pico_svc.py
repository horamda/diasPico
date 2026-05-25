"""
Peak-day detection and aggregation queries against Railway PostgreSQL.
All heavy SQL lives here; routes stay thin.
"""

from __future__ import annotations
from datetime import date
import calendar as cal_mod

import psycopg2.extras

from app.database import pg_cursor
from app.services.articulos_svc import ensure_articulos_table
from app.services.rechazos_svc import ensure_table as ensure_rechazos_table
from app.services.transportes_svc import ensure_transportes_table
from app.services.ventas_svc import ensure_ventas_detalle_table

IS_MERCADERIA = "LOWER(TRIM(COALESCE(a.tipo_producto,''))) = 'mercaderia'"
V_REC_JOIN = """
LEFT JOIN LATERAL (
    SELECT tomar, sector
    FROM rechazos r
    WHERE LOWER(TRIM(COALESCE(v.motivo_rechazo,''))) = r.motivo_key
       OR LOWER(TRIM(COALESCE(v.motivo_rechazo,''))) LIKE r.motivo_key || ' %%'
    ORDER BY LENGTH(r.motivo_key) DESC
    LIMIT 1
) rz ON TRUE
"""
V_DOC_CODE = "LOWER(TRIM(COALESCE(v.documento, '')))"
V_DOC_DETAIL = "LOWER(TRIM(COALESCE(v.detalle_documento, '')))"
V_IS_REC = (
    "(COALESCE(rz.tomar, FALSE) AND ("
    "COALESCE(v.bultos_rechazados, 0) > 0 "
    "OR COALESCE(v.unidad_medida_rechazado, 0) > 0 "
    "OR COALESCE(v.unidad_paquete_rechazado, 0) > 0"
    "))"
)
V_NOT_REMITO = (
    f"{V_DOC_CODE} NOT LIKE 'remit%%' "
    f"AND {V_DOC_CODE} NOT LIKE 'comod%%' "
    f"AND {V_DOC_DETAIL} NOT LIKE 'remit%%' "
    f"AND {V_DOC_DETAIL} NOT LIKE 'comod%%'"
)
V_DOCUMENT_KEY = (
    "COALESCE("
    "NULLIF(TRIM(v.detalle_documento), ''), "
    "NULLIF(CONCAT_WS('-', NULLIF(TRIM(v.documento), ''), NULLIF(TRIM(v.serie), ''), NULLIF(TRIM(v.numero), '')), ''), "
    "v.id::text"
    ")"
)
V_CLIENT_KEY = (
    "NULLIF(TRIM(v.cliente), '')"
)
V_PEDIDO_KEY = f"v.fecha::text || '|' || {V_CLIENT_KEY}"
V_TRUCK_KEY = "COALESCE(NULLIF(TRIM(v.transporte), ''), NULLIF(TRIM(v.descripcion_transporte), ''), 'SIN_TRANSPORTE')"
V_TRUCK_DAY_KEY = f"v.fecha::text || '|' || {V_TRUCK_KEY}"
V_PALLETS_EXPR = "CASE WHEN COALESCE(a.bultos_por_pallet, 0) > 0 THEN COALESCE(v.bultos, 0) / a.bultos_por_pallet ELSE 0 END"
V_IS_RMCYO = (
    f"({V_DOC_CODE} LIKE 'rmcyo%%' "
    f"OR {V_DOC_DETAIL} LIKE '%%cuenta%%orden%%')"
)
V_RECHAZO_TOTAL_FLAG = (
    "LOWER(TRIM(COALESCE(v.rechazo_total, ''))) IN "
    "('si', 'sí', 'sÃ­', 's', 'yes', 'y', 'true', '1', 'x')"
)
V_IS_REC_TOTAL = f"({V_IS_REC} AND {V_RECHAZO_TOTAL_FLAG})"
V_IS_REC_PARCIAL = f"({V_IS_REC} AND NOT {V_RECHAZO_TOTAL_FLAG})"


def _suc_filter(sucursal: str, table_alias: str = '') -> str:
    prefix = f"{table_alias}." if table_alias else ""
    suc_expr = f"COALESCE(NULLIF(TRIM({prefix}sucursal), ''), '1')"
    return f"AND {suc_expr} = %(s)s" if sucursal != 'TODAS' else ""


def _rango_mes(y: int, m: int) -> tuple[date, date]:
    return date(y, m, 1), date(y, m, cal_mod.monthrange(y, m)[1])


def get_params(sucursal: str) -> dict:
    with pg_cursor() as cur:
        cur.execute("""
            SELECT umbral_pct, metrica FROM parametros_pico
            WHERE sucursal = %(s)s OR sucursal = 'TODAS'
            ORDER BY (sucursal = %(s)s) DESC LIMIT 1
        """, {'s': sucursal})
        row = cur.fetchone()
    return dict(row) if row else {'umbral_pct': 1.20, 'metrica': 'bultos'}


def save_params(sucursal: str, umbral_pct: float, metrica: str) -> None:
    with pg_cursor() as cur:
        cur.execute("""
            INSERT INTO parametros_pico (sucursal, umbral_pct, metrica, actualizado)
            VALUES (%(s)s, %(u)s, %(m)s, NOW())
            ON CONFLICT (sucursal) DO UPDATE SET
                umbral_pct=EXCLUDED.umbral_pct,
                metrica=EXCLUDED.metrica,
                actualizado=NOW()
        """, {'s': sucursal, 'u': umbral_pct, 'm': metrica})


SUCURSAL_LABELS: dict[str, str] = {
    '1': 'Casa Central',
    '2': 'Dolores',
}


def get_sucursales() -> list[dict]:
    ensure_ventas_detalle_table()
    with pg_cursor() as cur:
        cur.execute("""
            SELECT DISTINCT sucursal FROM ventas_detalle
            WHERE sucursal IS NOT NULL AND sucursal != ''
            ORDER BY sucursal
        """)
        db_vals = {r['sucursal'] for r in cur.fetchall()}
    result = [{'value': k, 'label': v} for k, v in SUCURSAL_LABELS.items()]
    for s in sorted(db_vals):
        if s not in SUCURSAL_LABELS:
            result.append({'value': s, 'label': s})
    return result


# ── Calendario mensual ────────────────────────────────────────

def get_calendario(sucursal: str, mes: str, umbral_override: float | None, metrica_override: str | None) -> dict:
    ensure_ventas_detalle_table()
    ensure_articulos_table()
    ensure_rechazos_table()

    anio, mes_num = int(mes.split('-')[0]), int(mes.split('-')[1])
    ini, fin = _rango_mes(anio, mes_num)

    params_db = get_params(sucursal)
    umbral = umbral_override if umbral_override is not None else float(params_db['umbral_pct'])
    metrica = metrica_override if metrica_override is not None else params_db['metrica']

    swv = _suc_filter(sucursal, 'v')
    p = {'ini': ini, 'fin': fin, 's': sucursal}

    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT v.fecha::text AS f,
                SUM(CASE WHEN {V_IS_REC} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS b_rec,
                SUM(CASE WHEN {V_IS_REC_PARCIAL} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS b_rec_parcial,
                SUM(CASE WHEN {V_IS_REC_TOTAL} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS b_rec_total,
                SUM(COALESCE(v.bultos, 0)) AS b_tot,
                SUM(CASE WHEN {V_IS_REC} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rec,
                SUM(CASE WHEN {V_IS_REC_PARCIAL} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rec_parcial,
                SUM(CASE WHEN {V_IS_REC_TOTAL} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rec_total,
                SUM(COALESCE(v.unidad_medida, 0)) AS hl_tot,
                SUM(CASE WHEN {V_IS_RMCYO} THEN COALESCE(v.bultos, 0) ELSE 0 END) AS rmcyo_bultos,
                SUM(CASE WHEN {V_IS_RMCYO} THEN COALESCE(v.unidad_medida, 0) ELSE 0 END) AS rmcyo_hl,
                SUM(CASE WHEN {V_IS_RMCYO} AND {V_IS_REC} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS rmcyo_b_rec,
                SUM(CASE WHEN {V_IS_RMCYO} AND {V_IS_REC} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS rmcyo_hl_rec,
                SUM(COALESCE(v.unidad_paquete, 0)) AS up_tot,
                SUM({V_PALLETS_EXPR}) AS pallets,
                SUM(COALESCE(v.importe_neto, 0)) AS importe,
                COUNT(DISTINCT CASE WHEN {V_IS_REC} THEN {V_PEDIDO_KEY} END) AS p_rec,
                COUNT(DISTINCT {V_PEDIDO_KEY}) AS p_tot,
                COUNT(DISTINCT CASE WHEN {V_IS_RMCYO} THEN {V_PEDIDO_KEY} END) AS rmcyo_pedidos,
                COUNT(DISTINCT CASE WHEN {V_IS_RMCYO} AND {V_IS_REC} THEN {V_PEDIDO_KEY} END) AS rmcyo_p_rec,
                COUNT(DISTINCT {V_CLIENT_KEY}) AS clientes_unicos,
                COUNT(DISTINCT {V_TRUCK_KEY}) AS camiones_salidos
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            {V_REC_JOIN}
            WHERE v.fecha BETWEEN %(ini)s AND %(fin)s {swv}
              AND {IS_MERCADERIA}
              AND {V_NOT_REMITO}
            GROUP BY v.fecha
        """, p)
        det_map = {r['f']: dict(r) for r in cur.fetchall()}

        cur.execute(f"""
            SELECT
                SUM(CASE WHEN {V_IS_REC} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS b_rec,
                SUM(CASE WHEN {V_IS_REC_PARCIAL} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS b_rec_parcial,
                SUM(CASE WHEN {V_IS_REC_TOTAL} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS b_rec_total,
                SUM(COALESCE(v.bultos, 0)) AS b_tot,
                SUM(CASE WHEN {V_IS_REC} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rec,
                SUM(CASE WHEN {V_IS_REC_PARCIAL} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rec_parcial,
                SUM(CASE WHEN {V_IS_REC_TOTAL} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rec_total,
                SUM(COALESCE(v.unidad_medida, 0)) AS hl_tot,
                SUM(CASE WHEN {V_IS_RMCYO} THEN COALESCE(v.bultos, 0) ELSE 0 END) AS rmcyo_bultos,
                SUM(CASE WHEN {V_IS_RMCYO} THEN COALESCE(v.unidad_medida, 0) ELSE 0 END) AS rmcyo_hl,
                SUM(CASE WHEN {V_IS_RMCYO} AND {V_IS_REC} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS rmcyo_b_rec,
                SUM(CASE WHEN {V_IS_RMCYO} AND {V_IS_REC} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS rmcyo_hl_rec,
                SUM(COALESCE(v.unidad_paquete, 0)) AS up_tot,
                SUM({V_PALLETS_EXPR}) AS pallets,
                SUM(COALESCE(v.importe_neto, 0)) AS importe,
                COUNT(DISTINCT CASE WHEN {V_IS_REC} THEN {V_PEDIDO_KEY} END) AS p_rec,
                COUNT(DISTINCT {V_PEDIDO_KEY}) AS p_tot,
                COUNT(DISTINCT CASE WHEN {V_IS_RMCYO} THEN {V_PEDIDO_KEY} END) AS rmcyo_pedidos,
                COUNT(DISTINCT CASE WHEN {V_IS_RMCYO} AND {V_IS_REC} THEN {V_PEDIDO_KEY} END) AS rmcyo_p_rec,
                COUNT(DISTINCT {V_CLIENT_KEY}) AS clientes_unicos,
                COUNT(DISTINCT v.fecha) AS dias,
                COUNT(DISTINCT {V_TRUCK_DAY_KEY}) AS camiones
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            {V_REC_JOIN}
            WHERE v.fecha BETWEEN %(ini)s AND %(fin)s {swv}
              AND {IS_MERCADERIA}
              AND {V_NOT_REMITO}
        """, p)
        det_mes = dict(cur.fetchone() or {})

        cur.execute("""
            SELECT fecha::text, descripcion, LOWER(TRIM(COALESCE(tipo, ''))) AS tipo
            FROM feriados
            WHERE fecha BETWEEN %s AND %s
        """, (ini, fin))
        feriados_nac = {}
        feriados_loc = {}
        for r in cur.fetchall():
            if r['tipo'] == 'local':
                feriados_loc[r['fecha']] = r['descripcion']
            else:
                feriados_nac[r['fecha']] = {'desc': r['descripcion'], 'tipo': r['tipo']}

        try:
            if sucursal == 'TODAS':
                cur.execute("""
                    SELECT fecha::text, descripcion FROM eventos_especiales
                    WHERE fecha BETWEEN %(ini)s AND %(fin)s
                """, p)
            else:
                cur.execute("""
                    SELECT fecha::text, descripcion FROM eventos_especiales
                    WHERE fecha BETWEEN %(ini)s AND %(fin)s
                      AND (sucursal = %(s)s OR sucursal = 'TODAS')
                """, p)
            eventos_manuales = {r['fecha']: r['descripcion'] for r in cur.fetchall()}
        except Exception:
            eventos_manuales = {}

        eventos = {**feriados_loc, **eventos_manuales}

        clientes_mes = int(det_mes.get('clientes_unicos') or 0)

    dias_raw = []
    metric_vals = []
    for d in range(1, cal_mod.monthrange(anio, mes_num)[1] + 1):
        fk = f"{anio}-{mes_num:02d}-{d:02d}"
        dt = det_map.get(fk, {})
        if not dt:
            continue

        bultos = float(dt.get('b_tot') or 0)
        pallets = float(dt.get('pallets') or 0)
        up = float(dt.get('up_tot') or 0)
        pedidos = int(dt.get('p_tot') or 0)
        hl = float(dt.get('hl_tot') or 0)
        clientes = int(dt.get('clientes_unicos') or 0)
        b_rec = float(dt.get('b_rec') or 0)
        b_rec_parcial = float(dt.get('b_rec_parcial') or 0)
        b_rec_total = float(dt.get('b_rec_total') or 0)
        b_tot = float(dt.get('b_tot') or 0)
        hl_rec = float(dt.get('hl_rec') or 0)
        hl_rec_parcial = float(dt.get('hl_rec_parcial') or 0)
        hl_rec_total = float(dt.get('hl_rec_total') or 0)
        hl_tot = float(dt.get('hl_tot') or 0)
        rmcyo_bultos = float(dt.get('rmcyo_bultos') or 0)
        rmcyo_hl = float(dt.get('rmcyo_hl') or 0)
        rmcyo_b_rec = float(dt.get('rmcyo_b_rec') or 0)
        rmcyo_hl_rec = float(dt.get('rmcyo_hl_rec') or 0)
        rmcyo_pedidos = int(dt.get('rmcyo_pedidos') or 0)
        rmcyo_p_rec = int(dt.get('rmcyo_p_rec') or 0)
        p_rec = int(dt.get('p_rec') or 0)
        p_tot = int(dt.get('p_tot') or 0)
        mv = {
            'bultos': bultos,
            'pallets': pallets,
            'up': up,
            'pedidos': pedidos,
            'hectolitros': hl,
            'clientes': clientes,
        }.get(metrica, bultos)

        if mv > 0:
            metric_vals.append(float(mv))

        dias_raw.append({
            'fecha': fk,
            'pedidos': pedidos,
            'bultos': round(bultos, 1),
            'pallets': round(pallets, 2),
            'up': round(up, 1),
            'hectolitros': round(hl, 1),
            'importe': round(float(dt.get('importe') or 0), 2),
            'camiones_salidos': int(dt.get('camiones_salidos') or 0),
            'clientes_unicos': clientes,
            'rechazo_bultos': round(b_rec, 1),
            'rechazo_bultos_parcial': round(b_rec_parcial, 1),
            'rechazo_bultos_total': round(b_rec_total, 1),
            'rechazo_hl': round(hl_rec, 1),
            'rechazo_hl_parcial': round(hl_rec_parcial, 1),
            'rechazo_hl_total': round(hl_rec_total, 1),
            'rechazo_pedidos': p_rec,
            'rmcyo_bultos': round(rmcyo_bultos, 1),
            'rmcyo_hl': round(rmcyo_hl, 1),
            'rmcyo_rechazo_bultos': round(rmcyo_b_rec, 1),
            'rmcyo_rechazo_hl': round(rmcyo_hl_rec, 1),
            'rmcyo_pedidos': rmcyo_pedidos,
            'rmcyo_rechazo_pedidos': rmcyo_p_rec,
            'pct_rechazo_bultos': round(b_rec / b_tot * 100, 1) if b_tot else 0,
            'pct_rechazo_hl': round(hl_rec / hl_tot * 100, 1) if hl_tot else 0,
            'pct_rechazo_pedidos': round(p_rec / p_tot * 100, 1) if p_tot else 0,
            'metrica_val': round(mv, 1),
            'es_feriado': fk in feriados_nac,
            'feriado_desc': feriados_nac[fk]['desc'] if fk in feriados_nac else '',
            'feriado_tipo': feriados_nac[fk]['tipo'] if fk in feriados_nac else '',
            'es_evento': fk in eventos,
            'evento_desc': eventos.get(fk, ''),
        })

    avg_mes = sum(metric_vals) / len(metric_vals) if metric_vals else 0
    umbral_val = avg_mes * umbral

    dias = []
    for row in dias_raw:
        row['es_pico'] = row['metrica_val'] > 0 and row['metrica_val'] >= umbral_val
        dias.append(row)

    sum_b_tot = float(det_mes.get('b_tot') or 0)
    sum_b_rec = float(det_mes.get('b_rec') or 0)
    sum_b_rec_parcial = float(det_mes.get('b_rec_parcial') or 0)
    sum_b_rec_total = float(det_mes.get('b_rec_total') or 0)
    sum_hl_tot = float(det_mes.get('hl_tot') or 0)
    sum_hl_rec = float(det_mes.get('hl_rec') or 0)
    sum_hl_rec_parcial = float(det_mes.get('hl_rec_parcial') or 0)
    sum_hl_rec_total = float(det_mes.get('hl_rec_total') or 0)
    sum_p_tot = int(det_mes.get('p_tot') or 0)
    sum_p_rec = int(det_mes.get('p_rec') or 0)
    sum_rmcyo_bultos = float(det_mes.get('rmcyo_bultos') or 0)
    sum_rmcyo_hl = float(det_mes.get('rmcyo_hl') or 0)
    sum_rmcyo_b_rec = float(det_mes.get('rmcyo_b_rec') or 0)
    sum_rmcyo_hl_rec = float(det_mes.get('rmcyo_hl_rec') or 0)
    sum_rmcyo_pedidos = int(det_mes.get('rmcyo_pedidos') or 0)
    sum_rmcyo_p_rec = int(det_mes.get('rmcyo_p_rec') or 0)
    sum_up = float(det_mes.get('up_tot') or 0)
    sum_pallets = float(det_mes.get('pallets') or 0)
    sum_importe = float(det_mes.get('importe') or 0)
    sum_camiones = int(det_mes.get('camiones') or 0)

    kpis = {
        'dias': int(det_mes.get('dias') or len(det_map)),
        'bultos': round(sum_b_tot, 1),
        'hectolitros': round(sum_hl_tot, 1),
        'pallets': round(sum_pallets, 2),
        'up': round(sum_up, 1),
        'pedidos': sum_p_tot,
        'clientes': clientes_mes,
        'importe': round(sum_importe, 2),
        'camiones': sum_camiones,
        'rechazo_bultos': round(sum_b_rec, 1),
        'rechazo_bultos_parcial': round(sum_b_rec_parcial, 1),
        'rechazo_bultos_total': round(sum_b_rec_total, 1),
        'rechazo_hl': round(sum_hl_rec, 1),
        'rechazo_hl_parcial': round(sum_hl_rec_parcial, 1),
        'rechazo_hl_total': round(sum_hl_rec_total, 1),
        'rechazo_pedidos': sum_p_rec,
        'rmcyo_bultos': round(sum_rmcyo_bultos, 1),
        'rmcyo_hl': round(sum_rmcyo_hl, 1),
        'rmcyo_rechazo_bultos': round(sum_rmcyo_b_rec, 1),
        'rmcyo_rechazo_hl': round(sum_rmcyo_hl_rec, 1),
        'rmcyo_pedidos': sum_rmcyo_pedidos,
        'rmcyo_rechazo_pedidos': sum_rmcyo_p_rec,
        'rmcyo_pct_rechazo_bultos': round(sum_rmcyo_b_rec / sum_rmcyo_bultos * 100, 1) if sum_rmcyo_bultos else 0,
        'rmcyo_pct_rechazo_hl': round(sum_rmcyo_hl_rec / sum_rmcyo_hl * 100, 1) if sum_rmcyo_hl else 0,
        'rmcyo_pct_rechazo_pedidos': round(sum_rmcyo_p_rec / sum_rmcyo_pedidos * 100, 1) if sum_rmcyo_pedidos else 0,
        'pct_rechazo_bultos': round(sum_b_rec / sum_b_tot * 100, 1) if sum_b_tot else 0,
        'pct_rechazo_hl': round(sum_hl_rec / sum_hl_tot * 100, 1) if sum_hl_tot else 0,
        'pct_rechazo_pedidos': round(sum_p_rec / sum_p_tot * 100, 1) if sum_p_tot else 0,
    }
    from app.services import kpi_objetivos_svc
    kpis['objetivos'] = kpi_objetivos_svc.evaluar(kpis, sucursal, fin)

    return {
        'mes': mes,
        'sucursal': sucursal,
        'metrica': metrica,
        'umbral_pct': umbral,
        'avg_mes': round(avg_mes, 1),
        'avg_hist': round(avg_mes, 1),
        'umbral_val': round(umbral_val, 1),
        'dias': dias,
        'kpis': kpis,
        'picos_count': sum(1 for d in dias if d['es_pico']),
    }


def get_kpis(sucursal: str, mes: str) -> dict:
    ensure_ventas_detalle_table()

    anio, mes_num = int(mes.split('-')[0]), int(mes.split('-')[1])
    ini, fin = _rango_mes(anio, mes_num)
    swv = _suc_filter(sucursal, 'v')
    p   = {'ini': ini, 'fin': fin, 's': sucursal}

    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT
                SUM(CASE WHEN {V_IS_REC} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS b_rec,
                SUM(CASE WHEN {V_IS_REC_PARCIAL} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS b_rec_parcial,
                SUM(CASE WHEN {V_IS_REC_TOTAL} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS b_rec_total,
                SUM(COALESCE(v.bultos, 0)) AS b_tot,
                SUM(CASE WHEN {V_IS_REC} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rec,
                SUM(CASE WHEN {V_IS_REC_PARCIAL} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rec_parcial,
                SUM(CASE WHEN {V_IS_REC_TOTAL} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rec_total,
                SUM(COALESCE(v.unidad_medida, 0)) AS hl_tot,
                SUM(CASE WHEN {V_IS_RMCYO} THEN COALESCE(v.bultos, 0) ELSE 0 END) AS rmcyo_bultos,
                SUM(CASE WHEN {V_IS_RMCYO} THEN COALESCE(v.unidad_medida, 0) ELSE 0 END) AS rmcyo_hl,
                SUM(CASE WHEN {V_IS_RMCYO} AND {V_IS_REC} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS rmcyo_b_rec,
                SUM(CASE WHEN {V_IS_RMCYO} AND {V_IS_REC} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS rmcyo_hl_rec,
                SUM(COALESCE(v.unidad_paquete, 0)) AS up_tot,
                SUM({V_PALLETS_EXPR}) AS pallets,
                SUM(COALESCE(v.importe_neto, 0)) AS importe,
                COUNT(DISTINCT CASE WHEN {V_IS_REC} THEN {V_PEDIDO_KEY} END) AS p_rec,
                COUNT(DISTINCT {V_PEDIDO_KEY}) AS p_tot,
                COUNT(DISTINCT CASE WHEN {V_IS_RMCYO} THEN {V_PEDIDO_KEY} END) AS rmcyo_pedidos,
                COUNT(DISTINCT CASE WHEN {V_IS_RMCYO} AND {V_IS_REC} THEN {V_PEDIDO_KEY} END) AS rmcyo_p_rec,
                COUNT(DISTINCT {V_CLIENT_KEY}) AS clientes_unicos,
                COUNT(DISTINCT v.fecha) AS dias,
                COUNT(DISTINCT {V_TRUCK_DAY_KEY}) AS camiones
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            {V_REC_JOIN}
            WHERE v.fecha BETWEEN %(ini)s AND %(fin)s {swv}
              AND {IS_MERCADERIA}
              AND {V_NOT_REMITO}
        """, p)
        d = dict(cur.fetchone() or {})

    b_rec = float(d.get('b_rec') or 0)
    b_rec_parcial = float(d.get('b_rec_parcial') or 0)
    b_rec_total = float(d.get('b_rec_total') or 0)
    b_tot = float(d.get('b_tot') or 0)
    hl_rec = float(d.get('hl_rec') or 0)
    hl_rec_parcial = float(d.get('hl_rec_parcial') or 0)
    hl_rec_total = float(d.get('hl_rec_total') or 0)
    hl_tot = float(d.get('hl_tot') or 0)
    up_tot = float(d.get('up_tot') or 0)
    p_rec = int(d.get('p_rec') or 0)
    p_tot = int(d.get('p_tot') or 0)
    rmcyo_bultos = float(d.get('rmcyo_bultos') or 0)
    rmcyo_hl = float(d.get('rmcyo_hl') or 0)
    rmcyo_b_rec = float(d.get('rmcyo_b_rec') or 0)
    rmcyo_hl_rec = float(d.get('rmcyo_hl_rec') or 0)
    rmcyo_pedidos = int(d.get('rmcyo_pedidos') or 0)
    rmcyo_p_rec = int(d.get('rmcyo_p_rec') or 0)
    clientes_unicos = int(d.get('clientes_unicos') or 0)
    kpis = {
        'dias':        int(d.get('dias') or 0),
        'pedidos':     p_tot,
        'clientes':    clientes_unicos,
        'bultos':      round(b_tot, 1),
        'pallets':     round(float(d.get('pallets') or 0), 2),
        'up':          round(up_tot, 1),
        'importe':     round(float(d.get('importe') or 0), 2),
        'camiones':    int(d.get('camiones') or 0),
        'hectolitros': round(hl_tot, 1),
        'rechazo_bultos': round(b_rec, 1),
        'rechazo_bultos_parcial': round(b_rec_parcial, 1),
        'rechazo_bultos_total': round(b_rec_total, 1),
        'rechazo_hl': round(hl_rec, 1),
        'rechazo_hl_parcial': round(hl_rec_parcial, 1),
        'rechazo_hl_total': round(hl_rec_total, 1),
        'rechazo_pedidos': p_rec,
        'rmcyo_bultos': round(rmcyo_bultos, 1),
        'rmcyo_hl': round(rmcyo_hl, 1),
        'rmcyo_rechazo_bultos': round(rmcyo_b_rec, 1),
        'rmcyo_rechazo_hl': round(rmcyo_hl_rec, 1),
        'rmcyo_pedidos': rmcyo_pedidos,
        'rmcyo_rechazo_pedidos': rmcyo_p_rec,
        'rmcyo_pct_rechazo_bultos': round(rmcyo_b_rec / rmcyo_bultos * 100, 1) if rmcyo_bultos else 0,
        'rmcyo_pct_rechazo_hl': round(rmcyo_hl_rec / rmcyo_hl * 100, 1) if rmcyo_hl else 0,
        'rmcyo_pct_rechazo_pedidos': round(rmcyo_p_rec / rmcyo_pedidos * 100, 1) if rmcyo_pedidos else 0,
        'pct_rechazo_bultos': round(b_rec / b_tot * 100, 1) if b_tot else 0,
        'pct_rechazo_hl': round(hl_rec / hl_tot * 100, 1) if hl_tot else 0,
        'pct_rechazo_pedidos': round(p_rec / p_tot * 100, 1) if p_tot else 0,
    }
    from app.services import kpi_objetivos_svc
    kpis['objetivos'] = kpi_objetivos_svc.evaluar(kpis, sucursal, fin)
    return kpis


# ── Histórico mensual ─────────────────────────────────────────

def get_historico(sucursal: str, n_meses: int) -> dict:
    ensure_ventas_detalle_table()

    hoy = date.today()
    fin = date(hoy.year, hoy.month, cal_mod.monthrange(hoy.year, hoy.month)[1])
    m, y = hoy.month - n_meses + 1, hoy.year
    while m <= 0:
        m += 12; y -= 1
    ini = date(y, m, 1)

    swv = _suc_filter(sucursal, 'v')
    p   = {'ini': ini, 'fin': fin, 's': sucursal}

    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT TO_CHAR(v.fecha,'YYYY-MM') AS mes,
                SUM(CASE WHEN {V_IS_REC} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS b_rec,
                SUM(CASE WHEN {V_IS_REC_PARCIAL} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS b_rec_parcial,
                SUM(CASE WHEN {V_IS_REC_TOTAL} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS b_rec_total,
                SUM(COALESCE(v.bultos, 0)) AS b_tot,
                SUM(CASE WHEN {V_IS_REC} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rec,
                SUM(CASE WHEN {V_IS_REC_PARCIAL} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rec_parcial,
                SUM(CASE WHEN {V_IS_REC_TOTAL} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rec_total,
                SUM(COALESCE(v.unidad_medida, 0)) AS hl_tot,
                SUM(CASE WHEN {V_IS_RMCYO} THEN COALESCE(v.bultos, 0) ELSE 0 END) AS rmcyo_bultos,
                SUM(CASE WHEN {V_IS_RMCYO} THEN COALESCE(v.unidad_medida, 0) ELSE 0 END) AS rmcyo_hl,
                SUM(CASE WHEN {V_IS_RMCYO} AND {V_IS_REC} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS rmcyo_b_rec,
                SUM(CASE WHEN {V_IS_RMCYO} AND {V_IS_REC} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS rmcyo_hl_rec,
                SUM(COALESCE(v.unidad_paquete, 0)) AS up_tot,
                SUM({V_PALLETS_EXPR}) AS pallets,
                SUM(COALESCE(v.importe_neto, 0)) AS importe,
                COUNT(DISTINCT CASE WHEN {V_IS_REC} THEN {V_PEDIDO_KEY} END) AS p_rec,
                COUNT(DISTINCT {V_PEDIDO_KEY}) AS p_tot,
                COUNT(DISTINCT CASE WHEN {V_IS_RMCYO} THEN {V_PEDIDO_KEY} END) AS rmcyo_pedidos,
                COUNT(DISTINCT CASE WHEN {V_IS_RMCYO} AND {V_IS_REC} THEN {V_PEDIDO_KEY} END) AS rmcyo_p_rec,
                COUNT(DISTINCT {V_CLIENT_KEY}) AS clientes_unicos,
                COUNT(DISTINCT v.fecha) AS dias,
                COUNT(DISTINCT {V_TRUCK_DAY_KEY}) AS camiones
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            {V_REC_JOIN}
            WHERE v.fecha BETWEEN %(ini)s AND %(fin)s {swv}
              AND {IS_MERCADERIA}
              AND {V_NOT_REMITO}
            GROUP BY 1
        """, p)
        dm = {r['mes']: dict(r) for r in cur.fetchall()}

    result = []
    for mk in sorted(dm):
        d  = dm.get(mk, {})
        br = float(d.get('b_rec') or 0)
        brp = float(d.get('b_rec_parcial') or 0)
        brt = float(d.get('b_rec_total') or 0)
        bt = float(d.get('b_tot') or 0)
        hr = float(d.get('hl_rec') or 0)
        hrp = float(d.get('hl_rec_parcial') or 0)
        hrt = float(d.get('hl_rec_total') or 0)
        ht = float(d.get('hl_tot') or 0)
        up = float(d.get('up_tot') or 0)
        pr = int(d.get('p_rec') or 0)
        pt = int(d.get('p_tot') or 0)
        rb = float(d.get('rmcyo_bultos') or 0)
        rh = float(d.get('rmcyo_hl') or 0)
        rbr = float(d.get('rmcyo_b_rec') or 0)
        rhr = float(d.get('rmcyo_hl_rec') or 0)
        rp = int(d.get('rmcyo_pedidos') or 0)
        rpr = int(d.get('rmcyo_p_rec') or 0)
        result.append({
            'mes':         mk,
            'pedidos':     pt,
            'clientes':    int(d.get('clientes_unicos') or 0),
            'bultos':      round(bt, 1),
            'pallets':     round(float(d.get('pallets') or 0), 2),
            'up':          round(up, 1),
            'hectolitros': round(ht, 1),
            'importe':     round(float(d.get('importe') or 0), 2),
            'camiones':    int(d.get('camiones') or 0),
            'dias':        int(d.get('dias') or 0),
            'rechazo_bultos': round(br, 1),
            'rechazo_bultos_parcial': round(brp, 1),
            'rechazo_bultos_total': round(brt, 1),
            'rechazo_hl': round(hr, 1),
            'rechazo_hl_parcial': round(hrp, 1),
            'rechazo_hl_total': round(hrt, 1),
            'rechazo_pedidos': pr,
            'rmcyo_bultos': round(rb, 1),
            'rmcyo_hl': round(rh, 1),
            'rmcyo_rechazo_bultos': round(rbr, 1),
            'rmcyo_rechazo_hl': round(rhr, 1),
            'rmcyo_pedidos': rp,
            'rmcyo_rechazo_pedidos': rpr,
            'rmcyo_pct_rechazo_bultos': round(rbr / rb * 100, 1) if rb else 0,
            'rmcyo_pct_rechazo_hl': round(rhr / rh * 100, 1) if rh else 0,
            'rmcyo_pct_rechazo_pedidos': round(rpr / rp * 100, 1) if rp else 0,
            'pct_rechazo_bultos': round(br / bt * 100, 1) if bt else 0,
            'pct_rechazo_hl': round(hr / ht * 100, 1) if ht else 0,
            'pct_rechazo_pedidos': round(pr / pt * 100, 1) if pt else 0,
        })
    return {'meses': result, 'sucursal': sucursal}


def get_analisis_hl(sucursal: str, n_meses: int) -> dict:
    ensure_ventas_detalle_table()

    hoy = date.today()
    fin = date(hoy.year, hoy.month, cal_mod.monthrange(hoy.year, hoy.month)[1])
    m, y = hoy.month - n_meses + 1, hoy.year
    while m <= 0:
        m += 12
        y -= 1
    ini = date(y, m, 1)

    swv = _suc_filter(sucursal, 'v')
    p = {'ini': ini, 'fin': fin, 's': sucursal}
    rec_join = V_REC_JOIN
    is_rec = V_IS_REC
    not_remito = V_NOT_REMITO
    pedido_key = V_PEDIDO_KEY

    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT TO_CHAR(v.fecha,'YYYY-MM') AS mes,
                SUM(COALESCE(v.bultos, 0)) AS bultos_total,
                SUM(CASE WHEN {is_rec} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS bultos_rechazo,
                SUM(CASE WHEN {V_IS_REC_PARCIAL} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS bultos_rechazo_parcial,
                SUM(CASE WHEN {V_IS_REC_TOTAL} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS bultos_rechazo_total,
                SUM(COALESCE(v.unidad_medida, 0)) AS hl_total,
                SUM(CASE WHEN {is_rec} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rechazo,
                SUM(CASE WHEN {V_IS_REC_PARCIAL} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rechazo_parcial,
                SUM(CASE WHEN {V_IS_REC_TOTAL} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rechazo_total,
                SUM(CASE WHEN {V_IS_RMCYO} THEN COALESCE(v.bultos, 0) ELSE 0 END) AS rmcyo_bultos,
                SUM(CASE WHEN {V_IS_RMCYO} THEN COALESCE(v.unidad_medida, 0) ELSE 0 END) AS rmcyo_hl,
                SUM(CASE WHEN {V_IS_RMCYO} AND {is_rec} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS rmcyo_b_rec,
                SUM(CASE WHEN {V_IS_RMCYO} AND {is_rec} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS rmcyo_hl_rec,
                COUNT(DISTINCT {pedido_key}) AS pedidos_total,
                COUNT(DISTINCT CASE WHEN {is_rec} THEN {pedido_key} END) AS pedidos_rechazo,
                COUNT(DISTINCT CASE WHEN {V_IS_RMCYO} THEN {pedido_key} END) AS rmcyo_pedidos,
                COUNT(DISTINCT CASE WHEN {V_IS_RMCYO} AND {is_rec} THEN {pedido_key} END) AS rmcyo_p_rec,
                COUNT(DISTINCT v.fecha) AS dias,
                COUNT(DISTINCT v.fecha::text || '|' || COALESCE(NULLIF(TRIM(v.transporte), ''), NULLIF(TRIM(v.descripcion_transporte), ''), {pedido_key})) AS salidas
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            {rec_join}
            WHERE v.fecha BETWEEN %(ini)s AND %(fin)s {swv}
              AND {IS_MERCADERIA}
              AND {not_remito}
            GROUP BY 1
            ORDER BY 1
        """, p)
        meses_raw = [dict(r) for r in cur.fetchall()]

        cur.execute(f"""
            SELECT COALESCE(rz.sector, 'Sin sector') AS sector,
                COALESCE(v.motivo_rechazo, 'Sin motivo') AS motivo,
                SUM(COALESCE(v.bultos_rechazados, 0)) AS bultos_rechazo,
                SUM(CASE WHEN {V_RECHAZO_TOTAL_FLAG} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS bultos_rechazo_total,
                SUM(CASE WHEN NOT {V_RECHAZO_TOTAL_FLAG} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS bultos_rechazo_parcial,
                SUM(COALESCE(v.unidad_medida_rechazado, 0)) AS hl_rechazo,
                SUM(CASE WHEN {V_RECHAZO_TOTAL_FLAG} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rechazo_total,
                SUM(CASE WHEN NOT {V_RECHAZO_TOTAL_FLAG} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rechazo_parcial,
                COUNT(DISTINCT {pedido_key}) AS pedidos_rechazo,
                COUNT(*) AS ocurrencias,
                COUNT(DISTINCT TO_CHAR(v.fecha,'YYYY-MM')) AS meses_con_rechazo
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            {rec_join}
            WHERE v.fecha BETWEEN %(ini)s AND %(fin)s {swv}
              AND {is_rec}
              AND {IS_MERCADERIA}
              AND {not_remito}
            GROUP BY COALESCE(rz.sector, 'Sin sector'), COALESCE(v.motivo_rechazo, 'Sin motivo')
            ORDER BY bultos_rechazo DESC, hl_rechazo DESC
        """, p)
        motivos_raw = [dict(r) for r in cur.fetchall()]

    meses = []
    total_hl = 0.0
    total_hl_rechazo = 0.0
    total_hl_rechazo_parcial = 0.0
    total_hl_rechazo_total = 0.0
    total_bultos = 0.0
    total_bultos_rechazo = 0.0
    total_bultos_rechazo_parcial = 0.0
    total_bultos_rechazo_total = 0.0
    total_pedidos = 0
    total_pedidos_rechazo = 0
    total_rmcyo_hl = 0.0
    total_rmcyo_hl_rechazo = 0.0
    total_rmcyo_bultos = 0.0
    total_rmcyo_bultos_rechazo = 0.0
    total_rmcyo_pedidos = 0
    total_rmcyo_pedidos_rechazo = 0
    peor_mes = None
    mejor_mes = None

    for r in meses_raw:
        bultos_total = float(r.get('bultos_total') or 0)
        bultos_rechazo = float(r.get('bultos_rechazo') or 0)
        bultos_rechazo_parcial = float(r.get('bultos_rechazo_parcial') or 0)
        bultos_rechazo_total = float(r.get('bultos_rechazo_total') or 0)
        bultos_despachado = bultos_total
        hl_total = float(r.get('hl_total') or 0)
        hl_rechazo = float(r.get('hl_rechazo') or 0)
        hl_rechazo_parcial = float(r.get('hl_rechazo_parcial') or 0)
        hl_rechazo_total = float(r.get('hl_rechazo_total') or 0)
        hl_despachado = hl_total
        pedidos_total = int(r.get('pedidos_total') or 0)
        pedidos_rechazo = int(r.get('pedidos_rechazo') or 0)
        rmcyo_bultos = float(r.get('rmcyo_bultos') or 0)
        rmcyo_hl = float(r.get('rmcyo_hl') or 0)
        rmcyo_b_rec = float(r.get('rmcyo_b_rec') or 0)
        rmcyo_hl_rec = float(r.get('rmcyo_hl_rec') or 0)
        rmcyo_pedidos = int(r.get('rmcyo_pedidos') or 0)
        rmcyo_p_rec = int(r.get('rmcyo_p_rec') or 0)
        pct_hl = round(hl_rechazo / hl_total * 100, 2) if hl_total else 0
        pct_bultos = round(bultos_rechazo / bultos_total * 100, 2) if bultos_total else 0
        pct_pedidos = round(pedidos_rechazo / pedidos_total * 100, 2) if pedidos_total else 0
        row = {
            'mes': r['mes'],
            'bultos_total': round(bultos_total, 1),
            'bultos_despachado': round(bultos_despachado, 1),
            'bultos_entregado': round(bultos_despachado, 1),
            'bultos_rechazo': round(bultos_rechazo, 1),
            'bultos_rechazo_parcial': round(bultos_rechazo_parcial, 1),
            'bultos_rechazo_total': round(bultos_rechazo_total, 1),
            'pct_rechazo_bultos': pct_bultos,
            'hl_total': round(hl_total, 1),
            'hl_despachado': round(hl_despachado, 1),
            'hl_entregado': round(hl_despachado, 1),
            'hl_rechazo': round(hl_rechazo, 1),
            'hl_rechazo_parcial': round(hl_rechazo_parcial, 1),
            'hl_rechazo_total': round(hl_rechazo_total, 1),
            'pct_rechazo_hl': pct_hl,
            'pedidos_total': pedidos_total,
            'pedidos_rechazo': pedidos_rechazo,
            'pct_rechazo_pedidos': pct_pedidos,
            'rmcyo_bultos': round(rmcyo_bultos, 1),
            'rmcyo_hl': round(rmcyo_hl, 1),
            'rmcyo_rechazo_bultos': round(rmcyo_b_rec, 1),
            'rmcyo_rechazo_hl': round(rmcyo_hl_rec, 1),
            'rmcyo_pedidos': rmcyo_pedidos,
            'rmcyo_rechazo_pedidos': rmcyo_p_rec,
            'rmcyo_pct_rechazo_bultos': round(rmcyo_b_rec / rmcyo_bultos * 100, 2) if rmcyo_bultos else 0,
            'rmcyo_pct_rechazo_hl': round(rmcyo_hl_rec / rmcyo_hl * 100, 2) if rmcyo_hl else 0,
            'rmcyo_pct_rechazo_pedidos': round(rmcyo_p_rec / rmcyo_pedidos * 100, 2) if rmcyo_pedidos else 0,
            'dias': int(r.get('dias') or 0),
            'salidas': int(r.get('salidas') or 0),
        }
        meses.append(row)
        total_hl += hl_total
        total_hl_rechazo += hl_rechazo
        total_hl_rechazo_parcial += hl_rechazo_parcial
        total_hl_rechazo_total += hl_rechazo_total
        total_bultos += bultos_total
        total_bultos_rechazo += bultos_rechazo
        total_bultos_rechazo_parcial += bultos_rechazo_parcial
        total_bultos_rechazo_total += bultos_rechazo_total
        total_pedidos += pedidos_total
        total_pedidos_rechazo += pedidos_rechazo
        total_rmcyo_hl += rmcyo_hl
        total_rmcyo_hl_rechazo += rmcyo_hl_rec
        total_rmcyo_bultos += rmcyo_bultos
        total_rmcyo_bultos_rechazo += rmcyo_b_rec
        total_rmcyo_pedidos += rmcyo_pedidos
        total_rmcyo_pedidos_rechazo += rmcyo_p_rec
        if peor_mes is None or row['pct_rechazo_hl'] > peor_mes['pct_rechazo_hl']:
            peor_mes = row
        if mejor_mes is None or row['pct_rechazo_hl'] < mejor_mes['pct_rechazo_hl']:
            mejor_mes = row

    motivos = []
    for r in motivos_raw:
        hl = float(r.get('hl_rechazo') or 0)
        hl_parcial = float(r.get('hl_rechazo_parcial') or 0)
        hl_total_rec = float(r.get('hl_rechazo_total') or 0)
        bultos = float(r.get('bultos_rechazo') or 0)
        bultos_parcial = float(r.get('bultos_rechazo_parcial') or 0)
        bultos_total_rec = float(r.get('bultos_rechazo_total') or 0)
        motivos.append({
            'sector': r.get('sector') or 'Sin sector',
            'motivo': r.get('motivo') or 'Sin motivo',
            'bultos_rechazo': round(bultos, 1),
            'bultos_rechazo_parcial': round(bultos_parcial, 1),
            'bultos_rechazo_total': round(bultos_total_rec, 1),
            'hl_rechazo': round(hl, 1),
            'hl_rechazo_parcial': round(hl_parcial, 1),
            'hl_rechazo_total': round(hl_total_rec, 1),
            'pedidos_rechazo': int(r.get('pedidos_rechazo') or 0),
            'ocurrencias': int(r.get('ocurrencias') or 0),
            'pct_del_rechazo_bultos': round(bultos / total_bultos_rechazo * 100, 1) if total_bultos_rechazo else 0,
            'pct_del_rechazo_hl': round(hl / total_hl_rechazo * 100, 1) if total_hl_rechazo else 0,
            'pct_del_rechazo': round(hl / total_hl_rechazo * 100, 1) if total_hl_rechazo else 0,
            'meses_con_rechazo': int(r.get('meses_con_rechazo') or 0),
        })

    return {
        'sucursal': sucursal,
        'meses': meses,
        'motivos': motivos,
        'totales': {
            'bultos_total': round(total_bultos, 1),
            'bultos_despachado': round(total_bultos, 1),
            'bultos_entregado': round(total_bultos, 1),
            'bultos_rechazo': round(total_bultos_rechazo, 1),
            'bultos_rechazo_parcial': round(total_bultos_rechazo_parcial, 1),
            'bultos_rechazo_total': round(total_bultos_rechazo_total, 1),
            'pct_rechazo_bultos': round(total_bultos_rechazo / total_bultos * 100, 2) if total_bultos else 0,
            'hl_total': round(total_hl, 1),
            'hl_despachado': round(total_hl, 1),
            'hl_entregado': round(total_hl, 1),
            'hl_rechazo': round(total_hl_rechazo, 1),
            'hl_rechazo_parcial': round(total_hl_rechazo_parcial, 1),
            'hl_rechazo_total': round(total_hl_rechazo_total, 1),
            'pct_rechazo_hl': round(total_hl_rechazo / total_hl * 100, 2) if total_hl else 0,
            'pedidos_total': total_pedidos,
            'pedidos_rechazo': total_pedidos_rechazo,
            'pct_rechazo_pedidos': round(total_pedidos_rechazo / total_pedidos * 100, 2) if total_pedidos else 0,
            'rmcyo_bultos': round(total_rmcyo_bultos, 1),
            'rmcyo_hl': round(total_rmcyo_hl, 1),
            'rmcyo_rechazo_bultos': round(total_rmcyo_bultos_rechazo, 1),
            'rmcyo_rechazo_hl': round(total_rmcyo_hl_rechazo, 1),
            'rmcyo_pedidos': total_rmcyo_pedidos,
            'rmcyo_rechazo_pedidos': total_rmcyo_pedidos_rechazo,
            'rmcyo_pct_rechazo_bultos': round(total_rmcyo_bultos_rechazo / total_rmcyo_bultos * 100, 2) if total_rmcyo_bultos else 0,
            'rmcyo_pct_rechazo_hl': round(total_rmcyo_hl_rechazo / total_rmcyo_hl * 100, 2) if total_rmcyo_hl else 0,
            'rmcyo_pct_rechazo_pedidos': round(total_rmcyo_pedidos_rechazo / total_rmcyo_pedidos * 100, 2) if total_rmcyo_pedidos else 0,
            'peor_mes': peor_mes['mes'] if peor_mes else None,
            'peor_pct_rechazo_hl': peor_mes['pct_rechazo_hl'] if peor_mes else 0,
            'mejor_mes': mejor_mes['mes'] if mejor_mes else None,
            'mejor_pct_rechazo_hl': mejor_mes['pct_rechazo_hl'] if mejor_mes else 0,
        },
    }


# ── Detalle de un día ─────────────────────────────────────────

def get_detalle_dia(sucursal: str, fecha: date) -> dict:
    ensure_ventas_detalle_table()
    ensure_transportes_table()

    swv = _suc_filter(sucursal, 'v')
    p   = {'f': fecha, 's': sucursal}

    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT
                {V_TRUCK_KEY} AS camion_key,
                MAX(t.placa) AS patente,
                COALESCE(MAX(t.descripcion), MAX(v.descripcion_transporte)) AS transporte,
                MAX(t.carga_maxima_kg) AS carga_maxima_kg,
                MAX(t.capacidad_up) AS capacidad_up,
                NULL::text AS chofer,
                0 AS planillas,
                COUNT(DISTINCT {V_PEDIDO_KEY}) AS pedidos,
                SUM(COALESCE(v.bultos, 0)) AS bultos_totales,
                SUM({V_PALLETS_EXPR}) AS pallets,
                SUM(COALESCE(v.unidad_paquete, 0)) AS up,
                SUM(COALESCE(v.importe_neto, 0)) AS importe_total,
                NULL::timestamp AS fecha_salida,
                NULL::timestamp AS fecha_llegada
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            LEFT JOIN transportes t ON TRIM(COALESCE(v.transporte, '')) = t.codigo::text
            WHERE v.fecha = %(f)s {swv}
              AND {IS_MERCADERIA}
              AND {V_NOT_REMITO}
            GROUP BY {V_TRUCK_KEY}
            ORDER BY camion_key
        """, p)
        planillas = [dict(r) for r in cur.fetchall()]

        cur.execute(f"""
            SELECT COUNT(DISTINCT {V_TRUCK_KEY}) AS salidas_unicas
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            WHERE v.fecha = %(f)s {swv}
              AND {IS_MERCADERIA}
              AND {V_NOT_REMITO}
        """, p)
        salidas_unicas = int((cur.fetchone() or {}).get('salidas_unicas') or 0)

        cur.execute(f"""
            SELECT COUNT(DISTINCT {V_CLIENT_KEY}) AS clientes_unicos
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            WHERE v.fecha = %(f)s {swv}
              AND {IS_MERCADERIA}
              AND {V_NOT_REMITO}
        """, p)
        clientes_unicos = int((cur.fetchone() or {}).get('clientes_unicos') or 0)

        cur.execute(f"""
            SELECT v.id_articulo, MAX(v.descripcion_articulo) AS descripcion_articulo, '' AS unidad_medida,
                SUM(COALESCE(v.bultos, 0)) AS bultos,
                SUM(COALESCE(v.unidad_medida, 0)) AS cant_um,
                SUM(CASE WHEN {V_IS_REC} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS b_rec,
                SUM(CASE WHEN {V_IS_REC_PARCIAL} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS b_rec_parcial,
                SUM(CASE WHEN {V_IS_REC_TOTAL} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS b_rec_total,
                SUM(CASE WHEN {V_IS_REC} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rec,
                SUM(CASE WHEN {V_IS_REC_PARCIAL} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rec_parcial,
                SUM(CASE WHEN {V_IS_REC_TOTAL} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rec_total,
                COUNT(DISTINCT CASE WHEN {V_IS_REC} THEN {V_PEDIDO_KEY} END) AS p_rec,
                SUM(COALESCE(v.unidad_medida, 0)) AS hl
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            {V_REC_JOIN}
            WHERE v.fecha = %(f)s {swv}
              AND {IS_MERCADERIA}
              AND {V_NOT_REMITO}
            GROUP BY v.id_articulo
            ORDER BY bultos DESC LIMIT 30
        """, p)
        top_arts = [dict(r) for r in cur.fetchall()]

        cur.execute(f"""
            SELECT COALESCE(v.motivo_rechazo,'Sin motivo') AS motivo,
                COUNT(DISTINCT {V_PEDIDO_KEY}) AS pedidos,
                COUNT(*) AS ocurrencias,
                SUM(COALESCE(v.bultos_rechazados, 0)) AS bultos,
                SUM(CASE WHEN {V_RECHAZO_TOTAL_FLAG} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS bultos_total,
                SUM(CASE WHEN NOT {V_RECHAZO_TOTAL_FLAG} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS bultos_parcial,
                SUM(COALESCE(v.unidad_medida_rechazado, 0)) AS hectolitros
                ,SUM(CASE WHEN {V_RECHAZO_TOTAL_FLAG} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hectolitros_total
                ,SUM(CASE WHEN NOT {V_RECHAZO_TOTAL_FLAG} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hectolitros_parcial
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            {V_REC_JOIN}
            WHERE v.fecha = %(f)s {swv}
                  AND {V_IS_REC}
                  AND {IS_MERCADERIA}
                  AND {V_NOT_REMITO}
            GROUP BY motivo ORDER BY bultos DESC
        """, p)
        rechazos = [dict(r) for r in cur.fetchall()]

        cur.execute(f"""
            SELECT DISTINCT
                {V_CLIENT_KEY} AS id_cliente,
                COALESCE(c.razon_social, COALESCE(v.descripcion_cliente, '')) AS nombre_cliente,
                COALESCE(c.sucursal, v.sucursal) AS sucursal
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            LEFT JOIN clientes c ON {V_CLIENT_KEY} = c.cliente
            WHERE v.fecha = %(f)s {swv}
              AND {IS_MERCADERIA}
              AND {V_NOT_REMITO}
            ORDER BY sucursal, nombre_cliente
        """, p)
        clientes = [dict(r) for r in cur.fetchall()]

        cur.execute(f"""
            SELECT COALESCE(c.sucursal, v.sucursal) AS sucursal,
                COUNT(DISTINCT {V_CLIENT_KEY}) AS clientes_unicos
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            LEFT JOIN clientes c ON {V_CLIENT_KEY} = c.cliente
            WHERE v.fecha = %(f)s {swv}
              AND {IS_MERCADERIA}
              AND {V_NOT_REMITO}
            GROUP BY COALESCE(c.sucursal, v.sucursal)
            ORDER BY sucursal
        """, p)
        clientes_por_sucursal = [dict(r) for r in cur.fetchall()]

    return {
        'fecha':              fecha.isoformat(),
        'planillas':          planillas,
        'salidas_unicas':     salidas_unicas,
        'clientes_unicos':    clientes_unicos,
        'clientes':           clientes,
        'clientes_por_sucursal': clientes_por_sucursal,
        'top_articulos':      top_arts,
        'rechazos':           rechazos,
    }
