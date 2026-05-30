"""
Peak-day detection and aggregation queries against Railway PostgreSQL.
All heavy SQL lives here; routes stay thin.
"""

from __future__ import annotations
from datetime import date, timedelta
import calendar as cal_mod
import threading

import psycopg2.extras

from app.database import pg_cursor
from app.services.articulos_svc import ensure_articulos_table
from app.services.rechazos_svc import ensure_table as ensure_rechazos_table
from app.services.transportes_svc import ensure_transportes_table
from app.services.ventas_svc import ensure_ventas_detalle_table

NDS_UMBRAL_DEFAULT = 85.0  # días con NDS < 85% se marcan como problema

_PC_TABLE_READY = False
_PC_TABLE_LOCK = threading.Lock()
_AUS_TABLE_READY = False
_AUS_TABLE_LOCK = threading.Lock()


def _ensure_periodos_criticos_table() -> None:
    global _PC_TABLE_READY
    if _PC_TABLE_READY:
        return
    with _PC_TABLE_LOCK:
        if _PC_TABLE_READY:
            return
        with pg_cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS periodos_criticos (
                    id SERIAL PRIMARY KEY,
                    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
                    sucursal_id VARCHAR(50) NOT NULL DEFAULT 'TODAS',
                    nombre VARCHAR(100) NOT NULL,
                    fecha_inicio DATE NOT NULL,
                    fecha_fin DATE NOT NULL,
                    motivo VARCHAR(255),
                    anio INTEGER NOT NULL,
                    estado VARCHAR(20) NOT NULL DEFAULT 'activo',
                    creado TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT periodos_criticos_duracion CHECK (
                        fecha_fin >= fecha_inicio
                        AND fecha_fin <= fecha_inicio + INTERVAL '6 days'
                    )
                );
                CREATE INDEX IF NOT EXISTS idx_periodos_criticos_lookup
                    ON periodos_criticos(empresa_id, sucursal_id, anio);
            """)
        _PC_TABLE_READY = True


def _ensure_ausentismo_mensual_table() -> None:
    global _AUS_TABLE_READY
    if _AUS_TABLE_READY:
        return
    with _AUS_TABLE_LOCK:
        if _AUS_TABLE_READY:
            return
        with pg_cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ausentismo_mensual (
                    id SERIAL PRIMARY KEY,
                    empresa_id  VARCHAR(50) NOT NULL DEFAULT '1',
                    sucursal_id VARCHAR(50) NOT NULL DEFAULT 'TODAS',
                    anio        INTEGER     NOT NULL,
                    mes         INTEGER     NOT NULL CHECK (mes BETWEEN 1 AND 12),
                    pct_ausentismo NUMERIC(6,2) NOT NULL,
                    actualizado TIMESTAMP DEFAULT NOW(),
                    UNIQUE(empresa_id, sucursal_id, anio, mes)
                );
                CREATE INDEX IF NOT EXISTS idx_ausentismo_mensual_lookup
                    ON ausentismo_mensual(empresa_id, sucursal_id, anio);
            """)
        _AUS_TABLE_READY = True

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

def _get_ausentismo_mes(sucursal: str, mes: str) -> dict[str, int]:
    """Devuelve {fecha_iso: ausentes} para el mes dado. Silencia errores si MySQL no está."""
    try:
        from app.services import ausentismo_svc
        suc = None if sucursal == 'TODAS' else sucursal
        result = ausentismo_svc.get_ausentismo(sucursal=suc, mes=mes)
        if not result.get('disponible'):
            return {}
        aus_map = {}
        for row in (result.get('data') or []):
            fk = str(row.get('fecha') or '')[:10]
            if fk:
                aus_map[fk] = int(row.get('ausentes') or 0)
        return aus_map
    except Exception:
        return {}


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

    aus_map = _get_ausentismo_mes(sucursal, mes)

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
        nds = round((p_tot - p_rec) / p_tot * 100, 1) if p_tot else 100.0
        ausentismo_dia = aus_map.get(fk, 0)
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
            'nds': nds,
            'es_problema_nds': nds < NDS_UMBRAL_DEFAULT,
            'ausentismo': ausentismo_dia,
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


