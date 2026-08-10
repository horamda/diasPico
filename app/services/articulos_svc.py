from __future__ import annotations

import calendar as cal_mod
from datetime import date

from app.database import pg_conn, pg_cursor
from app.services.ventas_svc import ensure_ventas_detalle_table

_ARTICULOS_READY = False


def ensure_articulos_table() -> None:
    global _ARTICULOS_READY
    if _ARTICULOS_READY:
        return
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS articulos (
                    id_articulo         INTEGER PRIMARY KEY,
                    descripcion         VARCHAR(255),
                    activo              VARCHAR(10),
                    bultos_por_pallet   DECIMAL(10,4),
                    pisos               DECIMAL(10,4),
                    apilabilidad         DECIMAL(10,4),
                    bultos_por_piso     DECIMAL(10,4),
                    presentacion_bulto  INTEGER,
                    unidades_por_bulto  DECIMAL(10,4),
                    unidad_medida       VARCHAR(50),
                    desc_unidad_medida  VARCHAR(100),
                    valor_unidad_medida DECIMAL(10,4),
                    peso                DECIMAL(10,4),
                    alcoholico          VARCHAR(10),
                    division            VARCHAR(100),
                    familia             VARCHAR(100),
                    marca               VARCHAR(100),
                    tipo_producto       VARCHAR(100),
                    unidad_negocio      VARCHAR(100),
                    rotacion_abc        VARCHAR(5),
                    grupos_productos    VARCHAR(100),
                    activo_cc           VARCHAR(10),
                    activo_dolores      VARCHAR(10),
                    movil               VARCHAR(20),
                    anulado             VARCHAR(20),
                    actualizado         TIMESTAMP DEFAULT NOW()
                );
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS bultos_por_pallet DECIMAL(10,4);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS pisos DECIMAL(10,4);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS apilabilidad DECIMAL(10,4);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS bultos_por_piso DECIMAL(10,4);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS presentacion_bulto INTEGER;
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS unidades_por_bulto DECIMAL(10,4);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS desc_unidad_medida VARCHAR(100);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS valor_unidad_medida DECIMAL(10,4);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS peso DECIMAL(10,4);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS alcoholico VARCHAR(10);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS division VARCHAR(100);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS familia VARCHAR(100);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS marca VARCHAR(100);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS tipo_producto VARCHAR(100);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS unidad_negocio VARCHAR(100);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS rotacion_abc VARCHAR(5);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS grupos_productos VARCHAR(100);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS activo_cc VARCHAR(10);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS activo_dolores VARCHAR(10);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS movil VARCHAR(20);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS anulado VARCHAR(20);
                ALTER TABLE articulos ADD COLUMN IF NOT EXISTS actualizado TIMESTAMP DEFAULT NOW();
            """)
    _ARTICULOS_READY = True


def get_count() -> int:
    with pg_cursor(dict_cursor=False) as cur:
        cur.execute("SELECT COUNT(*) FROM articulos")
        return int(cur.fetchone()[0])


def _rango_mes(mes: str | None) -> tuple[str, date, date]:
    if not mes:
        today = date.today()
        y, m = today.year, today.month
    else:
        y, m = int(mes.split('-')[0]), int(mes.split('-')[1])
    return f"{y}-{m:02d}", date(y, m, 1), date(y, m, cal_mod.monthrange(y, m)[1])


def get_sin_clasificar(mes: str | None = None, sucursal: str = 'TODAS', limit: int = 20) -> dict:
    ensure_ventas_detalle_table()
    mes_label, ini, fin = _rango_mes(mes)
    params = {'ini': ini, 'fin': fin, 's': sucursal, 'limit': max(1, min(int(limit or 20), 100))}
    suc_filter = "AND COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') = %(s)s" if sucursal != 'TODAS' else ""

    base_where = f"""
        v.fecha BETWEEN %(ini)s AND %(fin)s
        {suc_filter}
        AND v.id_articulo IS NOT NULL
        AND a.id_articulo IS NULL
        AND LOWER(TRIM(COALESCE(v.documento, ''))) NOT LIKE '%%remit%%'
        AND LOWER(TRIM(COALESCE(v.documento, ''))) NOT LIKE '%%comod%%'
        AND LOWER(TRIM(COALESCE(v.detalle_documento, ''))) NOT LIKE '%%remit%%'
        AND LOWER(TRIM(COALESCE(v.detalle_documento, ''))) NOT LIKE '%%comod%%'
    """

    document_key = (
        "COALESCE("
        "NULLIF(TRIM(v.detalle_documento), ''), "
        "NULLIF(CONCAT_WS('-', NULLIF(TRIM(v.documento), ''), NULLIF(TRIM(v.serie), ''), NULLIF(TRIM(v.numero), '')), ''), "
        "v.id::text"
        ")"
    )
    cliente_key = f"COALESCE(NULLIF(TRIM(v.cliente), ''), NULLIF(TRIM(v.descripcion_cliente), ''), {document_key})"
    pedido_key = f"v.fecha::text || '|' || {cliente_key}"

    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT
                COUNT(*) AS filas,
                COUNT(DISTINCT v.id_articulo) AS articulos,
                COALESCE(SUM(v.bultos), 0) AS bultos,
                COALESCE(SUM(v.unidad_medida), 0) AS hectolitros,
                COUNT(DISTINCT {pedido_key}) AS pedidos
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            WHERE {base_where}
        """, params)
        total = dict(cur.fetchone() or {})

        cur.execute(f"""
            SELECT
                v.id_articulo,
                MAX(v.descripcion_articulo) AS descripcion_articulo,
                COUNT(*) AS filas,
                COALESCE(SUM(v.bultos), 0) AS bultos,
                COALESCE(SUM(v.unidad_medida), 0) AS hectolitros,
                COUNT(DISTINCT {pedido_key}) AS pedidos
            FROM ventas_detalle v
            LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
            WHERE {base_where}
            GROUP BY v.id_articulo
            ORDER BY filas DESC, bultos DESC
            LIMIT %(limit)s
        """, params)
        top = []
        for r in cur.fetchall():
            top.append({
                'id_articulo': r['id_articulo'],
                'descripcion_articulo': r['descripcion_articulo'],
                'filas': int(r.get('filas') or 0),
                'bultos': round(float(r.get('bultos') or 0), 1),
                'hectolitros': round(float(r.get('hectolitros') or 0), 1),
                'pedidos': int(r.get('pedidos') or 0),
            })

    return {
        'mes': mes_label,
        'sucursal': sucursal,
        'filas': int(total.get('filas') or 0),
        'articulos': int(total.get('articulos') or 0),
        'bultos': round(float(total.get('bultos') or 0), 1),
        'hectolitros': round(float(total.get('hectolitros') or 0), 1),
        'pedidos': int(total.get('pedidos') or 0),
        'top': top,
    }
