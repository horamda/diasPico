"""
Dropsize metrics for logistics dashboards.

Business rules match the main peak-day panel:
- Source table: ventas_detalle.
- Volume is total dispatched volume, including rejected rows.
- COMOD/REMIT documents are always excluded.
- Only articulos.tipo_producto = mercaderia is included.
- A drop is a delivered customer-day at branch grain:
  empresa + sucursal + fecha + cliente.
"""

from __future__ import annotations

import calendar as cal_mod
import json
from datetime import date, timedelta
from decimal import Decimal

from app.database import pg_conn, pg_cursor
from app.services.ventas_svc import ensure_ventas_detalle_table
from app.services.pico_svc import (
    IS_MERCADERIA,
    SUCURSAL_LABELS,
    V_NOT_REMITO,
    V_PALLETS_EXPR,
    _rango_mes,
    _suc_filter,
    get_params,
)

UNIDADES = {'bultos', 'hl', 'pallets'}
METRICAS_PICO = {'bultos', 'hl', 'pallets', 'clientes', 'todos'}
AGRUPACIONES = {'sucursal', 'segmento', 'localidad', 'canal', 'vendedor', 'ruta', 'chofer'}
_DROPSIZE_TABLES_READY = False


def _normalize_agrupacion(value: str | None) -> str:
    key = str(value or 'sucursal').strip().lower()
    return key if key in AGRUPACIONES else 'sucursal'


def _agrupacion_label(agrupacion: str) -> str:
    return {
        'sucursal': 'Sucursal',
        'segmento': 'Segmento',
        'localidad': 'Localidad',
        'canal': 'Canal',
        'vendedor': 'Vendedor',
        'ruta': 'Ruta',
        'chofer': 'Chofer',
    }.get(agrupacion, 'Sucursal')


def _delivery_key(alias: str = 'v') -> str:
    empresa = f"COALESCE(NULLIF(TRIM({alias}.empresa), ''), '1')"
    sucursal = f"COALESCE(NULLIF(TRIM({alias}.sucursal), ''), '1')"
    cliente = f"NULLIF(TRIM({alias}.cliente), '')"
    return f"{empresa} || '|' || {sucursal} || '|' || {alias}.fecha::text || '|' || {cliente}"


def _agrupacion_expr(agrupacion: str, alias: str = 'v') -> tuple[str, str, str]:
    agr = _normalize_agrupacion(agrupacion)
    if agr == 'segmento':
        expr = (
            "COALESCE("
            "ch.canal_descripcion, "
            "NULLIF(TRIM(v.descripcion_canal), ''), "
            "NULLIF(TRIM(v.descripcion_detallada_canal), ''), "
            "NULLIF(TRIM(cli.subcanal), ''), "
            "NULLIF(TRIM(v.canal), ''), "
            "'Sin segmento'"
            ")"
        )
        join_sql = """
            LEFT JOIN clientes cli
              ON cli.cliente = v.cliente
             AND COALESCE(NULLIF(TRIM(cli.sucursal), ''), '1') = COALESCE(NULLIF(TRIM(v.sucursal), ''), '1')
            LEFT JOIN canales ch
              ON ch.cliente = v.cliente
             AND ch.sucursal_id = COALESCE(NULLIF(TRIM(v.sucursal), ''), '1')
        """
        cte_sql = """
            canal_raw AS (
                SELECT
                    NULLIF(TRIM(v.cliente), '') AS cliente,
                    COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') AS sucursal_id,
                    COALESCE(
                        NULLIF(TRIM(v.descripcion_canal), ''),
                        NULLIF(TRIM(v.descripcion_detallada_canal), ''),
                        NULLIF(TRIM(v.canal), ''),
                        'Sin segmento'
                    ) AS canal_descripcion,
                    SUM(COALESCE(v.importe_neto, 0)) AS venta_canal
                FROM ventas_detalle v
                WHERE v.fecha BETWEEN %(ini)s AND %(fin)s
                  AND NULLIF(TRIM(v.cliente), '') IS NOT NULL
                GROUP BY 1, 2, 3
            ),
            canales AS (
                SELECT DISTINCT ON (cliente, sucursal_id)
                       cliente,
                       sucursal_id,
                       canal_descripcion
                FROM canal_raw
                ORDER BY cliente, sucursal_id, venta_canal DESC NULLS LAST, canal_descripcion
            )
        """
        return expr, join_sql, cte_sql
    if agr == 'localidad':
        expr = "COALESCE(NULLIF(TRIM(cli.localidad), ''), 'Sin localidad')"
        join_sql = """
            LEFT JOIN clientes cli
              ON cli.cliente = v.cliente
             AND COALESCE(NULLIF(TRIM(cli.sucursal), ''), '1') = COALESCE(NULLIF(TRIM(v.sucursal), ''), '1')
        """
        return expr, join_sql, ""
    if agr == 'canal':
        expr = (
            "COALESCE("
            "ch.canal_descripcion, "
            "NULLIF(TRIM(v.descripcion_canal), ''), "
            "NULLIF(TRIM(v.descripcion_detallada_canal), ''), "
            "NULLIF(TRIM(v.canal), ''), "
            "'Sin canal'"
            ")"
        )
        join_sql = """
            LEFT JOIN canales ch
              ON ch.cliente = v.cliente
             AND ch.sucursal_id = COALESCE(NULLIF(TRIM(v.sucursal), ''), '1')
        """
        cte_sql = """
            canal_raw AS (
                SELECT
                    NULLIF(TRIM(v.cliente), '') AS cliente,
                    COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') AS sucursal_id,
                    COALESCE(
                        NULLIF(TRIM(v.descripcion_canal), ''),
                        NULLIF(TRIM(v.descripcion_detallada_canal), ''),
                        NULLIF(TRIM(v.canal), ''),
                        'Sin canal'
                    ) AS canal_descripcion,
                    SUM(COALESCE(v.importe_neto, 0)) AS venta_canal
                FROM ventas_detalle v
                WHERE v.fecha BETWEEN %(ini)s AND %(fin)s
                  AND NULLIF(TRIM(v.cliente), '') IS NOT NULL
                GROUP BY 1, 2, 3
            ),
            canales AS (
                SELECT DISTINCT ON (cliente, sucursal_id)
                       cliente,
                       sucursal_id,
                       canal_descripcion
                FROM canal_raw
                ORDER BY cliente, sucursal_id, venta_canal DESC NULLS LAST, canal_descripcion
            )
        """
        return expr, join_sql, cte_sql
    if agr == 'vendedor':
        return (
            "COALESCE(NULLIF(TRIM(v.descripcion_vendedor), ''), NULLIF(TRIM(v.vendedor), ''), 'Sin vendedor')",
            "",
            "",
        )
    if agr == 'ruta':
        return (
            "COALESCE(NULLIF(TRIM(v.descripcion_ruta), ''), NULLIF(TRIM(v.ruta), ''), 'Sin ruta')",
            "",
            "",
        )
    if agr == 'chofer':
        return (
            "COALESCE(NULLIF(TRIM(v.descripcion_chofer), ''), NULLIF(TRIM(v.chofer), ''), 'Sin chofer')",
            "",
            "",
        )
    return ("COALESCE(NULLIF(TRIM(v.sucursal), ''), '1')", "", "")


