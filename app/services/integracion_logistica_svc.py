from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app.database import pg_cursor
from app.repositories.flota_repository import ensure_tables as ensure_flota_tables
from app.services.articulos_svc import ensure_articulos_table
from app.services.sucursales_svc import listar as listar_sucursales
from app.services.transportes_svc import ensure_transportes_table
from app.services.ventas_svc import ensure_ventas_detalle_table


_SIN_CAMION = "SIN_TRANSPORTE"
_SIN_CHOFER = "SIN_CHOFER"


def _base_cte(incluir_clientes: bool) -> str:
    clientes_detalle = """
        JSONB_AGG(DISTINCT JSONB_BUILD_OBJECT(
            'id', cliente_id,
            'nombre', cliente_nombre
        )) FILTER (WHERE cliente_id IS NOT NULL) AS clientes_detalle,
    """ if incluir_clientes else "NULL::jsonb AS clientes_detalle,"

    return f"""
        WITH base AS (
            SELECT
                v.fecha::date AS fecha,
                COALESCE(NULLIF(TRIM(v.empresa), ''), '1') AS empresa_id,
                COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') AS sucursal_id,
                COALESCE(NULLIF(TRIM(v.transporte), ''), '{_SIN_CAMION}') AS camion_codigo,
                COALESCE(
                    NULLIF(TRIM(v.descripcion_transporte), ''),
                    NULLIF(TRIM(v.descripcion_detallada_transporte), ''),
                    NULLIF(TRIM(v.transporte), ''),
                    'Sin transporte'
                ) AS camion_descripcion,
                COALESCE(NULLIF(TRIM(v.chofer), ''), '{_SIN_CHOFER}') AS chofer_codigo,
                COALESCE(
                    NULLIF(TRIM(v.descripcion_chofer), ''),
                    NULLIF(TRIM(v.descripcion_detallada_chofer), ''),
                    NULLIF(TRIM(v.chofer), ''),
                    'Sin chofer'
                ) AS chofer_nombre,
                NULLIF(TRIM(v.cliente), '') AS cliente_id,
                COALESCE(
                    NULLIF(TRIM(v.descripcion_cliente), ''),
                    NULLIF(TRIM(v.descripcion_detallada_cliente), ''),
                    NULLIF(TRIM(v.cliente), ''),
                    'Sin nombre'
                ) AS cliente_nombre,
                COALESCE(
                    NULLIF(TRIM(v.detalle_documento), ''),
                    NULLIF(CONCAT_WS(
                        '-',
                        NULLIF(TRIM(v.documento), ''),
                        NULLIF(TRIM(v.serie), ''),
                        NULLIF(TRIM(v.numero), '')
                    ), ''),
                    v.id::text
                ) AS documento_key,
                v.id_articulo,
                COALESCE(v.bultos, 0) AS bultos,
                COALESCE(v.unidad_medida, 0) AS hl,
                COALESCE(v.unidad_paquete, 0) AS up,
                COALESCE(a.bultos_por_pallet, 0) AS bultos_por_pallet
            FROM ventas_detalle v
            LEFT JOIN articulos a ON a.id_articulo = v.id_articulo
            WHERE v.fecha BETWEEN %(desde)s AND %(hasta)s
              AND COALESCE(NULLIF(TRIM(v.empresa), ''), '1') = %(empresa_id)s
              AND (%(sucursal)s = 'TODAS' OR COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') = %(sucursal)s)
              AND LOWER(TRIM(COALESCE(a.tipo_producto, ''))) = 'mercaderia'
              AND LOWER(TRIM(COALESCE(v.documento, ''))) NOT LIKE 'remit%%'
              AND LOWER(TRIM(COALESCE(v.documento, ''))) NOT LIKE 'comod%%'
              AND LOWER(TRIM(COALESCE(v.detalle_documento, ''))) NOT LIKE 'remit%%'
              AND LOWER(TRIM(COALESCE(v.detalle_documento, ''))) NOT LIKE 'comod%%'
        ),
        agregados AS (
            SELECT
                fecha,
                empresa_id,
                sucursal_id,
                camion_codigo,
                MAX(camion_descripcion) AS camion_descripcion,
                chofer_codigo,
                MAX(chofer_nombre) AS chofer_nombre,
                COUNT(DISTINCT cliente_id) AS clientes,
                COUNT(DISTINCT documento_key) AS documentos,
                COALESCE(SUM(bultos), 0) AS bultos,
                COALESCE(SUM(hl), 0) AS hl,
                COALESCE(SUM(up), 0) AS up,
                COALESCE(SUM(
                    CASE WHEN bultos_por_pallet > 0 THEN bultos / bultos_por_pallet ELSE 0 END
                ), 0) AS pallets_estimados,
                COUNT(DISTINCT id_articulo) FILTER (
                    WHERE bultos > 0 AND bultos_por_pallet <= 0
                ) AS articulos_sin_configuracion_pallet,
                COALESCE(SUM(
                    CASE WHEN bultos_por_pallet <= 0 THEN bultos ELSE 0 END
                ), 0) AS bultos_sin_conversion_pallet,
                {clientes_detalle}
                COUNT(*) AS lineas_origen
            FROM base
            GROUP BY fecha, empresa_id, sucursal_id, camion_codigo, chofer_codigo
        )
    """


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        value = float(value)
    return round(float(value), 4)


def _to_int(value: Any) -> int:
    return int(value or 0)


def _fecha_iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _sucursal_labels(empresa_id: str) -> dict[str, str]:
    try:
        return {
            str(row["id"]): str(row["nombre"])
            for row in listar_sucursales(empresa_id=empresa_id)
        }
    except Exception:
        return {"1": "Casa Central", "2": "Dolores"}


