"""Rechazos por cliente y fecha para cruces externos, sin inferir OTIF."""
from app.database import pg_cursor
from app.services import rechazos_svc as rec


def get_clientes_diario(*, empresa_id, sucursal, desde, hasta, limit, offset):
    rec.ensure_table()
    rec.ensure_ventas_detalle_table()
    rec.ensure_articulos_table()
    params = dict(empresa_id=empresa_id, sucursal=sucursal, desde=desde,
                  hasta=hasta, limit=limit, offset=offset)
    # Se mantiene el alcance de mercadería del dashboard. Los rechazos físicos
    # y los seleccionados por configuración se exponen por separado.
    sql = f"""
        WITH base AS (
            SELECT v.*, rz.tomar, rz.sector,
                COALESCE(NULLIF(TRIM(v.cliente), ''), '') AS cliente_id,
                COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') AS sucursal_id,
                (COALESCE(v.bultos_rechazados, 0) > 0
                 OR COALESCE(v.unidad_medida_rechazado, 0) > 0
                 OR COALESCE(v.unidad_paquete_rechazado, 0) > 0) AS tiene_rechazo
            FROM ventas_detalle v
            LEFT JOIN articulos a ON a.id_articulo = v.id_articulo
            {rec.REC_JOIN}
            WHERE v.fecha BETWEEN %(desde)s AND %(hasta)s
              AND COALESCE(NULLIF(TRIM(v.empresa), ''), '1') = %(empresa_id)s
              AND (%(sucursal)s = 'TODAS'
                   OR COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') = %(sucursal)s)
              AND {rec.IS_MERCADERIA} AND {rec.NOT_REMITO}
        ), agrupados AS (
            SELECT fecha, cliente_id,
                MAX(COALESCE(NULLIF(TRIM(descripcion_cliente), ''),
                             NULLIF(TRIM(descripcion_detallada_cliente), ''))) AS cliente_nombre,
                JSONB_AGG(DISTINCT sucursal_id) AS sucursales,
                COUNT(*) AS lineas_origen,
                BOOL_OR(tiene_rechazo) AS tiene_rechazo,
                BOOL_OR(tiene_rechazo AND COALESCE(tomar, FALSE)) AS tiene_rechazo_computable,
                COUNT(*) FILTER (WHERE tiene_rechazo AND tomar IS NULL) AS rechazos_sin_clasificar,
                COUNT(*) FILTER (WHERE bultos IS NULL OR bultos_rechazados IS NULL) AS lineas_bultos_incompletas,
                SUM(COALESCE(bultos, 0)) AS bultos_registrados,
                SUM(COALESCE(bultos_rechazados, 0)) AS bultos_rechazados,
                SUM(CASE WHEN tiene_rechazo AND COALESCE(tomar, FALSE)
                         THEN COALESCE(bultos_rechazados, 0) ELSE 0 END) AS bultos_rechazados_computables,
                SUM(COALESCE(unidad_medida, 0)) AS hl_registrados,
                SUM(COALESCE(unidad_medida_rechazado, 0)) AS hl_rechazados,
                SUM(COALESCE(unidad_paquete, 0)) AS up_registradas,
                SUM(COALESCE(unidad_paquete_rechazado, 0)) AS up_rechazadas,
                JSONB_AGG(DISTINCT JSONB_BUILD_OBJECT(
                    'documento', documento, 'letra', letra, 'serie', serie,
                    'numero', numero, 'detalle_documento', detalle_documento,
                    'sucursal_id', sucursal_id
                )) AS documentos,
                COALESCE(JSONB_AGG(DISTINCT JSONB_BUILD_OBJECT(
                    'motivo', motivo_rechazo, 'sector', sector,
                    'computable', COALESCE(tomar, FALSE),
                    'clasificado', tomar IS NOT NULL
                )) FILTER (WHERE tiene_rechazo), '[]'::jsonb) AS motivos
            FROM base
            GROUP BY fecha, cliente_id
        )
        SELECT (SELECT COUNT(*) FROM agrupados) AS total,
            COALESCE((SELECT JSONB_AGG(TO_JSONB(p) ORDER BY p.fecha, p.cliente_id)
                      FROM (SELECT * FROM agrupados ORDER BY fecha, cliente_id
                            LIMIT %(limit)s OFFSET %(offset)s) p), '[]'::jsonb) AS datos
    """
    with pg_cursor() as cur:
        cur.execute(sql, params)
        result = dict(cur.fetchone())
    datos = result.get('datos') or []
    for row in datos:
        row['empresa_id'] = empresa_id
        row['calidad'] = {
            'cliente_identificado': bool(row['cliente_id']),
            'multiples_sucursales': len(row['sucursales']) > 1,
            'lineas_rechazo_sin_clasificar': row.pop('rechazos_sin_clasificar'),
            'lineas_bultos_incompletas': row.pop('lineas_bultos_incompletas'),
        }
        row['sucursales'].sort()
        for field in ('documentos', 'motivos'):
            row[field].sort(key=lambda item: tuple(str(item[k] or '') for k in sorted(item)))
    return {'total': int(result.get('total') or 0), 'datos': datos}