DROPSIZE_OBJETIVOS_DDL = """
CREATE TABLE IF NOT EXISTS dropsize_objetivos (
    id BIGSERIAL PRIMARY KEY,
    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50),
    unidad VARCHAR(20) NOT NULL CHECK (unidad IN ('bultos', 'hl', 'pallets')),
    objetivo_minimo NUMERIC(14,4) NOT NULL,
    objetivo_ideal NUMERIC(14,4) NOT NULL,
    fecha_desde DATE NOT NULL,
    fecha_hasta DATE,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""


DROPSIZE_HISTORICO_DDL = """
CREATE TABLE IF NOT EXISTS dropsize_historico (
    id BIGSERIAL PRIMARY KEY,
    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50) NOT NULL,
    fecha DATE NOT NULL,
    periodo_mes SMALLINT NOT NULL,
    periodo_anio SMALLINT NOT NULL,
    clientes_entregados INTEGER NOT NULL DEFAULT 0,
    total_bultos NUMERIC(18,4) NOT NULL DEFAULT 0,
    total_hl NUMERIC(18,4) NOT NULL DEFAULT 0,
    total_pallets NUMERIC(18,4) NOT NULL DEFAULT 0,
    dropsize_bultos NUMERIC(18,4) NOT NULL DEFAULT 0,
    dropsize_hl NUMERIC(18,4) NOT NULL DEFAULT 0,
    dropsize_pallets NUMERIC(18,4) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, sucursal_id, fecha)
)
"""


def ensure_dropsize_tables(ensure_source: bool = False) -> None:
    global _DROPSIZE_TABLES_READY
    if ensure_source:
        ensure_ventas_detalle_table()
    if _DROPSIZE_TABLES_READY:
        return
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                {DROPSIZE_OBJETIVOS_DDL};
                {DROPSIZE_HISTORICO_DDL};
                CREATE INDEX IF NOT EXISTS idx_dropsize_obj_suc_unidad ON dropsize_objetivos(sucursal_id, unidad, activo);
                CREATE INDEX IF NOT EXISTS idx_dropsize_obj_fechas ON dropsize_objetivos(fecha_desde, fecha_hasta);
                CREATE INDEX IF NOT EXISTS idx_dropsize_hist_fecha ON dropsize_historico(fecha);
                CREATE INDEX IF NOT EXISTS idx_dropsize_hist_suc_fecha ON dropsize_historico(sucursal_id, fecha);
                CREATE INDEX IF NOT EXISTS idx_dropsize_hist_empresa ON dropsize_historico(empresa_id);
            """)
    _DROPSIZE_TABLES_READY = True