# ── Ausentismo mensual histórico ──────────────────────────────

NOMBRES_MES = ['Ene','Feb','Mar','Abr','May','Jun',
               'Jul','Ago','Sep','Oct','Nov','Dic']

# Umbral a partir del cual se considera ausentismo alto (boost al score)
AUS_UMBRAL_ALTO = 10.0   # >= 10% → boost fuerte
AUS_UMBRAL_MEDIO = 5.0   # >= 5%  → boost moderado


def get_ausentismo_mensual(empresa_id: str, sucursal_id: str, anio: int) -> list[dict]:
    _ensure_ausentismo_mensual_table()
    with pg_cursor() as cur:
        cur.execute("""
            SELECT mes, pct_ausentismo
            FROM ausentismo_mensual
            WHERE empresa_id = %(e)s AND sucursal_id = %(s)s AND anio = %(a)s
            ORDER BY mes
        """, {'e': empresa_id, 's': sucursal_id, 'a': anio})
        rows = [dict(r) for r in cur.fetchall()]
    # Completar meses faltantes con None
    by_mes = {r['mes']: float(r['pct_ausentismo']) for r in rows}
    return [
        {'mes': m, 'nombre': NOMBRES_MES[m - 1], 'pct_ausentismo': by_mes.get(m)}
        for m in range(1, 13)
    ]


def guardar_ausentismo_mensual(data: dict) -> dict:
    _ensure_ausentismo_mensual_table()
    empresa_id  = str(data.get('empresa_id') or '1')
    sucursal_id = str(data.get('sucursal_id') or 'TODAS')
    anio = int(data.get('anio') or 0)
    filas = data.get('filas') or []  # [{mes, pct_ausentismo}, ...]
    if not anio:
        raise ValueError("anio requerido")
    if not filas:
        raise ValueError("filas requeridas")
    with pg_cursor() as cur:
        for f in filas:
            mes = int(f.get('mes') or 0)
            pct = float(f.get('pct_ausentismo') or 0)
            if mes < 1 or mes > 12:
                continue
            cur.execute("""
                INSERT INTO ausentismo_mensual
                    (empresa_id, sucursal_id, anio, mes, pct_ausentismo)
                VALUES (%(e)s, %(s)s, %(a)s, %(m)s, %(p)s)
                ON CONFLICT (empresa_id, sucursal_id, anio, mes)
                DO UPDATE SET pct_ausentismo = EXCLUDED.pct_ausentismo,
                              actualizado = NOW()
            """, {'e': empresa_id, 's': sucursal_id, 'a': anio, 'm': mes, 'p': pct})
    return get_ausentismo_mensual(empresa_id, sucursal_id, anio)


def _aus_mensual_by_mes(empresa_id: str, sucursal_id: str, anio: int) -> dict[int, float]:
    """Devuelve {mes: pct} para el año indicado. Si no hay datos, intenta el año anterior."""
    _ensure_ausentismo_mensual_table()
    for a in (anio, anio - 1):
        with pg_cursor() as cur:
            cur.execute("""
                SELECT mes, pct_ausentismo FROM ausentismo_mensual
                WHERE empresa_id = %(e)s AND sucursal_id = %(s)s AND anio = %(a)s
            """, {'e': empresa_id, 's': sucursal_id, 'a': a})
            rows = cur.fetchall()
        if rows:
            return {r['mes']: float(r['pct_ausentismo']) for r in rows}
    return {}


# ── Periodos críticos ─────────────────────────────────────────

def _nombre_periodo(fecha_inicio: str, fecha_fin: str) -> str:
    """Genera nombre descriptivo para un periodo."""
    MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
             'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    fi = date.fromisoformat(fecha_inicio)
    ff = date.fromisoformat(fecha_fin)
    if fi == ff:
        return f"Periodo {MESES[fi.month - 1]} {fi.day}"
    if fi.month == ff.month:
        return f"Periodo {MESES[fi.month - 1]} {fi.day}-{ff.day}"
    return f"Periodo {MESES[fi.month - 1]} {fi.day} - {MESES[ff.month - 1]} {ff.day}"


