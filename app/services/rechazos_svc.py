from app.database import pg_conn, pg_cursor
from app.services.articulos_svc import ensure_articulos_table
from app.services.ventas_svc import ensure_ventas_detalle_table

_RECHAZOS_READY = False

IS_MERCADERIA = "LOWER(TRIM(COALESCE(a.tipo_producto,''))) = 'mercaderia'"
REC_JOIN = """
LEFT JOIN LATERAL (
    SELECT tomar, sector
    FROM rechazos r
    WHERE LOWER(TRIM(COALESCE(v.motivo_rechazo,''))) = r.motivo_key
       OR LOWER(TRIM(COALESCE(v.motivo_rechazo,''))) LIKE r.motivo_key || ' %%'
    ORDER BY LENGTH(r.motivo_key) DESC
    LIMIT 1
) rz ON TRUE
"""
DOC_CODE = "LOWER(TRIM(COALESCE(v.documento, '')))"
DOC_DETAIL = "LOWER(TRIM(COALESCE(v.detalle_documento, '')))"
IS_REC = (
    "(COALESCE(rz.tomar, FALSE) AND ("
    "COALESCE(v.bultos_rechazados, 0) > 0 "
    "OR COALESCE(v.unidad_medida_rechazado, 0) > 0 "
    "OR COALESCE(v.unidad_paquete_rechazado, 0) > 0"
    "))"
)
NOT_REMITO = (
    f"{DOC_CODE} NOT LIKE 'remit%%' "
    f"AND {DOC_CODE} NOT LIKE 'comod%%' "
    f"AND {DOC_DETAIL} NOT LIKE 'remit%%' "
    f"AND {DOC_DETAIL} NOT LIKE 'comod%%'"
)
PEDIDO_KEY = "v.fecha::text || '|' || NULLIF(TRIM(v.cliente), '')"
PALLETS_TOTAL_EXPR = "CASE WHEN COALESCE(a.bultos_por_pallet, 0) > 0 THEN COALESCE(v.bultos, 0) / a.bultos_por_pallet ELSE 0 END"
PALLETS_RECHAZO_EXPR = "CASE WHEN COALESCE(a.bultos_por_pallet, 0) > 0 THEN COALESCE(v.bultos_rechazados, 0) / a.bultos_por_pallet ELSE 0 END"


def _suc_filter(sucursal: str) -> str:
    return "AND COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') = %(sucursal)s" if sucursal != 'TODAS' else ""


def _num(value, digits: int = 2) -> float:
    return round(float(value or 0), digits)


def _base_payload(desde, hasta, sucursal: str, datos: list[dict], campos: list[str]) -> dict:
    return {
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'sucursal': sucursal,
        'total_filas': len(datos),
        'campos': campos,
        'datos': datos,
    }


DDL = """
CREATE TABLE IF NOT EXISTS rechazos (
    motivo_key      VARCHAR(255) PRIMARY KEY,
    motivo_rechazo  VARCHAR(255) NOT NULL,
    sector          VARCHAR(100),
    tomar           BOOLEAN NOT NULL DEFAULT FALSE,
    actualizado     TIMESTAMP DEFAULT NOW()
)
"""


def ensure_table() -> None:
    global _RECHAZOS_READY
    if _RECHAZOS_READY:
        return
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                {DDL};
                ALTER TABLE rechazos ADD COLUMN IF NOT EXISTS sector VARCHAR(100);
                CREATE INDEX IF NOT EXISTS idx_rechazos_tomar ON rechazos(tomar);
            """)
    _RECHAZOS_READY = True


def sync_from_detalle() -> dict:
    ensure_table()
    ensure_ventas_detalle_table()
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO rechazos (motivo_key, motivo_rechazo, sector, tomar)
                SELECT LOWER(TRIM(motivo_rechazo)) AS motivo_key,
                       MIN(TRIM(motivo_rechazo))   AS motivo_rechazo,
                       ''                           AS sector,
                       FALSE                       AS tomar
                FROM ventas_detalle
                WHERE motivo_rechazo IS NOT NULL
                  AND TRIM(motivo_rechazo) <> ''
                  AND LOWER(TRIM(COALESCE(documento, ''))) NOT LIKE '%remit%'
                  AND LOWER(TRIM(COALESCE(documento, ''))) NOT LIKE '%comod%'
                  AND LOWER(TRIM(COALESCE(detalle_documento, ''))) NOT LIKE '%remit%'
                  AND LOWER(TRIM(COALESCE(detalle_documento, ''))) NOT LIKE '%comod%'
                GROUP BY LOWER(TRIM(motivo_rechazo))
                ON CONFLICT (motivo_key) DO NOTHING
            """)
            inserted = cur.rowcount
    return {'inserted': inserted}