def _to_float(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _to_int(value) -> int:
    return int(value or 0)


def _round(value, digits: int = 2) -> float:
    return round(_to_float(value), digits)


def _safe_div(num, den) -> float:
    den_f = _to_float(den)
    return round(_to_float(num) / den_f, 4) if den_f else 0.0


def _pct_var(actual, base) -> float | None:
    base_f = _to_float(base)
    if not base_f:
        return None
    return round((_to_float(actual) - base_f) / base_f * 100, 2)


def _add_months(d: date, delta: int) -> date:
    month_idx = d.month - 1 + delta
    year = d.year + month_idx // 12
    month = month_idx % 12 + 1
    day = min(d.day, cal_mod.monthrange(year, month)[1])
    return date(year, month, day)


def _month_bounds(mes: str | None) -> tuple[date, date]:
    if not mes:
        today = date.today()
        return _rango_mes(today.year, today.month)
    y, m = (int(x) for x in mes.split('-', 1))
    return _rango_mes(y, m)


def _period_bounds(
    fecha_desde: str | date | None = None,
    fecha_hasta: str | date | None = None,
    mes: str | None = None,
) -> tuple[date, date]:
    if fecha_desde and fecha_hasta:
        ini = fecha_desde if isinstance(fecha_desde, date) else date.fromisoformat(str(fecha_desde))
        fin = fecha_hasta if isinstance(fecha_hasta, date) else date.fromisoformat(str(fecha_hasta))
        return ini, fin
    return _month_bounds(mes)


def _base_params(sucursal: str, ini: date, fin: date) -> dict:
    return {'ini': ini, 'fin': fin, 's': sucursal}


def _source_where(sucursal: str, alias: str = 'v') -> str:
    return f"""
        {alias}.fecha BETWEEN %(ini)s AND %(fin)s
        {_suc_filter(sucursal, alias)}
        AND {V_NOT_REMITO}
        AND {IS_MERCADERIA}
        AND NULLIF(TRIM(COALESCE({alias}.cliente, '')), '') IS NOT NULL
    """


def _format_summary(row: dict | None, fecha_desde: date | None = None, fecha_hasta: date | None = None) -> dict:
    row = row or {}
    clientes = _to_int(row.get('clientes_entregados'))
    total_bultos = _round(row.get('total_bultos'))
    total_hl = _round(row.get('total_hl'))
    total_pallets = _round(row.get('total_pallets'))
    return {
        'fecha_desde': fecha_desde.isoformat() if fecha_desde else None,
        'fecha_hasta': fecha_hasta.isoformat() if fecha_hasta else None,
        'clientes_entregados': clientes,
        'entregas_consolidadas': clientes,
        'total_bultos': total_bultos,
        'total_hl': total_hl,
        'total_pallets': total_pallets,
        'dropsize_bultos': _safe_div(total_bultos, clientes),
        'dropsize_hl': _safe_div(total_hl, clientes),
        'dropsize_pallets': _safe_div(total_pallets, clientes),
    }


def _aggregate_source(sucursal: str, ini: date, fin: date) -> dict:
    ensure_dropsize_tables(ensure_source=True)
    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT
                COUNT(DISTINCT {_delivery_key()}) AS clientes_entregados,
                COALESCE(SUM(COALESCE(v.bultos, 0)), 0) AS total_bultos,
                COALESCE(SUM(COALESCE(v.unidad_medida, 0)), 0) AS total_hl,
                COALESCE(SUM({V_PALLETS_EXPR}), 0) AS total_pallets
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            WHERE {_source_where(sucursal)}
        """, _base_params(sucursal, ini, fin))
        return _format_summary(cur.fetchone(), ini, fin)


def _hist_where(sucursal: str) -> str:
    return "AND sucursal_id = %(s)s" if sucursal != 'TODAS' else ""


def _aggregate_historico(sucursal: str, ini: date, fin: date) -> dict | None:
    ensure_dropsize_tables()
    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT
                COUNT(*) AS rows_count,
                COALESCE(SUM(clientes_entregados), 0) AS clientes_entregados,
                COALESCE(SUM(total_bultos), 0) AS total_bultos,
                COALESCE(SUM(total_hl), 0) AS total_hl,
                COALESCE(SUM(total_pallets), 0) AS total_pallets
            FROM dropsize_historico
            WHERE fecha BETWEEN %(ini)s AND %(fin)s
            {_hist_where(sucursal)}
        """, _base_params(sucursal, ini, fin))
        row = cur.fetchone()
    if not row or _to_int(row.get('rows_count')) == 0:
        return None
    return _format_summary(row, ini, fin)


def _aggregate(sucursal: str, ini: date, fin: date) -> dict:
    return _aggregate_historico(sucursal, ini, fin) or _aggregate_source(sucursal, ini, fin)


def _resumen_historico_con_objetivos(sucursal: str, ini: date, fin: date) -> dict | None:
    ensure_dropsize_tables()
    sucursal_id = None if sucursal == 'TODAS' else sucursal
    params = {'ini': ini, 'fin': fin, 's': sucursal, 'sucursal_obj': sucursal_id}
    with pg_cursor() as cur:
        cur.execute(f"""
            WITH agg AS (
                SELECT
                    COUNT(*) AS rows_count,
                    COALESCE(SUM(clientes_entregados), 0) AS clientes_entregados,
                    COALESCE(SUM(total_bultos), 0) AS total_bultos,
                    COALESCE(SUM(total_hl), 0) AS total_hl,
                    COALESCE(SUM(total_pallets), 0) AS total_pallets
                FROM dropsize_historico
                WHERE fecha BETWEEN %(ini)s AND %(fin)s
                {_hist_where(sucursal)}
            ),
            obj AS (
                SELECT DISTINCT ON (unidad)
                       unidad,
                       jsonb_build_object(
                           'id', id,
                           'empresa_id', empresa_id,
                           'sucursal_id', sucursal_id,
                           'unidad', unidad,
                           'objetivo_minimo', objetivo_minimo,
                           'objetivo_ideal', objetivo_ideal,
                           'fecha_desde', fecha_desde::text,
                           'fecha_hasta', fecha_hasta::text,
                           'activo', activo
                       ) AS data
                FROM dropsize_objetivos
                WHERE activo = TRUE
                  AND unidad = ANY(%(unidades)s)
                  AND fecha_desde <= %(fin)s
                  AND (fecha_hasta IS NULL OR fecha_hasta >= %(fin)s)
                  AND (sucursal_id IS NULL OR sucursal_id = %(sucursal_obj)s)
                ORDER BY unidad, (sucursal_id = %(sucursal_obj)s) DESC, fecha_desde DESC, id DESC
            ),
            obj_json AS (
                SELECT COALESCE(jsonb_object_agg(unidad, data), '{{}}'::jsonb) AS objetivos
                FROM obj
            )
            SELECT agg.*, obj_json.objetivos
            FROM agg CROSS JOIN obj_json
        """, {**params, 'unidades': ['bultos', 'hl', 'pallets']})
        row = cur.fetchone()
    if not row or _to_int(row.get('rows_count')) == 0:
        return None

    resumen = _format_summary(row, ini, fin)
    objetivos_raw = row.get('objetivos') or {}
    if isinstance(objetivos_raw, str):
        objetivos_raw = json.loads(objetivos_raw)
    resumen['objetivos'] = {
        unidad: _semaforo(resumen.get(f'dropsize_{unidad}', 0), objetivos_raw.get(unidad))
        for unidad in ('bultos', 'hl', 'pallets')
    }
    return resumen