def get_periodos_criticos(empresa_id: str, sucursal_id: str, anio: int) -> list[dict]:
    _ensure_periodos_criticos_table()
    with pg_cursor() as cur:
        cur.execute("""
            SELECT id, empresa_id, sucursal_id, nombre,
                   fecha_inicio::text, fecha_fin::text,
                   motivo, anio, estado, creado::text
            FROM periodos_criticos
            WHERE empresa_id = %(e)s AND sucursal_id = %(s)s AND anio = %(a)s
            ORDER BY fecha_inicio
        """, {'e': empresa_id, 's': sucursal_id, 'a': anio})
        return [dict(r) for r in cur.fetchall()]


def guardar_periodo_critico(data: dict) -> dict:
    _ensure_periodos_criticos_table()
    empresa_id = str(data.get('empresa_id') or '1')
    sucursal_id = str(data.get('sucursal_id') or 'TODAS')
    nombre = str(data.get('nombre') or '').strip()
    fecha_inicio = data.get('fecha_inicio')
    fecha_fin = data.get('fecha_fin') or fecha_inicio
    motivo = data.get('motivo') or None
    anio = int(data.get('anio') or date.fromisoformat(str(fecha_inicio)).year)

    if not nombre:
        raise ValueError("nombre requerido")
    if not fecha_inicio:
        raise ValueError("fecha_inicio requerida")

    fi = date.fromisoformat(str(fecha_inicio))
    ff = date.fromisoformat(str(fecha_fin))
    if ff < fi:
        raise ValueError("fecha_fin debe ser >= fecha_inicio")
    if (ff - fi).days > 6:
        raise ValueError("El periodo no puede superar 7 dias")

    with pg_cursor() as cur:
        cur.execute("""
            INSERT INTO periodos_criticos
                (empresa_id, sucursal_id, nombre, fecha_inicio, fecha_fin, motivo, anio)
            VALUES (%(e)s, %(s)s, %(n)s, %(fi)s, %(ff)s, %(m)s, %(a)s)
            RETURNING id, empresa_id, sucursal_id, nombre,
                      fecha_inicio::text, fecha_fin::text, motivo, anio, estado
        """, {
            'e': empresa_id, 's': sucursal_id, 'n': nombre,
            'fi': fi, 'ff': ff, 'm': motivo, 'a': anio,
        })
        return dict(cur.fetchone())


def eliminar_periodo_critico(periodo_id: int) -> None:
    _ensure_periodos_criticos_table()
    with pg_cursor() as cur:
        cur.execute("DELETE FROM periodos_criticos WHERE id = %s", (periodo_id,))


