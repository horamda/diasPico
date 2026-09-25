"""PDV attention cost: assigned route kilometers times one all-inclusive rate."""
import math
from datetime import date
from urllib.parse import urlencode, urlsplit

import requests
from flask import current_app

from app.database import pg_cursor
from app.services import segmentacion_svc as segmentation


def client_id(value):
    value = str(value or '').strip()
    if value.endswith('.0'):
        value = value[:-2]
    return str(int(value)) if value.isdigit() else value


def rate_value(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError('Ingresá un costo por km válido.')
    if not math.isfinite(value) or value <= 0 or value > 100000000:
        raise ValueError('El costo por km debe ser mayor a cero y de hasta 100.000.000.')
    return value


def load_clients(desde, hasta, empresa):
    segmentation.ensure_tables()
    source = 'seg_cliente_dpo_cache' if segmentation._dpo_cache_has_rows() else segmentation._plan_source()
    with pg_cursor() as cur:
        cur.execute(f"""WITH sales AS (
            SELECT TRIM(v.cliente) AS cliente,
                   COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') AS sucursal,
                   SUM(COALESCE(v.importe_neto, 0)) AS venta,
                   SUM(COALESCE(v.bultos, 0)) AS bultos
            FROM ventas_detalle v
            JOIN articulos a ON a.id_articulo = v.id_articulo
            WHERE v.fecha BETWEEN %(desde)s AND %(hasta)s
              AND COALESCE(NULLIF(TRIM(v.empresa), ''), '1') = %(empresa)s
              AND LOWER(TRIM(COALESCE(a.tipo_producto, ''))) = 'mercaderia'
              AND LOWER(TRIM(COALESCE(v.documento, ''))) NOT LIKE 'remit%%'
              AND LOWER(TRIM(COALESCE(v.documento, ''))) NOT LIKE 'comod%%'
              AND LOWER(TRIM(COALESCE(v.detalle_documento, ''))) NOT LIKE 'remit%%'
              AND LOWER(TRIM(COALESCE(v.detalle_documento, ''))) NOT LIKE 'comod%%'
            GROUP BY 1, 2
        ) SELECT c.cliente, c.descripcion_cliente, c.sucursal, c.sucursal_nombre,
                 c.localidad, c.cluster_dpo, s.venta AS venta_ytd, s.bultos AS bultos_ytd
          FROM {source} c
          LEFT JOIN sales s ON s.cliente = TRIM(c.cliente) AND s.sucursal = c.sucursal""",
                    {'desde': desde, 'hasta': hasta, 'empresa': empresa})
        return [dict(r) for r in cur.fetchall()]


def fetch_distances(base_url, key, desde, hasta):
    url = base_url.rstrip('/') + '/api/integracion/v1/pdv-distancias'
    response = requests.get(url, params={'desde': desde, 'hasta': hasta},
                            headers={'Authorization': 'Bearer ' + key},
                            timeout=(5, 40), allow_redirects=False)
    if response.status_code != 200:
        raise RuntimeError('Reparto no respondió correctamente. Revisá la conexión y la clave de integración.')
    data = response.json()
    if (data.get('ok') is not True or data.get('version') != 1
            or data.get('desde') != desde or data.get('hasta') != hasta
            or not isinstance(data.get('items'), list)):
        raise RuntimeError('La respuesta de Reparto no corresponde al período solicitado.')
    return data


def aggregate(clients, visits, rate, base_url, sucursal='', cluster=''):
    """Keep uncosted visits visible and never join customers across branches."""
    groups = {}
    for client in clients:
        key = (str(client.get('sucursal') or '').strip(), client_id(client.get('cliente')))
        if key in groups:
            raise ValueError('Hay códigos de cliente duplicados en la misma sucursal. Revisá el maestro.')
        groups[key] = {
            'cliente': key[1], 'sucursal': key[0],
            'nombre': client.get('descripcion_cliente') or '',
            'localidad': client.get('localidad') or '',
            'cluster': client.get('cluster_dpo') or 'Sin clasificar',
            'venta': float(client['venta_ytd']) if client.get('venta_ytd') is not None else None,
            'bultos': float(client['bultos_ytd']) if client.get('bultos_ytd') is not None else None,
            'visitas': [], 'sin_maestro': False,
        }
    identities = set()
    for visit in visits:
        key = (str(visit.get('sucursal') or '').strip(), client_id(visit.get('cliente')))
        identity = (key, str(visit.get('rid') or ''))
        if not all(key) or not identity[1] or identity in identities:
            raise ValueError('Reparto devolvió atenciones duplicadas o sin identificación.')
        identities.add(identity)
        row = groups.setdefault(key, {
            'cliente': key[1], 'sucursal': key[0], 'nombre': visit.get('nombre') or '',
            'localidad': '', 'cluster': 'Sin clasificar', 'venta': None, 'bultos': None,
            'visitas': [], 'sin_maestro': True,
        })
        km = visit.get('km_asignados')
        if km is not None and (not isinstance(km, (int, float)) or not math.isfinite(km) or km < 0):
            raise ValueError('Reparto devolvió una distancia inválida.')
        row['visitas'].append({
            'rid': visit['rid'], 'fecha': visit.get('fecha'),
            'km_tramo': visit.get('km_tramo'), 'km_regreso': visit.get('km_regreso'),
            'km_asignados': km, 'costo': km * rate if km is not None else None,
            'estimada': visit.get('distancia_estimada'),
            'estado_entrega': visit.get('estado_entrega') or 'Sin estado',
            'detalle_url': base_url.rstrip('/') + '/costos-distribucion?' + urlencode({'rid': visit['rid']}),
        })
    result = []
    for row in groups.values():
        if sucursal and sucursal != 'TODAS' and row['sucursal'] != sucursal:
            continue
        if cluster and row['cluster'] != cluster:
            continue
        visits = row['visitas']
        known = [v for v in visits if v['km_asignados'] is not None]
        pending = len(visits) - len(known)
        km = sum(v['km_asignados'] for v in known) if known else None
        cost = km * rate if km is not None else None
        complete = bool(visits) and pending == 0
        row.update({
            'atenciones': len(visits), 'atenciones_con_km': len(known), 'pendientes': pending,
            'km_asignados': km, 'costo': cost,
            'costo_por_atencion': cost / len(known) if known else None,
            'costo_por_bulto': cost / row['bultos'] if complete and (row['bultos'] or 0) > 0 else None,
            'costo_sobre_venta': cost / row['venta'] * 100 if complete and (row['venta'] or 0) > 0 else None,
            'estado': ('Sin visitas registradas' if not visits else 'Sin distancias' if not known
                       else 'Parcial' if pending else 'Calculado'),
            'estimadas': sum(bool(v['estimada']) for v in known),
        })
        result.append(row)
    result.sort(key=lambda r: (r['costo'] is None, -(r['costo'] or 0), r['sucursal'], r['cliente']))
    return result


def report(rate=2500, sucursal='', cluster=''):
    rate = rate_value(rate)
    base = str(current_app.config.get('REPARTO_COST_API_URL') or '').strip().rstrip('/')
    key = str(current_app.config.get('REPARTO_COST_API_KEY') or '').strip()
    if not base or not key:
        return {'configurado': False, 'tarifa': rate, 'items': [],
                'mensaje': 'Falta conectar las distancias de Dashboard Reparto. La tarifa está lista; todavía no hay costos por km disponibles.'}
    parsed = urlsplit(base)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError('La dirección de Dashboard Reparto no es válida.')
    params = segmentation.get_parametros()
    period = params.get('periodo') or {}
    desde = str(period.get('fecha_desde') or '')[:10]
    hasta = str(period.get('fecha_hasta') or '')[:10]
    start, end = date.fromisoformat(desde), date.fromisoformat(hasta)
    if end < start or (end - start).days > 366:
        raise ValueError('Configurá en Parámetros un período válido de hasta 366 días.')
    # Reparto is a single-company dataset; never silently reuse it for another company.
    empresa = str(period.get('empresa_id') or params.get('empresa_id') or '1')
    if empresa != str(current_app.config.get('REPARTO_COST_EMPRESA_ID') or '1'):
        raise ValueError('La empresa del período no coincide con la conexión de Reparto.')
    data = fetch_distances(base, key, desde, hasta)
    rows = aggregate(load_clients(desde, hasta, empresa), data['items'], rate, base, str(sucursal or ''),
                     segmentation._normalize_cluster_filter(cluster) or '')
    return {'configurado': True, 'tarifa': rate, 'desde': desde, 'hasta': hasta,
            'items': rows, 'rutas': data.get('rutas'),
            'rutas_sin_distancias': data.get('rutas_sin_distancias'),
            'mensaje': 'Costo = (tramo hasta el cliente + regreso proporcional) × tarifa por km. '
                       'Una atención corresponde a un cliente en un recorrido. '
                       'Los kilómetros provienen del ruteo calculado; no son un registro GPS del trayecto real. '
                       'Los totales parciales incluyen sólo atenciones con distancia disponible.'}