def _evolucion_diaria_historico(sucursal: str, ini: date, fin: date) -> dict | None:
    ensure_dropsize_tables()
    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT
                fecha,
                SUM(clientes_entregados) AS clientes_entregados,
                SUM(total_bultos) AS total_bultos,
                SUM(total_hl) AS total_hl,
                SUM(total_pallets) AS total_pallets
            FROM dropsize_historico
            WHERE fecha BETWEEN %(ini)s AND %(fin)s
            {_hist_where(sucursal)}
            GROUP BY fecha
            ORDER BY fecha
        """, _base_params(sucursal, ini, fin))
        rows = cur.fetchall()
    if not rows:
        return None
    dias = []
    for r in rows:
        item = _format_summary(r, r['fecha'], r['fecha'])
        item['fecha'] = r['fecha'].isoformat()
        dias.append(item)
    return {'fecha_desde': ini.isoformat(), 'fecha_hasta': fin.isoformat(), 'dias': dias}


def _evolucion_mensual_historico(sucursal: str, ini: date, fin: date) -> dict | None:
    ensure_dropsize_tables()
    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT
                TO_CHAR(DATE_TRUNC('month', fecha), 'YYYY-MM') AS mes,
                SUM(clientes_entregados) AS clientes_entregados,
                SUM(total_bultos) AS total_bultos,
                SUM(total_hl) AS total_hl,
                SUM(total_pallets) AS total_pallets
            FROM dropsize_historico
            WHERE fecha BETWEEN %(ini)s AND %(fin)s
            {_hist_where(sucursal)}
            GROUP BY DATE_TRUNC('month', fecha)
            ORDER BY DATE_TRUNC('month', fecha)
        """, _base_params(sucursal, ini, fin))
        rows = cur.fetchall()
    if not rows:
        return None
    result = []
    for r in rows:
        item = _format_summary(r)
        item['mes'] = r['mes']
        result.append(item)
    return {'fecha_desde': ini.isoformat(), 'fecha_hasta': fin.isoformat(), 'meses': result}


def _ranking_historico(ini: date, fin: date, unidad: str, sucursal: str = 'TODAS') -> dict | None:
    ensure_dropsize_tables()
    params = _base_params(sucursal, ini, fin)
    where = f"fecha BETWEEN %(ini)s AND %(fin)s {_hist_where(sucursal)}"
    with pg_cursor() as cur:
        cur.execute("""
            SELECT
                sucursal_id,
                SUM(clientes_entregados) AS clientes_entregados,
                SUM(total_bultos) AS total_bultos,
                SUM(total_hl) AS total_hl,
                SUM(total_pallets) AS total_pallets
            FROM dropsize_historico
            WHERE """ + where + """
            GROUP BY sucursal_id
        """, params)
        rows = cur.fetchall()
    if not rows:
        return None
    ranking = []
    for r in rows:
        item = _format_summary(r)
        item['grupo_id'] = r['sucursal_id']
        item['grupo'] = SUCURSAL_LABELS.get(r['sucursal_id'], r['sucursal_id'])
        item['sucursal_id'] = r['sucursal_id']
        item['sucursal'] = item['grupo']
        ranking.append(item)
    ranking.sort(key=lambda x: x.get(f'dropsize_{unidad}', 0), reverse=True)
    for i, item in enumerate(ranking, 1):
        item['ranking'] = i
    return {
        'fecha_desde': ini.isoformat(),
        'fecha_hasta': fin.isoformat(),
        'unidad': unidad,
        'agrupacion': 'sucursal',
        'agrupacion_label': _agrupacion_label('sucursal'),
        'ranking': ranking,
    }


def _ranking_source(ini: date, fin: date, unidad: str, agrupacion: str, sucursal: str = 'TODAS') -> dict | None:
    agrupacion = _normalize_agrupacion(agrupacion)
    expr, join_sql, cte_sql = _agrupacion_expr(agrupacion)
    ensure_dropsize_tables(ensure_source=True)
    params = _base_params(sucursal, ini, fin)
    with pg_cursor() as cur:
        cur.execute(f"""
            {f'WITH {cte_sql}' if cte_sql else ''}
            SELECT
                {expr} AS grupo_id,
                COUNT(DISTINCT {_delivery_key()}) AS clientes_entregados,
                COALESCE(SUM(COALESCE(v.bultos, 0)), 0) AS total_bultos,
                COALESCE(SUM(COALESCE(v.unidad_medida, 0)), 0) AS total_hl,
                COALESCE(SUM({V_PALLETS_EXPR}), 0) AS total_pallets
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            {join_sql}
            WHERE {_source_where(sucursal)}
            GROUP BY {expr}
        """, params)
        rows = cur.fetchall()
    if not rows:
        return None

    ranking = []
    for r in rows:
        item = _format_summary(r)
        grupo_id = str(r.get('grupo_id') or '')
        item['grupo_id'] = grupo_id
        item['grupo'] = SUCURSAL_LABELS.get(grupo_id, grupo_id) if agrupacion == 'sucursal' else grupo_id
        item['sucursal_id'] = grupo_id if agrupacion == 'sucursal' else None
        item['sucursal'] = item['grupo']
        ranking.append(item)
    ranking.sort(key=lambda x: x.get(f'dropsize_{unidad}', 0), reverse=True)
    for i, item in enumerate(ranking, 1):
        item['ranking'] = i
    return {
        'fecha_desde': ini.isoformat(),
        'fecha_hasta': fin.isoformat(),
        'unidad': unidad,
        'agrupacion': agrupacion,
        'agrupacion_label': _agrupacion_label(agrupacion),
        'ranking': ranking,
    }