def sugerir_periodos_criticos(sucursal: str, anio: int) -> list[dict]:
    """Analiza el año y sugiere periodos críticos usando volumen, NDS y ausentismo histórico."""
    _ensure_periodos_criticos_table()
    ensure_ventas_detalle_table()
    ensure_articulos_table()
    ensure_rechazos_table()

    empresa_id = '1'
    ini = date(anio, 1, 1)
    fin = date(anio, 12, 31)
    swv = _suc_filter(sucursal, 'v')
    p = {'ini': ini, 'fin': fin, 's': sucursal}

    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT v.fecha::text AS f,
                SUM(COALESCE(v.bultos, 0)) AS b_tot,
                COUNT(DISTINCT {V_PEDIDO_KEY}) AS p_tot,
                COUNT(DISTINCT CASE WHEN {V_IS_REC} THEN {V_PEDIDO_KEY} END) AS p_rec
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            {V_REC_JOIN}
            WHERE v.fecha BETWEEN %(ini)s AND %(fin)s {swv}
              AND {IS_MERCADERIA}
              AND {V_NOT_REMITO}
            GROUP BY v.fecha
            ORDER BY v.fecha
        """, p)
        dias_raw = {r['f']: dict(r) for r in cur.fetchall()}

    if not dias_raw:
        return []

    # --- A) Ausentismo mensual histórico (tabla PostgreSQL) ---
    aus_hist = _aus_mensual_by_mes(empresa_id, sucursal, anio)

    # --- Ausentismo diario desde MySQL (si está disponible) ---
    aus_diario: dict[str, int] = {}
    try:
        from app.services import ausentismo_svc
        suc_param = None if sucursal == 'TODAS' else sucursal
        for mes_num in range(1, 13):
            mes_str = f"{anio}-{mes_num:02d}"
            result = ausentismo_svc.get_ausentismo(sucursal=suc_param, mes=mes_str)
            if result.get('disponible'):
                for row in (result.get('data') or []):
                    fk = str(row.get('fecha') or '')[:10]
                    if fk:
                        aus_diario[fk] = int(row.get('ausentes') or 0)
    except Exception:
        pass

    vols = [float(d.get('b_tot') or 0) for d in dias_raw.values() if float(d.get('b_tot') or 0) > 0]
    avg_vol = sum(vols) / len(vols) if vols else 1.0
    umbral_vol = avg_vol * 1.20

    # --- B) Umbral dinámico calibrado con ausentismo histórico ---
    # Meses con aus >= AUS_UMBRAL_ALTO tienen threshold reducido → siempre sugeridos
    meses_aus_alto  = {m for m, v in aus_hist.items() if v >= AUS_UMBRAL_ALTO}
    meses_aus_medio = {m for m, v in aus_hist.items() if AUS_UMBRAL_MEDIO <= v < AUS_UMBRAL_ALTO}

    # --- C) Puntuar cada día ---
    dias_scored: list[dict] = []
    for fk in sorted(dias_raw):
        d = dias_raw[fk]
        mes_num = int(fk[5:7])
        vol = float(d.get('b_tot') or 0)
        p_tot = int(d.get('p_tot') or 0)
        p_rec = int(d.get('p_rec') or 0)
        nds = (p_tot - p_rec) / p_tot * 100 if p_tot else 100.0
        aus_dia = aus_diario.get(fk, 0)

        vol_score   = min(1.0, vol / umbral_vol) if umbral_vol > 0 else 0.0
        nds_penalty = max(0.0, 1.0 - nds / 100.0)
        aus_penalty = min(1.0, aus_dia / 5.0)

        # Boost por ausentismo mensual histórico (C)
        if mes_num in meses_aus_alto:
            aus_boost = 0.35
        elif mes_num in meses_aus_medio:
            aus_boost = 0.18
        else:
            aus_boost = 0.0

        score = vol_score * 0.45 + nds_penalty * 0.30 + aus_penalty * 0.10 + aus_boost

        dias_scored.append({
            'fecha': fk,
            'score': score,
            'es_pico': vol >= umbral_vol,
            'es_nds_problema': nds < NDS_UMBRAL_DEFAULT,
            'es_aus_historico': mes_num in meses_aus_alto or mes_num in meses_aus_medio,
            'ausentismo_diario': aus_dia,
            'pct_aus_mes': aus_hist.get(mes_num, 0.0),
            'bultos': round(vol, 0),
            'nds': round(nds, 1),
        })

    # Threshold reducido porque ahora el boost garantiza que meses críticos suban
    SCORE_THRESHOLD = 0.35
    periodos: list[dict] = []
    current: dict | None = None

    for day in dias_scored:
        es_critico = (
            day['score'] >= SCORE_THRESHOLD
            or day['es_pico']
            or day['es_nds_problema']
            or day['es_aus_historico']
        )
        if es_critico:
            if current is None:
                current = {
                    'fecha_inicio': day['fecha'],
                    'fecha_fin': day['fecha'],
                    'dias': [day],
                    'score_total': day['score'],
                }
            else:
                last = date.fromisoformat(current['fecha_fin'])
                curr = date.fromisoformat(day['fecha'])
                duracion = (curr - date.fromisoformat(current['fecha_inicio'])).days
                if (curr - last).days <= 2 and duracion < 6:
                    current['fecha_fin'] = day['fecha']
                    current['dias'].append(day)
                    current['score_total'] += day['score']
                else:
                    periodos.append(current)
                    current = {
                        'fecha_inicio': day['fecha'],
                        'fecha_fin': day['fecha'],
                        'dias': [day],
                        'score_total': day['score'],
                    }
        else:
            if current:
                periodos.append(current)
                current = None

    if current:
        periodos.append(current)

    periodos.sort(key=lambda x: x['score_total'], reverse=True)

    result = []
    for per in periodos:
        dias = per['dias']
        avg_nds = sum(d['nds'] for d in dias) / len(dias)
        avg_aus_hist = sum(d['pct_aus_mes'] for d in dias) / len(dias)
        motivos = []
        if any(d['es_pico'] for d in dias):
            motivos.append('alto volumen')
        if any(d['es_nds_problema'] for d in dias):
            motivos.append('NDS bajo')
        if any(d['es_aus_historico'] for d in dias):
            motivos.append(f'ausentismo hist. {round(avg_aus_hist, 1)}%')
        if any(d['ausentismo_diario'] >= 3 for d in dias):
            motivos.append('ausentismo real')
        duracion = (
            date.fromisoformat(per['fecha_fin']) - date.fromisoformat(per['fecha_inicio'])
        ).days + 1
        result.append({
            'fecha_inicio': per['fecha_inicio'],
            'fecha_fin': per['fecha_fin'],
            'duracion_dias': duracion,
            'score': round(per['score_total'], 2),
            'nds_promedio': round(avg_nds, 1),
            'pct_ausentismo_historico': round(avg_aus_hist, 1),
            'motivo_sugerido': ', '.join(motivos) if motivos else 'volumen elevado',
            'nombre_sugerido': _nombre_periodo(per['fecha_inicio'], per['fecha_fin']),
        })

    return result


# ── Dotación operativa ────────────────────────────────────────

SUC_LABELS = {'1': 'Casa Central', '2': 'Dolores'}


def get_dotacion_diaria(empresa_id: str, sucursal_id: str,
                        fecha_ini: date, fecha_fin: date) -> dict:
    """Devuelve filas de operacion_camiones día a día, agrupadas por sucursal."""
    suc_filter = "" if sucursal_id == 'TODAS' else "AND sucursal_id = %(s)s"
    p = {'e': empresa_id, 's': sucursal_id, 'fi': fecha_ini, 'ff': fecha_fin}

    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT fecha, sucursal_id, nro_salida, chofer,
                   ayudante_1, ayudante_2
            FROM operacion_camiones
            WHERE empresa_id = %(e)s
              AND fecha BETWEEN %(fi)s AND %(ff)s
              {suc_filter}
            ORDER BY fecha DESC, sucursal_id, nro_salida
        """, p)
        rows = [dict(r) for r in cur.fetchall()]

    # Agrupar por fecha+sucursal y calcular personas por día
    from collections import defaultdict
    by_fecha_suc: dict = defaultdict(list)
    for r in rows:
        key = (str(r['fecha']), r['sucursal_id'])
        by_fecha_suc[key].append(r)

    dias_cc, dias_dl, dias_total = [], [], []
    fechas_vistas: set = set()

    for (fk, suc), salidas in sorted(by_fecha_suc.items(), reverse=True):
        choferes  = sum(1 for s in salidas if s['chofer'])
        ayu1      = sum(1 for s in salidas if s['ayudante_1'])
        ayu2      = sum(1 for s in salidas if s['ayudante_2'])
        total_p   = choferes + ayu1 + ayu2
        resumen = {
            'fecha': fk,
            'sucursal_id': suc,
            'sucursal_nombre': SUC_LABELS.get(suc, suc),
            'n_salidas': len(salidas),
            'n_choferes': choferes,
            'n_ayudante1': ayu1,
            'n_ayudante2': ayu2,
            'total_personas': total_p,
            'detalle': [
                {
                    'nro_salida': s['nro_salida'],
                    'chofer': s['chofer'] or '—',
                    'ayudante_1': s['ayudante_1'] or '—',
                    'ayudante_2': s['ayudante_2'] or '—',
                    'personas': (1 if s['chofer'] else 0)
                                + (1 if s['ayudante_1'] else 0)
                                + (1 if s['ayudante_2'] else 0),
                }
                for s in salidas
            ],
        }
        if suc == '1':
            dias_cc.append(resumen)
        elif suc == '2':
            dias_dl.append(resumen)
        fechas_vistas.add(fk)

    # Total empresa: sumar CC + Dolores por fecha
    totales_by_fecha: dict = {}
    for r in dias_cc + dias_dl:
        fk = r['fecha']
        if fk not in totales_by_fecha:
            totales_by_fecha[fk] = {
                'fecha': fk, 'sucursal_id': 'TODAS',
                'sucursal_nombre': 'Empresa',
                'n_salidas': 0, 'n_choferes': 0,
                'n_ayudante1': 0, 'n_ayudante2': 0, 'total_personas': 0,
            }
        t = totales_by_fecha[fk]
        t['n_salidas']    += r['n_salidas']
        t['n_choferes']   += r['n_choferes']
        t['n_ayudante1']  += r['n_ayudante1']
        t['n_ayudante2']  += r['n_ayudante2']
        t['total_personas'] += r['total_personas']
    dias_total = sorted(totales_by_fecha.values(), key=lambda x: x['fecha'], reverse=True)

    return {
        'casa_central': dias_cc,
        'dolores': dias_dl,
        'total': dias_total,
    }