def list_rechazos() -> list[dict]:
    ensure_table()
    ensure_ventas_detalle_table()
    with pg_cursor() as cur:
        cur.execute("""
            SELECT
                r.motivo_key,
                r.motivo_rechazo,
                r.sector,
                r.tomar,
                COALESCE(x.filas, 0) AS filas,
                COALESCE(x.bultos, 0) AS bultos,
                r.actualizado
            FROM rechazos r
            LEFT JOIN (
                SELECT LOWER(TRIM(motivo_rechazo)) AS motivo_key,
                       COUNT(*) AS filas,
                       SUM(bultos_rechazados) AS bultos
                FROM ventas_detalle
                WHERE motivo_rechazo IS NOT NULL
                  AND TRIM(motivo_rechazo) <> ''
                  AND LOWER(TRIM(COALESCE(documento, ''))) NOT LIKE '%remit%'
                  AND LOWER(TRIM(COALESCE(documento, ''))) NOT LIKE '%comod%'
                  AND LOWER(TRIM(COALESCE(detalle_documento, ''))) NOT LIKE '%remit%'
                  AND LOWER(TRIM(COALESCE(detalle_documento, ''))) NOT LIKE '%comod%'
                GROUP BY LOWER(TRIM(motivo_rechazo))
            ) x ON x.motivo_key = r.motivo_key
            ORDER BY r.tomar DESC, r.motivo_rechazo
        """)
        return [dict(r) for r in cur.fetchall()]