def _comparativo_historico(
    sucursal: str,
    ini: date,
    fin: date,
    prev_ini: date,
    prev_fin: date,
    aa_ini: date,
    aa_fin: date,
) -> dict[str, dict] | None:
    ensure_dropsize_tables()
    params = {
        'ini': ini,
        'fin': fin,
        'prev_ini': prev_ini,
        'prev_fin': prev_fin,
        'aa_ini': aa_ini,
        'aa_fin': aa_fin,
        's': sucursal,
    }
    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT
                periodo,
                SUM(clientes_entregados) AS clientes_entregados,
                SUM(total_bultos) AS total_bultos,
                SUM(total_hl) AS total_hl,
                SUM(total_pallets) AS total_pallets
            FROM (
                SELECT
                    CASE
                        WHEN fecha BETWEEN %(ini)s AND %(fin)s THEN 'actual'
                        WHEN fecha BETWEEN %(prev_ini)s AND %(prev_fin)s THEN 'previo'
                        WHEN fecha BETWEEN %(aa_ini)s AND %(aa_fin)s THEN 'anio_anterior'
                    END AS periodo,
                    clientes_entregados,
                    total_bultos,
                    total_hl,
                    total_pallets
                FROM dropsize_historico
                WHERE (
                    fecha BETWEEN %(ini)s AND %(fin)s
                    OR fecha BETWEEN %(prev_ini)s AND %(prev_fin)s
                    OR fecha BETWEEN %(aa_ini)s AND %(aa_fin)s
                )
                {_hist_where(sucursal)}
            ) x
            WHERE periodo IS NOT NULL
            GROUP BY periodo
        """, params)
        rows = cur.fetchall()
    if not rows:
        return None
    return {r['periodo']: _format_summary(r) for r in rows}


def _objetivo_dict(row) -> dict:
    return {
        'id': row['id'],
        'empresa_id': row['empresa_id'],
        'sucursal_id': row['sucursal_id'],
        'unidad': row['unidad'],
        'objetivo_minimo': _round(row['objetivo_minimo'], 4),
        'objetivo_ideal': _round(row['objetivo_ideal'], 4),
        'fecha_desde': row['fecha_desde'].isoformat(),
        'fecha_hasta': row['fecha_hasta'].isoformat() if row['fecha_hasta'] else None,
        'activo': bool(row['activo']),
    }


def _objetivos_para(unidades: tuple[str, ...], sucursal: str, fecha_ref: date) -> dict[str, dict]:
    ensure_dropsize_tables()
    sucursal_id = None if sucursal == 'TODAS' else sucursal
    with pg_cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (unidad)
                   id, empresa_id, sucursal_id, unidad, objetivo_minimo, objetivo_ideal,
                   fecha_desde, fecha_hasta, activo
            FROM dropsize_objetivos
            WHERE activo = TRUE
              AND unidad = ANY(%(unidades)s)
              AND fecha_desde <= %(fecha)s
              AND (fecha_hasta IS NULL OR fecha_hasta >= %(fecha)s)
              AND (sucursal_id IS NULL OR sucursal_id = %(sucursal)s)
            ORDER BY unidad, (sucursal_id = %(sucursal)s) DESC, fecha_desde DESC, id DESC
        """, {'unidades': list(unidades), 'sucursal': sucursal_id, 'fecha': fecha_ref})
        rows = cur.fetchall()
    return {r['unidad']: _objetivo_dict(r) for r in rows}


def _objetivo_para(unidad: str, sucursal: str, fecha_ref: date) -> dict | None:
    with pg_cursor() as cur:
        cur.execute("""
            SELECT id, empresa_id, sucursal_id, unidad, objetivo_minimo, objetivo_ideal,
                   fecha_desde, fecha_hasta, activo
            FROM dropsize_objetivos
            WHERE activo = TRUE
              AND unidad = %(unidad)s
              AND fecha_desde <= %(fecha)s
              AND (fecha_hasta IS NULL OR fecha_hasta >= %(fecha)s)
              AND (sucursal_id IS NULL OR sucursal_id = %(sucursal)s)
            ORDER BY (sucursal_id = %(sucursal)s) DESC, fecha_desde DESC, id DESC
            LIMIT 1
        """, {'unidad': unidad, 'sucursal': None if sucursal == 'TODAS' else sucursal, 'fecha': fecha_ref})
        row = cur.fetchone()
    if not row:
        return None
    return _objetivo_dict(row)


def _semaforo(valor: float, objetivo: dict | None) -> dict:
    if not objetivo:
        return {'estado': 'sin_objetivo', 'label': 'Sin objetivo', 'objetivo': None}
    minimo = _to_float(objetivo['objetivo_minimo'])
    ideal = _to_float(objetivo['objetivo_ideal'])
    if valor >= ideal:
        estado = 'verde'
    elif valor >= minimo:
        estado = 'amarillo'
    else:
        estado = 'rojo'
    return {'estado': estado, 'label': estado.capitalize(), 'objetivo': objetivo}