def get_dotacion_mensual(empresa_id: str, anio: int, anio_base: int) -> dict:
    """Promedios mensuales de dotación por sucursal para dos años."""
    p = {'e': empresa_id, 'ini': date(min(anio, anio_base), 1, 1),
         'fin': date(max(anio, anio_base), 12, 31)}

    with pg_cursor() as cur:
        cur.execute("""
            WITH daily AS (
                SELECT
                    EXTRACT(YEAR  FROM fecha)::int AS anio,
                    EXTRACT(MONTH FROM fecha)::int AS mes,
                    sucursal_id,
                    fecha,
                    COUNT(*)                                              AS n_salidas,
                    COUNT(chofer)                                         AS n_choferes,
                    COUNT(ayudante_1) FILTER (WHERE ayudante_1 IS NOT NULL
                                              AND   ayudante_1 != '')    AS n_ayu1,
                    COUNT(ayudante_2) FILTER (WHERE ayudante_2 IS NOT NULL
                                              AND   ayudante_2 != '')    AS n_ayu2
                FROM operacion_camiones
                WHERE empresa_id = %(e)s
                  AND fecha BETWEEN %(ini)s AND %(fin)s
                GROUP BY 1, 2, 3, 4
            )
            SELECT anio, mes, sucursal_id,
                   COUNT(DISTINCT fecha)          AS dias,
                   ROUND(AVG(n_salidas),  1)      AS avg_salidas,
                   ROUND(AVG(n_choferes), 1)      AS avg_choferes,
                   ROUND(AVG(n_ayu1),     1)      AS avg_ayu1,
                   ROUND(AVG(n_ayu2),     1)      AS avg_ayu2,
                   ROUND(AVG(n_choferes + n_ayu1 + n_ayu2), 1) AS avg_personas
            FROM daily
            GROUP BY 1, 2, 3
            ORDER BY 1, 2, 3
        """, p)
        rows = [dict(r) for r in cur.fetchall()]

    # Organizar: {(anio, mes, suc): row}
    by_key: dict = {}
    for r in rows:
        by_key[(r['anio'], r['mes'], r['sucursal_id'])] = r

    # Calcular totals empresa (CC + Dolores) por año+mes
    from collections import defaultdict
    total_tmp: dict = defaultdict(lambda: {
        'dias': 0, 'avg_salidas': 0.0, 'avg_choferes': 0.0,
        'avg_ayu1': 0.0, 'avg_ayu2': 0.0, 'avg_personas': 0.0, '_n': 0,
    })
    for r in rows:
        k = (r['anio'], r['mes'])
        t = total_tmp[k]
        t['avg_salidas']  += float(r['avg_salidas']  or 0)
        t['avg_choferes'] += float(r['avg_choferes'] or 0)
        t['avg_ayu1']     += float(r['avg_ayu1']     or 0)
        t['avg_ayu2']     += float(r['avg_ayu2']     or 0)
        t['avg_personas'] += float(r['avg_personas'] or 0)
        t['dias']          = max(t['dias'], int(r['dias'] or 0))
        t['_n']           += 1

    def _row(anio, mes, suc):
        d = by_key.get((anio, mes, suc)) or {}
        return {
            'avg_salidas':  float(d.get('avg_salidas')  or 0),
            'avg_choferes': float(d.get('avg_choferes') or 0),
            'avg_ayu1':     float(d.get('avg_ayu1')     or 0),
            'avg_ayu2':     float(d.get('avg_ayu2')     or 0),
            'avg_personas': float(d.get('avg_personas') or 0),
            'dias':         int(d.get('dias')            or 0),
            'tiene_datos':  bool(d),
        }

    def _total_row(anio, mes):
        t = total_tmp.get((anio, mes), {})
        return {
            'avg_salidas':  round(float(t.get('avg_salidas')  or 0), 1),
            'avg_choferes': round(float(t.get('avg_choferes') or 0), 1),
            'avg_ayu1':     round(float(t.get('avg_ayu1')     or 0), 1),
            'avg_ayu2':     round(float(t.get('avg_ayu2')     or 0), 1),
            'avg_personas': round(float(t.get('avg_personas') or 0), 1),
            'dias':         int(t.get('dias')                  or 0),
            'tiene_datos':  bool(t),
        }

    meses = []
    for mes in range(1, 13):
        meses.append({
            'mes': mes,
            'nombre': NOMBRES_MES[mes - 1],
            anio: {
                'cc': _row(anio, mes, '1'),
                'dl': _row(anio, mes, '2'),
                'total': _total_row(anio, mes),
            },
            anio_base: {
                'cc': _row(anio_base, mes, '1'),
                'dl': _row(anio_base, mes, '2'),
                'total': _total_row(anio_base, mes),
            },
        })
    return {'anio': anio, 'anio_base': anio_base, 'meses': meses}