def update_tomar(motivo_key: str, tomar: bool) -> dict:
    ensure_table()
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE rechazos SET tomar = %s, actualizado = NOW()
                WHERE motivo_key = %s
            """, (tomar, motivo_key))
            updated = cur.rowcount
    return {'updated': updated}


RESUMEN_DIARIO_CAMPOS = [
    'fecha',
    'sucursal',
    'pedidos',
    'pedidos_rechazo',
    'pct_rechazo_pedidos',
    'bultos',
    'bultos_rechazo',
    'pct_rechazo_bultos',
    'hl',
    'hl_rechazo',
    'pct_rechazo_hl',
    'pallets',
    'pallets_rechazo',
    'pct_rechazo_pallets',
]


DETALLE_DIARIO_CAMPOS = [
    'fecha',
    'sucursal',
    'chofer',
    'chofer_codigo',
    'sector',
    'motivo',
    'pedidos_rechazo',
    'ocurrencias',
    'bultos_rechazo',
    'hl_rechazo',
    'pallets_rechazo',
]


RECHAZOS_CLIENTE_CAMPOS = [
    'cliente',
    'descripcion_cliente',
    'sucursal',
    'pedidos_rechazo',
    'ocurrencias',
    'bultos_rechazo',
    'hl_rechazo',
    'pallets_rechazo',
    'motivos',
]


RECHAZOS_MOTIVO_CAMPOS = [
    'sector',
    'motivo',
    'pedidos_rechazo',
    'clientes_rechazo',
    'ocurrencias',
    'bultos_rechazo',
    'hl_rechazo',
    'pallets_rechazo',
]


def get_resumen_diario(desde, hasta, sucursal: str = 'TODAS') -> dict:
    if desde > hasta:
        raise ValueError('desde no puede ser posterior a hasta')
    ensure_table()
    ensure_ventas_detalle_table()
    ensure_articulos_table()
    sucursal = sucursal or 'TODAS'
    params = {'desde': desde, 'hasta': hasta, 'sucursal': sucursal}
    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT
                v.fecha::date AS fecha,
                COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') AS sucursal,
                COUNT(DISTINCT {PEDIDO_KEY}) AS pedidos,
                COUNT(DISTINCT CASE WHEN {IS_REC} THEN {PEDIDO_KEY} END) AS pedidos_rechazo,
                SUM(COALESCE(v.bultos, 0)) AS bultos,
                SUM(CASE WHEN {IS_REC} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS bultos_rechazo,
                SUM(COALESCE(v.unidad_medida, 0)) AS hl,
                SUM(CASE WHEN {IS_REC} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END) AS hl_rechazo,
                SUM({PALLETS_TOTAL_EXPR}) AS pallets,
                SUM(CASE WHEN {IS_REC} THEN {PALLETS_RECHAZO_EXPR} ELSE 0 END) AS pallets_rechazo
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            {REC_JOIN}
            WHERE v.fecha BETWEEN %(desde)s AND %(hasta)s
              {_suc_filter(sucursal)}
              AND {IS_MERCADERIA}
              AND {NOT_REMITO}
            GROUP BY v.fecha::date, COALESCE(NULLIF(TRIM(v.sucursal), ''), '1')
            ORDER BY v.fecha::date, sucursal
        """, params)
        rows = [dict(r) for r in cur.fetchall()]

    datos = []
    for r in rows:
        pedidos = int(r.get('pedidos') or 0)
        pedidos_rechazo = int(r.get('pedidos_rechazo') or 0)
        bultos = float(r.get('bultos') or 0)
        bultos_rechazo = float(r.get('bultos_rechazo') or 0)
        hl = float(r.get('hl') or 0)
        hl_rechazo = float(r.get('hl_rechazo') or 0)
        pallets = float(r.get('pallets') or 0)
        pallets_rechazo = float(r.get('pallets_rechazo') or 0)
        datos.append({
            'fecha': r['fecha'].isoformat(),
            'sucursal': r.get('sucursal') or '',
            'pedidos': pedidos,
            'pedidos_rechazo': pedidos_rechazo,
            'pct_rechazo_pedidos': round(pedidos_rechazo / pedidos * 100, 2) if pedidos else 0,
            'bultos': round(bultos, 2),
            'bultos_rechazo': round(bultos_rechazo, 2),
            'pct_rechazo_bultos': round(bultos_rechazo / bultos * 100, 2) if bultos else 0,
            'hl': round(hl, 4),
            'hl_rechazo': round(hl_rechazo, 4),
            'pct_rechazo_hl': round(hl_rechazo / hl * 100, 2) if hl else 0,
            'pallets': round(pallets, 4),
            'pallets_rechazo': round(pallets_rechazo, 4),
            'pct_rechazo_pallets': round(pallets_rechazo / pallets * 100, 2) if pallets else 0,
        })
    return _base_payload(desde, hasta, sucursal, datos, RESUMEN_DIARIO_CAMPOS)