def _attach_objetivos(resumen: dict, sucursal: str, fecha_ref: date) -> dict:
    objetivos_cfg = _objetivos_para(('bultos', 'hl', 'pallets'), sucursal, fecha_ref)
    objetivos = {}
    for unidad in ('bultos', 'hl', 'pallets'):
        valor = resumen.get(f'dropsize_{unidad}', 0)
        objetivos[unidad] = _semaforo(valor, objetivos_cfg.get(unidad))
    resumen['objetivos'] = objetivos
    return resumen


def get_resumen(sucursal: str, fecha_desde: str | None = None, fecha_hasta: str | None = None, mes: str | None = None) -> dict:
    ini, fin = _period_bounds(fecha_desde, fecha_hasta, mes)
    resumen = _resumen_historico_con_objetivos(sucursal, ini, fin)
    if resumen:
        return resumen
    resumen = _aggregate_source(sucursal, ini, fin)
    return _attach_objetivos(resumen, sucursal, fin)


def get_evolucion_diaria(sucursal: str, fecha_desde: str | None = None, fecha_hasta: str | None = None, mes: str | None = None) -> dict:
    ini, fin = _period_bounds(fecha_desde, fecha_hasta, mes)
    historico = _evolucion_diaria_historico(sucursal, ini, fin)
    if historico:
        return historico
    ensure_dropsize_tables(ensure_source=True)
    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT
                v.fecha::date AS fecha,
                COUNT(DISTINCT {_delivery_key()}) AS clientes_entregados,
                COALESCE(SUM(COALESCE(v.bultos, 0)), 0) AS total_bultos,
                COALESCE(SUM(COALESCE(v.unidad_medida, 0)), 0) AS total_hl,
                COALESCE(SUM({V_PALLETS_EXPR}), 0) AS total_pallets
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            WHERE {_source_where(sucursal)}
            GROUP BY v.fecha::date
            ORDER BY v.fecha::date
        """, _base_params(sucursal, ini, fin))
        rows = cur.fetchall()
    dias = []
    for r in rows:
        item = _format_summary(r, r['fecha'], r['fecha'])
        item['fecha'] = r['fecha'].isoformat()
        dias.append(item)
    return {'fecha_desde': ini.isoformat(), 'fecha_hasta': fin.isoformat(), 'dias': dias}


def get_evolucion_mensual(sucursal: str, meses: int = 12, mes_hasta: str | None = None) -> dict:
    meses = max(1, min(int(meses or 12), 60))
    hasta_ini, hasta_fin = _month_bounds(mes_hasta)
    ini = _add_months(hasta_ini, -(meses - 1))
    fin = hasta_fin
    historico = _evolucion_mensual_historico(sucursal, ini, fin)
    if historico:
        return historico
    ensure_dropsize_tables(ensure_source=True)
    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT
                TO_CHAR(DATE_TRUNC('month', v.fecha), 'YYYY-MM') AS mes,
                COUNT(DISTINCT {_delivery_key()}) AS clientes_entregados,
                COALESCE(SUM(COALESCE(v.bultos, 0)), 0) AS total_bultos,
                COALESCE(SUM(COALESCE(v.unidad_medida, 0)), 0) AS total_hl,
                COALESCE(SUM({V_PALLETS_EXPR}), 0) AS total_pallets
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            WHERE {_source_where(sucursal)}
            GROUP BY DATE_TRUNC('month', v.fecha)
            ORDER BY DATE_TRUNC('month', v.fecha)
        """, _base_params(sucursal, ini, fin))
        rows = cur.fetchall()
    result = []
    for r in rows:
        item = _format_summary(r)
        item['mes'] = r['mes']
        result.append(item)
    return {'fecha_desde': ini.isoformat(), 'fecha_hasta': fin.isoformat(), 'meses': result}


def get_ranking_sucursales(
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    mes: str | None = None,
    unidad: str = 'bultos',
    agrupacion: str = 'sucursal',
    sucursal: str = 'TODAS',
) -> dict:
    ini, fin = _period_bounds(fecha_desde, fecha_hasta, mes)
    unidad = unidad if unidad in UNIDADES else 'bultos'
    agrupacion = _normalize_agrupacion(agrupacion)
    historico = _ranking_historico(ini, fin, unidad, sucursal) if agrupacion == 'sucursal' else None
    if historico:
        return historico
    return _ranking_source(ini, fin, unidad, agrupacion, sucursal)


def _comparar(actual: dict, base: dict) -> dict:
    keys = [
        'clientes_entregados', 'total_bultos', 'total_hl', 'total_pallets',
        'dropsize_bultos', 'dropsize_hl', 'dropsize_pallets',
    ]
    return {k: _pct_var(actual.get(k), base.get(k)) for k in keys}