def get_comparativo_anual(sucursal: str, anio: int, anio_base: int) -> dict:
    """Comparativo año vs año base: KPIs de ventas + dotación + ausentismo."""
    ensure_ventas_detalle_table()
    ensure_articulos_table()
    ensure_rechazos_table()

    empresa_id = '1'
    ini = date(min(anio, anio_base), 1, 1)
    fin = date(max(anio, anio_base), 12, 31)
    swv = _suc_filter(sucursal, 'v')
    p = {'ini': ini, 'fin': fin, 's': sucursal}

    with pg_cursor() as cur:
        # KPIs mensuales de ventas (ambos años)
        cur.execute(f"""
            SELECT
                EXTRACT(YEAR  FROM v.fecha)::int AS anio,
                EXTRACT(MONTH FROM v.fecha)::int AS mes,
                SUM(COALESCE(v.bultos, 0))                                           AS b_tot,
                SUM(COALESCE(v.unidad_medida, 0))                                    AS hl_tot,
                COUNT(DISTINCT {V_CLIENT_KEY})                                        AS pdv_unicos,
                COUNT(DISTINCT {V_TRUCK_DAY_KEY})                                     AS salidas,
                COUNT(DISTINCT {V_PEDIDO_KEY})                                        AS p_tot,
                COUNT(DISTINCT CASE WHEN {V_IS_REC} THEN {V_PEDIDO_KEY} END)         AS p_rec,
                SUM(CASE WHEN {V_IS_REC} THEN COALESCE(v.bultos_rechazados,0) END)   AS b_rec,
                SUM(CASE WHEN {V_IS_REC} THEN COALESCE(v.unidad_medida_rechazado,0) END) AS hl_rec,
                COUNT(DISTINCT v.fecha)                                               AS dias_con_datos
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            {V_REC_JOIN}
            WHERE v.fecha BETWEEN %(ini)s AND %(fin)s {swv}
              AND {IS_MERCADERIA} AND {V_NOT_REMITO}
            GROUP BY 1, 2
            ORDER BY 1, 2
        """, p)
        ventas_rows = {(r['anio'], r['mes']): dict(r) for r in cur.fetchall()}

        # Días pico por mes (volume > monthly avg * 1.20)
        cur.execute(f"""
            WITH daily AS (
                SELECT EXTRACT(YEAR FROM v.fecha)::int  AS anio,
                       EXTRACT(MONTH FROM v.fecha)::int AS mes,
                       v.fecha,
                       SUM(COALESCE(v.bultos, 0)) AS b_dia
                FROM ventas_detalle v
                LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
                WHERE v.fecha BETWEEN %(ini)s AND %(fin)s {swv}
                  AND {IS_MERCADERIA} AND {V_NOT_REMITO}
                GROUP BY 1, 2, 3
            ),
            mavg AS (
                SELECT anio, mes, AVG(b_dia) AS avg_b FROM daily GROUP BY 1, 2
            )
            SELECT d.anio, d.mes, COUNT(*) AS dias_pico
            FROM daily d JOIN mavg m ON d.anio = m.anio AND d.mes = m.mes
            WHERE d.b_dia > m.avg_b * 1.20
            GROUP BY 1, 2
        """, p)
        picos_map = {(r['anio'], r['mes']): int(r['dias_pico']) for r in cur.fetchall()}

    # Dotación mensual
    dot = get_dotacion_mensual(empresa_id, anio, anio_base)
    dot_by_anio_mes = {(d['mes'], a): d[a] for d in dot['meses'] for a in (anio, anio_base)}

    # Ausentismo mensual — siempre busca 'TODAS' como fallback porque los datos
    # se cargan a nivel empresa, no por sucursal individual
    def _aus_dict(a):
        rows = get_ausentismo_mensual(empresa_id, sucursal, a)
        if not any(r['pct_ausentismo'] is not None for r in rows):
            rows = get_ausentismo_mensual(empresa_id, 'TODAS', a)
        return {r['mes']: r['pct_ausentismo'] for r in rows}

    aus_base   = _aus_dict(anio_base)
    aus_actual = _aus_dict(anio)

    today = date.today()

    def _build(a, mes) -> dict | None:
        v = ventas_rows.get((a, mes))
        if not v:
            return None
        b_tot  = float(v.get('b_tot')  or 0)
        hl_tot = float(v.get('hl_tot') or 0)
        p_tot  = int(v.get('p_tot')    or 0)
        p_rec  = int(v.get('p_rec')    or 0)
        b_rec  = float(v.get('b_rec')  or 0)
        hl_rec = float(v.get('hl_rec') or 0)
        dot_m  = dot_by_anio_mes.get((mes, a), {})
        return {
            'bultos':       round(b_tot,  0),
            'hl':           round(hl_tot, 1),
            'pdv_unicos':   int(v.get('pdv_unicos') or 0),
            'salidas':      int(v.get('salidas')    or 0),
            'p_tot':        p_tot,
            'pct_rec_hl':   round(hl_rec / hl_tot * 100, 2) if hl_tot else 0,
            'pct_rec_blt':  round(b_rec  / b_tot  * 100, 2) if b_tot  else 0,
            'pct_rec_pdv':  round(p_rec  / p_tot  * 100, 2) if p_tot  else 0,
            'nds':          round((p_tot - p_rec) / p_tot * 100, 1) if p_tot else 100.0,
            'dias_pico':    picos_map.get((a, mes), 0),
            'dias':         int(v.get('dias_con_datos') or 0),
            'ausentismo':   (aus_base if a == anio_base else aus_actual).get(mes),
            'dotacion': {
                'cc':    dot_m.get('cc',    {}),
                'dl':    dot_m.get('dl',    {}),
                'total': dot_m.get('total', {}),
            },
        }

    meses = []
    for mes in range(1, 13):
        if anio == today.year:
            es_futuro = mes > today.month
        else:
            es_futuro = anio > today.year

        actual = _build(anio, mes)
        base   = _build(anio_base, mes)

        meses.append({
            'mes':       mes,
            'nombre':    NOMBRES_MES[mes - 1],
            'es_futuro': es_futuro,
            'actual':    actual,
            'base':      base,
            'delta_hl':  round((actual['hl'] - base['hl']) / base['hl'] * 100, 1)
                         if actual and base and base['hl'] else None,
        })

    return {
        'sucursal':  sucursal,
        'anio':      anio,
        'anio_base': anio_base,
        'meses':     meses,
    }
