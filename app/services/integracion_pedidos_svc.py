"""Comprobantes y rechazos de ventas; no acredita entregas efectivas."""
import hashlib
import json
import unicodedata

from app.database import pg_cursor
from app.services import rechazos_svc as rec


def _flag(value):
    value = unicodedata.normalize('NFKD', str(value or '').strip().lower())
    value = ''.join(c for c in value if not unicodedata.combining(c))
    if value in {'si', 's', 'yes', 'y', 'true', '1', 'x'}:
        return True
    if value in {'no', 'n', 'false', '0'}:
        return False
    return None


def _clasificar(lineas):
    """No compara rechazado/venta: la semántica del denominador no está confirmada."""
    flags = [_flag(line['rechazo_total']) for line in lineas]
    campos = ('bultos_rechazados', 'hl_rechazados', 'up_rechazadas')
    rechazos = [any((line.get(k) or 0) > 0 for k in campos) for line in lineas]
    faltantes = any(any(line.get(k) is None for k in campos) for line in lineas)
    negativos = any(any((line.get(k) or 0) < 0 for k in ('bultos', 'hl', 'up') + campos) for line in lineas)
    inconsistente = any(flag is True and not rechazo for flag, rechazo in zip(flags, rechazos))
    if not lineas or negativos or inconsistente:
        return 'sin_determinar', faltantes, negativos, inconsistente
    if not any(rechazos):
        estado = 'sin_determinar' if faltantes else 'sin_rechazo_registrado'
    elif all(rechazos) and all(flag is True for flag in flags):
        estado = 'total'
    elif faltantes or any(flag is None for flag in flags):
        estado = 'sin_determinar'
    else:
        estado = 'parcial'
    return estado, faltantes, negativos, inconsistente