def _clientes_detalle(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    by_id: dict[str, dict] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        cliente_id = str(item.get("id") or "").strip()
        if not cliente_id:
            continue
        by_id[cliente_id] = {
            "id": cliente_id,
            "nombre": str(item.get("nombre") or cliente_id),
        }
    return sorted(by_id.values(), key=lambda item: (item["nombre"].casefold(), item["id"]))


def _format_row(row: dict, labels: dict[str, str], incluir_clientes: bool) -> dict:
    camion_codigo = str(row.get("camion_codigo") or "").strip()
    chofer_codigo = str(row.get("chofer_codigo") or "").strip()
    sucursal_id = str(row.get("sucursal_id") or "")
    articulos_sin_pallet = _to_int(row.get("articulos_sin_configuracion_pallet"))
    bultos_sin_pallet = _to_float(row.get("bultos_sin_conversion_pallet"))

    item = {
        "fecha": _fecha_iso(row.get("fecha")),
        "empresa_id": str(row.get("empresa_id") or "1"),
        "sucursal_id": sucursal_id,
        "sucursal": labels.get(sucursal_id, sucursal_id),
        "camion_codigo": None if camion_codigo == _SIN_CAMION else camion_codigo,
        "camion_descripcion": str(
            row.get("camion_descripcion_final")
            or row.get("camion_descripcion")
            or "Sin transporte"
        ),
        "patente": row.get("patente"),
        "marca": row.get("marca"),
        "modelo": row.get("modelo"),
        "carga_maxima_kg": _to_float(row.get("carga_maxima_kg")),
        "capacidad_up": _to_float(row.get("capacidad_up")),
        "camion_en_maestro_flota": bool(row.get("camion_en_maestro_flota")),
        "chofer_codigo": None if chofer_codigo == _SIN_CHOFER else chofer_codigo,
        "chofer": str(row.get("chofer_nombre") or "Sin chofer"),
        "clientes": _to_int(row.get("clientes")),
        "documentos": _to_int(row.get("documentos")),
        "bultos": _to_float(row.get("bultos")),
        "hl": _to_float(row.get("hl")),
        "pallets_estimados": _to_float(row.get("pallets_estimados")),
        "up": _to_float(row.get("up")),
        "lineas_origen": _to_int(row.get("lineas_origen")),
        "calidad": {
            "pallets_completos": articulos_sin_pallet == 0,
            "articulos_sin_configuracion_pallet": articulos_sin_pallet,
            "bultos_sin_conversion_pallet": bultos_sin_pallet,
            "camion_identificado": camion_codigo != _SIN_CAMION,
            "chofer_identificado": chofer_codigo != _SIN_CHOFER,
        },
    }
    if incluir_clientes:
        item["clientes_detalle"] = _clientes_detalle(row.get("clientes_detalle"))
    return item


def get_logistica_diaria(
    *,
    empresa_id: str,
    sucursal: str,
    desde: date,
    hasta: date,
    incluir_clientes: bool,
    limit: int,
    offset: int,
) -> dict:
    ensure_ventas_detalle_table()
    ensure_articulos_table()
    ensure_transportes_table()
    ensure_flota_tables()

    params = {
        "empresa_id": empresa_id,
        "sucursal": sucursal,
        "desde": desde,
        "hasta": hasta,
        "limit": limit,
        "offset": offset,
    }

    count_sql = _base_cte(False) + """
        SELECT
            COUNT(*) AS total,
            MIN(fecha) AS fecha_min,
            MAX(fecha) AS fecha_max
        FROM agregados
    """
    data_sql = _base_cte(incluir_clientes) + """
        SELECT
            a.*,
            COALESCE(NULLIF(f.descripcion, ''), NULLIF(t.descripcion, ''), a.camion_descripcion) AS camion_descripcion_final,
            COALESCE(NULLIF(f.placa, ''), NULLIF(t.placa, '')) AS patente,
            COALESCE(NULLIF(f.marca, ''), NULLIF(t.marca, '')) AS marca,
            COALESCE(NULLIF(f.modelo, ''), NULLIF(t.modelo, '')) AS modelo,
            COALESCE(f.carga_maxima_kg, t.carga_maxima_kg, 0) AS carga_maxima_kg,
            COALESCE(f.capacidad_up, t.capacidad_up, 0) AS capacidad_up,
            (f.id IS NOT NULL OR t.codigo IS NOT NULL) AS camion_en_maestro_flota
        FROM agregados a
        LEFT JOIN flota_vehiculos f
          ON f.empresa_id = a.empresa_id
         AND f.codigo = a.camion_codigo
         AND f.anulado = FALSE
        LEFT JOIN transportes t ON t.codigo::text = a.camion_codigo
        ORDER BY a.fecha, a.sucursal_id, a.camion_codigo, a.chofer_codigo
        LIMIT %(limit)s OFFSET %(offset)s
    """

    with pg_cursor() as cur:
        cur.execute(count_sql, params)
        coverage = dict(cur.fetchone() or {})
        cur.execute(data_sql, params)
        rows = [dict(row) for row in cur.fetchall()]

    labels = _sucursal_labels(empresa_id)
    datos = [_format_row(row, labels, incluir_clientes) for row in rows]
    total = _to_int(coverage.get("total"))
    return {
        "total": total,
        "fecha_min": _fecha_iso(coverage.get("fecha_min")),
        "fecha_max": _fecha_iso(coverage.get("fecha_max")),
        "datos": datos,
    }