def get_comparativo(
    sucursal: str,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    mes: str | None = None,
) -> dict:
    ini, fin = _period_bounds(fecha_desde, fecha_hasta, mes)
    span_days = (fin - ini).days + 1
    prev_fin = ini - timedelta(days=1)
    prev_ini = prev_fin - timedelta(days=span_days - 1)
    aa_ini = _add_months(ini, -12)
    aa_fin = aa_ini + timedelta(days=span_days - 1)
    historico = _comparativo_historico(sucursal, ini, fin, prev_ini, prev_fin, aa_ini, aa_fin) or {}
    actual = historico.get('actual') or _aggregate(sucursal, ini, fin)
    previo = historico.get('previo') or _aggregate(sucursal, prev_ini, prev_fin)
    anio_anterior = historico.get('anio_anterior') or _aggregate(sucursal, aa_ini, aa_fin)
    return {
        'actual': actual,
        'periodo_actual': {
            'fecha_desde': ini.isoformat(),
            'fecha_hasta': fin.isoformat(),
            'dias': span_days,
        },
        'mes_anterior': {
            'periodo': f'{prev_ini.isoformat()} a {prev_fin.isoformat()}',
            'fecha_desde': prev_ini.isoformat(),
            'fecha_hasta': prev_fin.isoformat(),
            'resumen': previo,
            'variacion_pct': _comparar(actual, previo),
        },
        'anio_anterior': {
            'periodo': f'{aa_ini.isoformat()} a {aa_fin.isoformat()}',
            'fecha_desde': aa_ini.isoformat(),
            'fecha_hasta': aa_fin.isoformat(),
            'resumen': anio_anterior,
            'variacion_pct': _comparar(actual, anio_anterior),
        },
    }


def get_dias_pico(
    sucursal: str,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    mes: str | None = None,
    metrica: str = 'todos',
    umbral: float | None = None,
) -> dict:
    metrica = metrica if metrica in METRICAS_PICO else 'todos'
    data = get_evolucion_diaria(sucursal, fecha_desde, fecha_hasta, mes)
    dias = data['dias']
    params = get_params(sucursal)
    factor = float(umbral if umbral is not None else params.get('umbral_pct', 1.20))
    metric_keys = {
        'bultos': 'total_bultos',
        'hl': 'total_hl',
        'pallets': 'total_pallets',
        'clientes': 'clientes_entregados',
    }
    selected = metric_keys if metrica == 'todos' else {metrica: metric_keys[metrica]}
    promedios = {}
    umbrales = {}
    for name, key in selected.items():
        vals = [_to_float(d.get(key)) for d in dias if _to_float(d.get(key)) > 0]
        avg = round(sum(vals) / len(vals), 4) if vals else 0.0
        promedios[name] = avg
        umbrales[name] = round(avg * factor, 4)
    picos = []
    for d in dias:
        motivos = []
        for name, key in selected.items():
            if umbrales[name] > 0 and _to_float(d.get(key)) >= umbrales[name]:
                motivos.append(name)
        if motivos:
            row = dict(d)
            row['motivos'] = motivos
            picos.append(row)
    return {
        'fecha_desde': data['fecha_desde'],
        'fecha_hasta': data['fecha_hasta'],
        'metrica': metrica,
        'umbral_factor': factor,
        'promedios': promedios,
        'umbrales': umbrales,
        'dias': picos,
    }


