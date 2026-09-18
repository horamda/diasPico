"""Pedidos registrados en el detalle de repartos, sin cruces heurísticos."""
import hashlib
import json
import unicodedata

from app.database import pg_cursor


def _normalizar(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).upper().split())


def _estado(estados):
    normalized = {_normalizar(e) for e in estados}
    if not normalized or not normalized <= {'ENTREGADO', 'RECHAZADO', 'EN TRANSITO', 'PARCIAL'}:
        return 'sin_determinar'
    if 'EN TRANSITO' in normalized:
        return 'en_transito'
    if 'PARCIAL' in normalized or normalized == {'ENTREGADO', 'RECHAZADO'}:
        return 'parcial'
    return 'completa' if normalized == {'ENTREGADO'} else 'rechazada'


def get_pedidos(*, desde, hasta, sucursal, limit, offset):
    params = dict(desde=desde, hasta=hasta, sucursal=sucursal, limit=limit, offset=offset)
    with pg_cursor() as cur:
        cur.execute("""
            WITH base AS (
                SELECT d.*,
                    NULLIF(TRIM(sucursal), '') AS sucursal_id,
                    CASE WHEN nro_pedido > 0 THEN 'pedido:' || nro_pedido::text
                         WHEN NULLIF(TRIM(comprobante), '') IS NOT NULL
                         THEN 'comprobante:' || TRIM(comprobante)
                         ELSE 'fila:' || id::text END AS referencia
                FROM repartos_detalle d
                WHERE fecha_entrega_planilla BETWEEN %(desde)s AND %(hasta)s
                  AND (%(sucursal)s = 'TODAS' OR TRIM(sucursal) = %(sucursal)s)
            ), agrupados AS (
                SELECT referencia, sucursal_id, id_cliente::text AS cliente_id,
                    fecha_entrega_planilla AS fecha_entrega,
                    MAX(nombre_cliente) AS cliente_nombre,
                    MAX(nro_pedido) FILTER (WHERE nro_pedido > 0)::text AS numero_pedido,
                    COUNT(*) AS lineas_origen,
                    JSONB_AGG(DISTINCT estado) AS estados_origen,
                    COALESCE(JSONB_AGG(DISTINCT TRIM(comprobante))
                        FILTER (WHERE NULLIF(TRIM(comprobante), '') IS NOT NULL), '[]') AS comprobantes,
                    COALESCE(JSONB_AGG(DISTINCT nro_planilla::text)
                        FILTER (WHERE nro_planilla IS NOT NULL), '[]') AS planillas,
                    COALESCE(JSONB_AGG(DISTINCT ruta_venta)
                        FILTER (WHERE NULLIF(TRIM(ruta_venta), '') IS NOT NULL), '[]') AS rutas_venta,
                    COALESCE(JSONB_AGG(DISTINCT ruta_distribucion)
                        FILTER (WHERE NULLIF(TRIM(ruta_distribucion), '') IS NOT NULL), '[]') AS rutas_distribucion,
                    JSONB_AGG(JSONB_BUILD_OBJECT(
                        'id_origen', id::text, 'comprobante', comprobante,
                        'articulo_id', id_articulo, 'estado', estado,
                        'bultos', bultos, 'cantidad_um', cantidad_um,
                        'unidad_medida', unidad_medida, 'cantidad_up', cantidad_up,
                        'motivo_rechazo', motivo_rechazo, 'hora_entrega', hora_entrega,
                        'numero_planilla', nro_planilla::text,
                        'ruta_venta', ruta_venta, 'ruta_distribucion', ruta_distribucion
                    ) ORDER BY id) AS detalle
                FROM base
                GROUP BY referencia, sucursal_id, id_cliente, fecha_entrega_planilla
            )
            SELECT (SELECT COUNT(*) FROM agrupados) AS total,
                COALESCE((SELECT JSONB_AGG(TO_JSONB(p)
                    ORDER BY fecha_entrega, sucursal_id, cliente_id, referencia)
                    FROM (SELECT * FROM agrupados
                          ORDER BY fecha_entrega, sucursal_id, cliente_id, referencia
                          LIMIT %(limit)s OFFSET %(offset)s) p), '[]') AS datos,
                (SELECT MAX(fecha_entrega_planilla) FROM repartos_detalle
                 WHERE %(sucursal)s = 'TODAS' OR TRIM(sucursal) = %(sucursal)s) AS ultima_fecha_disponible
        """, params)
        result = dict(cur.fetchone())
    for row in result['datos']:
        identity = [row['sucursal_id'], row['cliente_id'], row['fecha_entrega'], row['referencia']]
        row['id_integracion'] = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
        row['tipo_identificador'] = row.pop('referencia').split(':', 1)[0]
        row['estado_entrega'] = _estado(row['estados_origen'])
        row['fuente_estado'] = 'repartos_detalle.estado'
        row['fuente_fecha_entrega'] = 'repartos_detalle.fecha_entrega_planilla'
        row['vinculo_foxtrot'] = {
            'numero_pedido': row['numero_pedido'],
            'comprobantes': sorted(row.pop('comprobantes')),
            'planillas': sorted(row.pop('planillas')),
            'rutas_venta': sorted(row.pop('rutas_venta')),
            'rutas_distribucion': sorted(row.pop('rutas_distribucion')),
        }
        row['comprobantes'] = row['vinculo_foxtrot']['comprobantes']
        row['calidad'] = {
            'cliente_identificado': row['cliente_id'] is not None,
            'sucursal_identificada': row['sucursal_id'] is not None,
            'pedido_o_comprobante_identificado': row['tipo_identificador'] != 'fila',
            'multiples_planillas': len(row['vinculo_foxtrot']['planillas']) > 1,
            'estado_determinado': row['estado_entrega'] != 'sin_determinar',
        }
    fecha = result['ultima_fecha_disponible']
    result['ultima_fecha_disponible'] = fecha.isoformat() if fecha else None
    return result