def get_rechazos_por_cliente(desde, hasta, sucursal: str = 'TODAS', limit: int = 50) -> dict:
    if desde > hasta:
        raise ValueError('desde no puede ser posterior a hasta')
    ensure_table()
    ensure_ventas_detalle_table()
    ensure_articulos_table()
    sucursal = sucursal or 'TODAS'
    limit = max(1, min(int(limit or 50), 500))
    params = {'desde': desde, 'hasta': hasta, 'sucursal': sucursal, 'limit': limit}
    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT
                COALESCE(NULLIF(TRIM(v.cliente), ''), 'Sin cliente') AS cliente,
                COALESCE(NULLIF(TRIM(MAX(v.descripcion_cliente)), ''), NULLIF(TRIM(MAX(v.descripcion_detallada_cliente)), ''), '') AS descripcion_cliente,
                COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') AS sucursal,
                COUNT(DISTINCT CASE WHEN {IS_REC} THEN {PEDIDO_KEY} END) AS pedidos_rechazo,
                COUNT(*) AS ocurrencias,
                SUM(COALESCE(v.bultos_rechazados, 0)) AS bultos_rechazo,
                SUM(COALESCE(v.unidad_medida_rechazado, 0)) AS hl_rechazo,
                SUM({PALLETS_RECHAZO_EXPR}) AS pallets_rechazo,
                STRING_AGG(DISTINCT COALESCE(NULLIF(TRIM(v.motivo_rechazo), ''), 'Sin motivo'), ' | ' ORDER BY COALESCE(NULLIF(TRIM(v.motivo_rechazo), ''), 'Sin motivo')) AS motivos
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            {REC_JOIN}
            WHERE v.fecha BETWEEN %(desde)s AND %(hasta)s
              {_suc_filter(sucursal)}
              AND {IS_REC}
              AND {IS_MERCADERIA}
              AND {NOT_REMITO}
            GROUP BY
                COALESCE(NULLIF(TRIM(v.cliente), ''), 'Sin cliente'),
                COALESCE(NULLIF(TRIM(v.sucursal), ''), '1')
            ORDER BY bultos_rechazo DESC, hl_rechazo DESC, pedidos_rechazo DESC
            LIMIT %(limit)s
        """, params)
        rows = [dict(r) for r in cur.fetchall()]

    datos = [{
        'cliente': r.get('cliente') or 'Sin cliente',
        'descripcion_cliente': r.get('descripcion_cliente') or '',
        'sucursal': r.get('sucursal') or '',
        'pedidos_rechazo': int(r.get('pedidos_rechazo') or 0),
        'ocurrencias': int(r.get('ocurrencias') or 0),
        'bultos_rechazo': _num(r.get('bultos_rechazo'), 2),
        'hl_rechazo': _num(r.get('hl_rechazo'), 4),
        'pallets_rechazo': _num(r.get('pallets_rechazo'), 4),
        'motivos': r.get('motivos') or '',
    } for r in rows]
    return _base_payload(desde, hasta, sucursal, datos, RECHAZOS_CLIENTE_CAMPOS)


def get_rechazos_por_motivo(desde, hasta, sucursal: str = 'TODAS', limit: int = 50) -> dict:
    if desde > hasta:
        raise ValueError('desde no puede ser posterior a hasta')
    ensure_table()
    ensure_ventas_detalle_table()
    ensure_articulos_table()
    sucursal = sucursal or 'TODAS'
    limit = max(1, min(int(limit or 50), 500))
    params = {'desde': desde, 'hasta': hasta, 'sucursal': sucursal, 'limit': limit}
    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT
                COALESCE(rz.sector, 'Sin sector') AS sector,
                COALESCE(NULLIF(TRIM(v.motivo_rechazo), ''), 'Sin motivo') AS motivo,
                COUNT(DISTINCT CASE WHEN {IS_REC} THEN {PEDIDO_KEY} END) AS pedidos_rechazo,
                COUNT(DISTINCT NULLIF(TRIM(v.cliente), '')) AS clientes_rechazo,
                COUNT(*) AS ocurrencias,
                SUM(COALESCE(v.bultos_rechazados, 0)) AS bultos_rechazo,
                SUM(COALESCE(v.unidad_medida_rechazado, 0)) AS hl_rechazo,
                SUM({PALLETS_RECHAZO_EXPR}) AS pallets_rechazo
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            {REC_JOIN}
            WHERE v.fecha BETWEEN %(desde)s AND %(hasta)s
              {_suc_filter(sucursal)}
              AND {IS_REC}
              AND {IS_MERCADERIA}
              AND {NOT_REMITO}
            GROUP BY
                COALESCE(rz.sector, 'Sin sector'),
                COALESCE(NULLIF(TRIM(v.motivo_rechazo), ''), 'Sin motivo')
            ORDER BY bultos_rechazo DESC, hl_rechazo DESC, pedidos_rechazo DESC
            LIMIT %(limit)s
        """, params)
        rows = [dict(r) for r in cur.fetchall()]

    datos = [{
        'sector': r.get('sector') or 'Sin sector',
        'motivo': r.get('motivo') or 'Sin motivo',
        'pedidos_rechazo': int(r.get('pedidos_rechazo') or 0),
        'clientes_rechazo': int(r.get('clientes_rechazo') or 0),
        'ocurrencias': int(r.get('ocurrencias') or 0),
        'bultos_rechazo': _num(r.get('bultos_rechazo'), 2),
        'hl_rechazo': _num(r.get('hl_rechazo'), 4),
        'pallets_rechazo': _num(r.get('pallets_rechazo'), 4),
    } for r in rows]
    return _base_payload(desde, hasta, sucursal, datos, RECHAZOS_MOTIVO_CAMPOS)