def list_objetivos(sucursal: str | None = None) -> list[dict]:
    ensure_dropsize_tables()
    params = {}
    where = ""
    if sucursal and sucursal != 'TODAS':
        where = "WHERE sucursal_id IS NULL OR sucursal_id = %(s)s"
        params['s'] = sucursal
    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT id, empresa_id, sucursal_id, unidad, objetivo_minimo, objetivo_ideal,
                   fecha_desde, fecha_hasta, activo, created_at, updated_at
            FROM dropsize_objetivos
            {where}
            ORDER BY activo DESC, unidad, sucursal_id NULLS FIRST, fecha_desde DESC, id DESC
        """, params)
        rows = cur.fetchall()
    return [{
        'id': r['id'],
        'empresa_id': r['empresa_id'],
        'sucursal_id': r['sucursal_id'],
        'sucursal': SUCURSAL_LABELS.get(r['sucursal_id'], 'Todas') if r['sucursal_id'] else 'Todas',
        'unidad': r['unidad'],
        'objetivo_minimo': _round(r['objetivo_minimo'], 4),
        'objetivo_ideal': _round(r['objetivo_ideal'], 4),
        'fecha_desde': r['fecha_desde'].isoformat(),
        'fecha_hasta': r['fecha_hasta'].isoformat() if r['fecha_hasta'] else None,
        'activo': bool(r['activo']),
    } for r in rows]


def save_objetivo(data: dict) -> dict:
    ensure_dropsize_tables()
    unidad = str(data.get('unidad', 'bultos')).lower()
    if unidad not in UNIDADES:
        raise ValueError('unidad invalida')
    objetivo_minimo = float(data.get('objetivo_minimo', 0))
    objetivo_ideal = float(data.get('objetivo_ideal', 0))
    if objetivo_minimo < 0 or objetivo_ideal < 0:
        raise ValueError('los objetivos no pueden ser negativos')
    if objetivo_ideal < objetivo_minimo:
        raise ValueError('objetivo_ideal debe ser mayor o igual al objetivo_minimo')
    fecha_desde = date.fromisoformat(str(data.get('fecha_desde') or date.today().isoformat()))
    fecha_hasta_raw = data.get('fecha_hasta') or None
    fecha_hasta = date.fromisoformat(str(fecha_hasta_raw)) if fecha_hasta_raw else None
    if fecha_hasta and fecha_hasta < fecha_desde:
        raise ValueError('fecha_hasta debe ser mayor o igual a fecha_desde')
    sucursal = data.get('sucursal_id') or data.get('sucursal')
    sucursal_id = None if not sucursal or sucursal == 'TODAS' else str(sucursal)
    empresa_id = str(data.get('empresa_id') or '1')
    activo = bool(data.get('activo', True))
    objetivo_id = data.get('id')
    with pg_cursor() as cur:
        if objetivo_id:
            cur.execute("""
                UPDATE dropsize_objetivos
                SET empresa_id=%(empresa_id)s,
                    sucursal_id=%(sucursal_id)s,
                    unidad=%(unidad)s,
                    objetivo_minimo=%(objetivo_minimo)s,
                    objetivo_ideal=%(objetivo_ideal)s,
                    fecha_desde=%(fecha_desde)s,
                    fecha_hasta=%(fecha_hasta)s,
                    activo=%(activo)s,
                    updated_at=NOW()
                WHERE id=%(id)s
                RETURNING id
            """, {
                'id': objetivo_id, 'empresa_id': empresa_id, 'sucursal_id': sucursal_id,
                'unidad': unidad, 'objetivo_minimo': objetivo_minimo, 'objetivo_ideal': objetivo_ideal,
                'fecha_desde': fecha_desde, 'fecha_hasta': fecha_hasta, 'activo': activo,
            })
            row = cur.fetchone()
            if not row:
                raise ValueError('objetivo no encontrado')
            saved_id = row['id']
        else:
            cur.execute("""
                INSERT INTO dropsize_objetivos
                    (empresa_id, sucursal_id, unidad, objetivo_minimo, objetivo_ideal, fecha_desde, fecha_hasta, activo)
                VALUES
                    (%(empresa_id)s, %(sucursal_id)s, %(unidad)s, %(objetivo_minimo)s, %(objetivo_ideal)s, %(fecha_desde)s, %(fecha_hasta)s, %(activo)s)
                RETURNING id
            """, {
                'empresa_id': empresa_id, 'sucursal_id': sucursal_id, 'unidad': unidad,
                'objetivo_minimo': objetivo_minimo, 'objetivo_ideal': objetivo_ideal,
                'fecha_desde': fecha_desde, 'fecha_hasta': fecha_hasta, 'activo': activo,
            })
            saved_id = cur.fetchone()['id']
    return {'ok': True, 'id': saved_id}


def delete_objetivo(objetivo_id: int | str) -> dict:
    ensure_dropsize_tables()
    try:
        objetivo_id = int(objetivo_id)
    except (ValueError, TypeError):
        raise ValueError('ID de objetivo inválido')

    with pg_cursor() as cur:
        cur.execute("DELETE FROM dropsize_objetivos WHERE id = %s", (objetivo_id,))
        if cur.rowcount == 0:
            raise ValueError('Objetivo no encontrado')

    return {'ok': True, 'id': objetivo_id}


def recalcular_historico(sucursal: str = 'TODAS', fecha_desde: str | None = None, fecha_hasta: str | None = None, mes: str | None = None) -> dict:
    ini, fin = _period_bounds(fecha_desde, fecha_hasta, mes)
    ensure_dropsize_tables(ensure_source=True)
    p = _base_params(sucursal, ini, fin)
    delete_suc = "" if sucursal == 'TODAS' else "AND sucursal_id = %(s)s"
    with pg_cursor() as cur:
        cur.execute(f"""
            DELETE FROM dropsize_historico
            WHERE fecha BETWEEN %(ini)s AND %(fin)s
            {delete_suc}
        """, p)
        cur.execute(f"""
            INSERT INTO dropsize_historico (
                empresa_id, sucursal_id, fecha, periodo_mes, periodo_anio,
                clientes_entregados, total_bultos, total_hl, total_pallets,
                dropsize_bultos, dropsize_hl, dropsize_pallets, updated_at
            )
            SELECT
                COALESCE(NULLIF(TRIM(v.empresa), ''), '1') AS empresa_id,
                COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') AS sucursal_id,
                v.fecha::date AS fecha,
                EXTRACT(MONTH FROM v.fecha)::smallint AS periodo_mes,
                EXTRACT(YEAR FROM v.fecha)::smallint AS periodo_anio,
                COUNT(DISTINCT {_delivery_key()}) AS clientes_entregados,
                COALESCE(SUM(COALESCE(v.bultos, 0)), 0) AS total_bultos,
                COALESCE(SUM(COALESCE(v.unidad_medida, 0)), 0) AS total_hl,
                COALESCE(SUM({V_PALLETS_EXPR}), 0) AS total_pallets,
                COALESCE(SUM(COALESCE(v.bultos, 0)), 0) / NULLIF(COUNT(DISTINCT {_delivery_key()}), 0) AS dropsize_bultos,
                COALESCE(SUM(COALESCE(v.unidad_medida, 0)), 0) / NULLIF(COUNT(DISTINCT {_delivery_key()}), 0) AS dropsize_hl,
                COALESCE(SUM({V_PALLETS_EXPR}), 0) / NULLIF(COUNT(DISTINCT {_delivery_key()}), 0) AS dropsize_pallets,
                NOW() AS updated_at
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            WHERE {_source_where(sucursal)}
            GROUP BY
                COALESCE(NULLIF(TRIM(v.empresa), ''), '1'),
                COALESCE(NULLIF(TRIM(v.sucursal), ''), '1'),
                v.fecha::date
            ON CONFLICT (empresa_id, sucursal_id, fecha) DO UPDATE SET
                periodo_mes=EXCLUDED.periodo_mes,
                periodo_anio=EXCLUDED.periodo_anio,
                clientes_entregados=EXCLUDED.clientes_entregados,
                total_bultos=EXCLUDED.total_bultos,
                total_hl=EXCLUDED.total_hl,
                total_pallets=EXCLUDED.total_pallets,
                dropsize_bultos=EXCLUDED.dropsize_bultos,
                dropsize_hl=EXCLUDED.dropsize_hl,
                dropsize_pallets=EXCLUDED.dropsize_pallets,
                updated_at=NOW()
        """, p)
        affected = cur.rowcount
    return {'ok': True, 'fecha_desde': ini.isoformat(), 'fecha_hasta': fin.isoformat(), 'registros': affected}