def get_pedidos(*, desde, hasta, sucursal, limit, offset, empresa_id='1'):
    rec.ensure_ventas_detalle_table()
    rec.ensure_articulos_table()
    rec.ensure_table()
    params = dict(desde=desde, hasta=hasta, sucursal=sucursal, limit=limit,
                  offset=offset, empresa_id=empresa_id)
    with pg_cursor() as cur:
        cur.execute(f"""
            WITH alcance AS NOT MATERIALIZED (
                SELECT v.*,
                    COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') AS sucursal_id,
                    NULLIF(TRIM(v.cliente), '') AS cliente_id
                FROM ventas_detalle v
                LEFT JOIN articulos a ON a.id_articulo = v.id_articulo
                WHERE COALESCE(NULLIF(TRIM(v.empresa), ''), '1') = %(empresa_id)s
                  AND (%(sucursal)s = 'TODAS'
                       OR COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') = %(sucursal)s)
                  AND {rec.IS_MERCADERIA} AND {rec.NOT_REMITO}
            ), base AS (
                SELECT v.*,
                    CASE WHEN NULLIF(TRIM(documento), '') IS NOT NULL
                              AND NULLIF(TRIM(serie), '') IS NOT NULL
                              AND NULLIF(TRIM(numero), '') IS NOT NULL
                         THEN JSONB_BUILD_ARRAY('comprobante', TRIM(documento),
                              COALESCE(TRIM(letra), ''), TRIM(serie), TRIM(numero))
                         WHEN NULLIF(TRIM(detalle_documento), '') IS NOT NULL
                         THEN JSONB_BUILD_ARRAY('detalle', TRIM(detalle_documento))
                         ELSE JSONB_BUILD_ARRAY('fila', id::text) END AS referencia
                FROM alcance v WHERE fecha BETWEEN %(desde)s AND %(hasta)s
            ), grupos AS (
                SELECT referencia, sucursal_id, cliente_id, fecha
                FROM base GROUP BY referencia, sucursal_id, cliente_id, fecha
            ), pagina AS (
                SELECT * FROM grupos ORDER BY fecha, sucursal_id, cliente_id, referencia
                LIMIT %(limit)s OFFSET %(offset)s
            ), detalle_pagina AS (
                SELECT p.referencia, p.sucursal_id, p.cliente_id, p.fecha AS fecha_movimiento,
                    MAX(COALESCE(NULLIF(TRIM(v.descripcion_cliente), ''),
                                 NULLIF(TRIM(v.descripcion_detallada_cliente), ''))) AS cliente_nombre,
                    MAX(NULLIF(TRIM(v.numero), '')) AS numero_comprobante,
                    JSONB_AGG(DISTINCT JSONB_BUILD_OBJECT(
                        'documento', v.documento, 'letra', v.letra, 'serie', v.serie,
                        'numero', v.numero, 'detalle_documento', v.detalle_documento
                    )) AS comprobantes,
                    JSONB_AGG(JSONB_BUILD_OBJECT(
                        'id_origen', v.id::text, 'articulo_id', v.id_articulo,
                        'bultos', v.bultos, 'hl', v.unidad_medida, 'up', v.unidad_paquete,
                        'bultos_rechazados', v.bultos_rechazados,
                        'hl_rechazados', v.unidad_medida_rechazado,
                        'up_rechazadas', v.unidad_paquete_rechazado,
                        'rechazo_total', v.rechazo_total, 'motivo_rechazo', v.motivo_rechazo,
                        'rechazo_computable', {rec.IS_REC},
                        'motivo_clasificado', rz.tomar IS NOT NULL, 'sector', rz.sector,
                        'ruta_codigo', NULLIF(TRIM(v.ruta), ''), 'ruta', v.descripcion_ruta,
                        'chofer_codigo', v.chofer, 'transporte_codigo', v.transporte
                    ) ORDER BY v.id) AS detalle
                FROM pagina p JOIN base v ON v.referencia = p.referencia
                    AND v.sucursal_id = p.sucursal_id
                    AND v.cliente_id IS NOT DISTINCT FROM p.cliente_id AND v.fecha = p.fecha
                {rec.REC_JOIN}
                GROUP BY p.referencia, p.sucursal_id, p.cliente_id, p.fecha
            )
            SELECT (SELECT COUNT(*) FROM grupos) AS total,
                (SELECT MAX(fecha) FROM alcance) AS ultima_fecha_disponible,
                COALESCE((SELECT JSONB_AGG(TO_JSONB(p)
                    ORDER BY fecha_movimiento, sucursal_id, cliente_id, referencia)
                    FROM detalle_pagina p), '[]'::jsonb) AS datos
        """, params)
        result = dict(cur.fetchone())
    for row in result['datos']:
        referencia = row.pop('referencia')
        identity = [empresa_id, row['sucursal_id'], row['cliente_id'], row['fecha_movimiento'], referencia]
        row['id_integracion'] = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
        row['empresa_id'] = empresa_id
        row['tipo_identificador'] = 'fila' if referencia[0] == 'fila' else 'comprobante'
        row['numero_pedido'] = None
        row['fecha_entrega'] = None
        row['fuente_fecha_entrega'] = None
        row['fuente_fecha_movimiento'] = 'ventas_detalle.fecha'
        estado, faltantes, negativos, inconsistente = _clasificar(row['detalle'])
        row['estado_rechazo'] = estado
        row['estado_entrega'] = {'total': 'rechazada', 'parcial': 'parcial'}.get(estado, 'sin_determinar')
        row['fuente_estado'] = 'ventas_detalle: cantidades rechazadas y rechazo_total'
        row['estado_entrega_inferido'] = row['estado_entrega'] != 'sin_determinar'
        row['lineas_origen'] = len(row['detalle'])
        campos = ('bultos', 'hl', 'up', 'bultos_rechazados', 'hl_rechazados', 'up_rechazadas')
        row['cantidades'] = {
            campo: (sum(line[campo] for line in row['detalle'])
                    if all(line[campo] is not None for line in row['detalle']) else None)
            for campo in campos
        }
        row['tiene_rechazo_registrado'] = any(
            any((line[campo] or 0) > 0 for campo in campos[3:]) for line in row['detalle'])
        row['tiene_rechazo_computable'] = any(line['rechazo_computable'] for line in row['detalle'])
        row['vinculo_foxtrot'] = {
            'numero_pedido': None, 'comprobantes': row['comprobantes'],
            'rutas_venta': sorted({line['ruta_codigo'] for line in row['detalle'] if line['ruta_codigo']}),
            'rutas_distribucion': [], 'planillas': [],
        }
        row['calidad'] = {
            'cliente_identificado': bool(row['cliente_id']),
            'pedido_o_comprobante_identificado': referencia[0] != 'fila',
            'cantidades_rechazo_incompletas': faltantes,
            'cantidades_negativas': negativos,
            'lineas_rechazo_sin_clasificar': sum(
                not line['motivo_clasificado'] and any((line[campo] or 0) > 0 for campo in campos[3:])
                for line in row['detalle']),
            'marca_total_sin_cantidad_rechazada': inconsistente,
            'fecha_entrega_disponible': False,
            'entrega_completa_confirmada': False,
        }
    fecha = result['ultima_fecha_disponible']
    result['ultima_fecha_disponible'] = fecha.isoformat() if fecha else None
    return result