def get_detalle_diario(desde, hasta, sucursal: str = 'TODAS') -> dict:
    if desde > hasta:
        raise ValueError('desde no puede ser posterior a hasta')
    ensure_table()
    ensure_ventas_detalle_table()
    ensure_articulos_table()
    sucursal = sucursal or 'TODAS'
    params = {'desde': desde, 'hasta': hasta, 'sucursal': sucursal}
    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT
                v.fecha::date AS fecha,
                COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') AS sucursal,
                COALESCE(NULLIF(TRIM(v.descripcion_chofer), ''), NULLIF(TRIM(v.descripcion_detallada_chofer), ''), NULLIF(TRIM(v.chofer), ''), 'Sin chofer') AS chofer,
                COALESCE(NULLIF(TRIM(v.chofer), ''), '') AS chofer_codigo,
                COALESCE(rz.sector, 'Sin sector') AS sector,
                COALESCE(NULLIF(TRIM(v.motivo_rechazo), ''), 'Sin motivo') AS motivo,
                COUNT(DISTINCT CASE WHEN {IS_REC} THEN {PEDIDO_KEY} END) AS pedidos_rechazo,
                COUNT(*) AS ocurrencias,
                SUM(COALESCE(v.bultos_rechazados, 0)) AS bultos_rechazo,
                SUM(COALESCE(v.unidad_medida_rechazado, 0)) AS hl_rechazo,
                SUM({PALLETS_RECHAZO_EXPR}) AS pallets_rechazo
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            {REC_JOIN}
            WHERE v.fecha BETWEEN %(desde)s AND %(hasta)s
              {_suc_filter(sucursal)}
              AND {IS_REC}
              AND {IS_MERCADERIA}
              AND {NOT_REMITO}
            GROUP BY
                v.fecha::date,
                COALESCE(NULLIF(TRIM(v.sucursal), ''), '1'),
                COALESCE(NULLIF(TRIM(v.descripcion_chofer), ''), NULLIF(TRIM(v.descripcion_detallada_chofer), ''), NULLIF(TRIM(v.chofer), ''), 'Sin chofer'),
                COALESCE(NULLIF(TRIM(v.chofer), ''), ''),
                COALESCE(rz.sector, 'Sin sector'),
                COALESCE(NULLIF(TRIM(v.motivo_rechazo), ''), 'Sin motivo')
            ORDER BY v.fecha::date, sucursal, bultos_rechazo DESC, hl_rechazo DESC
        """, params)
        rows = [dict(r) for r in cur.fetchall()]

    datos = [{
        'fecha': r['fecha'].isoformat(),
        'sucursal': r.get('sucursal') or '',
        'chofer': r.get('chofer') or 'Sin chofer',
        'chofer_codigo': r.get('chofer_codigo') or '',
        'sector': r.get('sector') or 'Sin sector',
        'motivo': r.get('motivo') or 'Sin motivo',
        'pedidos_rechazo': int(r.get('pedidos_rechazo') or 0),
        'ocurrencias': int(r.get('ocurrencias') or 0),
        'bultos_rechazo': _num(r.get('bultos_rechazo'), 2),
        'hl_rechazo': _num(r.get('hl_rechazo'), 4),
        'pallets_rechazo': _num(r.get('pallets_rechazo'), 4),
    } for r in rows]
    return _base_payload(desde, hasta, sucursal, datos, DETALLE_DIARIO_CAMPOS)


def get_integracion_diaria(desde, hasta, sucursal: str = 'TODAS') -> dict:
    return {
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'sucursal': sucursal or 'TODAS',
        'resumen_diario': get_resumen_diario(desde, hasta, sucursal).get('datos', []),
        'detalle_diario': get_detalle_diario(desde, hasta, sucursal).get('datos', []),
    }
