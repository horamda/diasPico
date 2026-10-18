"""Diagnóstico operativo de lectura: señales explicables, sin modificar recorridos."""
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from sqlalchemy import text

from . import ventas_app as V
from .db import Session
from .services import _km

DAYS = ['LU', 'MA', 'MI', 'JU', 'VI', 'SA']
UNIDADES = ('bultos', 'hl', 'pallets')


def volumen(filas):
    return {k: round(sum(float(f.get(k) or 0) for f in filas), 4) for k in (*UNIDADES, 'bultos_sin_bxp')}


def variacion(actual, anterior):
    return round(actual / anterior - 1, 4) if anterior > 0 else None


def diagnostico(clientes, plan, dias, suc='TODAS', hoy=None):
    hoy = hoy or datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).date()
    if not V.disponible() or not V.ultima_fecha():
        return {'disponible': False, 'dias': dias, 'suc': suc}
    hasta = V.ultima_fecha()
    desde = hasta - timedelta(days=dias - 1)
    prev_hasta, prev_desde = desde - timedelta(days=1), desde - timedelta(days=dias)
    actual = V.comportamiento(dias, hasta)['clientes']
    anteriores = defaultdict(list)
    for d in V.comprobantes(prev_desde, prev_hasta):
        anteriores[d['cliente']].append(d)
    anterior = {cid: V._metricas(ds, dias, prev_hasta) for cid, ds in anteriores.items()}
    docs = V.comprobantes(desde, hasta)
    # Un comprobante puede contener varios motivos: no quedarse con MAX(motivo).
    motivos = defaultdict(list)
    sql_rech = f"""SELECT TRIM(v.cliente) AS cliente, v.fecha, {V.DOC_KEY} AS doc,
        COALESCE(NULLIF(TRIM(v.motivo_rechazo), ''), 'Sin motivo') AS motivo,
        SUM(v.bultos_rechazados) AS bultos
        FROM ventas_detalle v LEFT JOIN articulos a ON a.id_articulo=v.id_articulo
        WHERE {V.FILTROS} AND {V.MERC} AND v.bultos_rechazados > 0
        GROUP BY TRIM(v.cliente), v.fecha, {V.DOC_KEY}, COALESCE(NULLIF(TRIM(v.motivo_rechazo), ''), 'Sin motivo')"""
    for r in Session().execute(text(sql_rech), V._params(desde, hasta)).mappings():
        cid = str(r['cliente'] or '')
        if cid.isdecimal():
            motivos[(int(cid), V._d(r['fecha']), r['doc'])].append((r['motivo'], float(r['bultos'])))
    for d in docs:
        d['rechazo_motivos'] = motivos[(d['cliente'], d['fecha'], d['doc'])]
    # Calidad: incluye filas sin cliente; los problemas de origen se informan globalmente.
    filtros = V.FILTROS.replace("AND NULLIF(TRIM(v.cliente), '') IS NOT NULL", '')
    sql = f"""SELECT TRIM(v.cliente) AS cliente,
        SUM(CASE WHEN a.id_articulo IS NULL THEN 1 ELSE 0 END) AS sin_articulo,
        SUM(CASE WHEN {V.MERC} AND v.unidad_medida IS NULL THEN 1 ELSE 0 END) AS sin_hl,
        COUNT(*) AS filas
        FROM ventas_detalle v LEFT JOIN articulos a ON a.id_articulo=v.id_articulo
        WHERE {filtros} GROUP BY TRIM(v.cliente)"""
    known = {c['id'] for c in clientes}
    calidad = {'filas_sin_articulo': 0, 'filas_sin_hl': 0, 'filas_sin_cliente': 0}
    for r in Session().execute(text(sql), V._params(desde, hasta)).mappings():
        cid = str(r['cliente'] or '')
        calidad['filas_sin_articulo'] += int(r['sin_articulo'] or 0)
        calidad['filas_sin_hl'] += int(r['sin_hl'] or 0)
        if not cid.isdecimal() or int(cid) not in known:
            calidad['filas_sin_cliente'] += int(r['filas'])
    primera = V._d(Session().execute(text('SELECT MIN(fecha) FROM ventas_detalle')).scalar())
    meta = {'desde': desde.isoformat(), 'hasta': hasta.isoformat(), 'anterior_desde': prev_desde.isoformat(),
            'anterior_hasta': prev_hasta.isoformat(), 'primera_fecha': primera.isoformat() if primera else None,
            'historial_suficiente': bool(primera and primera <= prev_desde),
            'dias_desactualizacion': (hoy - hasta).days, 'calidad_origen': calidad}
    return analizar(clientes, plan, actual, anterior, docs, dias, suc, meta)


def analizar(clientes, plan, actual, anterior, docs, dias, suc, meta):
    """Agrupa por sucursal de entrega del maestro, no por sucursal contable de venta."""
    activos = [c for c in clientes if not c['an'] and (suc == 'TODAS' or c['suc'] == suc)]
    grupos, por_doc = defaultdict(list), defaultdict(list)
    for c in activos:
        grupos[(c['suc'], c['loc'])].append(c)
    for d in docs:
        por_doc[d['cliente']].append(d)
    alertas = []
    def alerta(tipo, nivel, c, evidencia, accion, **extra):
        alertas.append({'tipo': tipo, 'nivel': nivel, 'id': c.get('id'), 'nombre': c.get('n', ''),
                        'suc': c['suc'], 'loc': c.get('loc', ''), 'evidencia': evidencia, 'accion': accion,
                        **volumen([actual.get(c.get('id'), {})]), **extra})
    locs = []
    for (sucursal, loc), cs in grupos.items():
        a = volumen([actual.get(c['id'], {}) for c in cs])
        p = volumen([anterior.get(c['id'], {}) for c in cs])
        pesos = sorted([max(0, actual.get(c['id'], {}).get('bultos', 0)) for c in cs], reverse=True)
        concentracion = sum(pesos[:3]) / sum(pesos) if sum(pesos) else None
        locs.append({'suc': sucursal, 'loc': loc, 'clientes': len(cs), **a, 'anterior': p,
                     'variacion': {u: variacion(a[u], p[u]) if meta['historial_suficiente'] else None for u in UNIDADES},
                     'top3_pct': concentracion, 'bultos_sem': round(a['bultos'] * 7 / dias, 2),
                     'hl_sem': round(a['hl'] * 7 / dias, 2), 'pallets_sem': round(a['pallets'] * 7 / dias, 4)})
    altas = {}
    rechazos = defaultdict(lambda: {'bultos': 0, 'comprobantes': set(), 'clientes': set()})
    for c in activos:
        m, p = actual.get(c['id'], {}), anterior.get(c['id'], {})
        asignados = [d for d in DAYS if d in c['d']]
        n, frec = m.get('compras', 0), m.get('frec_hist')
        if asignados and not n:
            ultima = m.get('ultima') or 'sin compra registrada'
            alerta('sin_compras', 'alta' if m.get('estado') == 'inactivo' else 'media', c,
                   f"{len(asignados)} días asignados; 0 compras en {dias} días. Última: {ultima}.",
                   'Confirmar próxima compra antes de mantener la parada; no quitarla automáticamente.')
        elif m.get('estado') in ('riesgo', 'inactivo'):
            alerta('actividad', 'alta', c, f"{m.get('dias_sin')} días sin comprar al cierre; frecuencia histórica: {frec or 'sin base'} días.",
                   'Contactar al cliente y revisar el motivo de la interrupción.')
        if not asignados:
            alerta('sin_dias', 'alta' if n else 'media', c, f'{n} compras y ningún día de entrega asignado.', 'Revisar la asignación de días.')
        if c.get('lat') is None or c.get('lng') is None or c.get('far'):
            alerta('ubicacion', 'media', c, 'Coordenadas ausentes o marcadas para revisión.', 'Verificar ubicación antes de evaluar distancias.')
        if m.get('bultos_sin_bxp', 0) > 0:
            alerta('bxp', 'media', c, f"{m['bultos_sin_bxp']:g} bultos sin conversión a pallets.", 'Completar BxP en el maestro de artículos.')
        peers = [actual.get(x['id'], {}).get('drop', 0) for x in grupos[(c['suc'], c['loc'])]]
        peers = [x for x in peers if x > 0]
        pequeno = len(peers) >= 5 and 0 < m.get('drop', 0) < median(peers) * .5
        if dias >= 30 and n >= 3 and len(asignados) >= 2 and n * 7 / dias < len(asignados) * .5 and pequeno:
            alerta('frecuencia', 'media', c, f"{len(asignados)} días asignados/sem; {n * 7 / dias:.1f} compras/sem; {m['drop']:g} bultos/compra (<50% de la mediana local).",
                   'Evaluar concentrar pedidos en menos días con el cliente.')
        if meta['historial_suficiente'] and p.get('compras', 0) >= 3:
            cambio = variacion(m.get('bultos', 0), p.get('bultos', 0))
            if cambio is not None and cambio <= -.3:
                alerta('caida', 'alta', c, f"Bultos {cambio:.0%} frente a los {dias} días anteriores ({p['bultos']:g} → {m.get('bultos', 0):g}).",
                       'Revisar pérdida de compra, stock y cambios de frecuencia.', anterior=volumen([p]))
        fechas = defaultdict(lambda: dict.fromkeys(UNIDADES, 0.0))
        rech_docs = set()
        for d in por_doc[c['id']]:
            if d['tipo'] in V.DOC_VENTA | {'RMCYO'} and (d['bultos'] > 0 or d['neto'] > 0):
                for u in UNIDADES:
                    fechas[d['fecha']][u] += max(0, d[u])
            if d['rech'] > 0:
                rech_docs.add(d['doc'])
                for motivo, cantidad in d.get('rechazo_motivos', [(d['motivo'] or 'Sin motivo', d['rech'])]):
                    key = (c['suc'], V.WD[d['fecha'].weekday()], motivo)
                    rechazos[key]['bultos'] += cantidad
                    rechazos[key]['comprobantes'].add((c['id'], d['fecha'], d['doc']))
                    rechazos[key]['clientes'].add(c['id'])
        # P90 por cliente: escenario alto; NO es un pico simultáneo del camión.
        altas[c['id']] = {u: sorted(f[u] for f in fechas.values())[math.ceil(.9 * len(fechas)) - 1]
                          if len(fechas) >= 5 else None for u in UNIDADES}
        if len(rech_docs) >= 2:
            alerta('rechazos', 'alta', c, f"{len(rech_docs)} comprobantes con rechazo; {m.get('rech', 0):g} bultos rechazados.",
                   'Revisar horario, pedido y motivo con el cliente y reparto.')
        if pequeno and n >= 3 and c.get('lat') is not None and c.get('lng') is not None and not c.get('far'):
            vecinos = [x for x in activos if x['id'] != c['id'] and x['suc'] == c['suc'] and x.get('lat') is not None and x.get('lng') is not None and not x.get('far')
                       and any(d in x['d'] for d in asignados)]
            distancia = min((_km((c['lat'], c['lng']), (x['lat'], x['lng'])) for x in vecinos), default=None)
            if distancia is not None and distancia > 5:
                alerta('distancia', 'media', c, f"{distancia:.1f} km en línea recta al cliente más cercano con algún día compartido; volumen por compra bajo.",
                       'Evaluar agrupación de días; verificar distancia vial y tiempos antes de decidir.')
    vehiculos = [v for v in plan['vehiculos'] if suc == 'TODAS' or v['deposito'] == suc]
    usos = Counter((v['deposito'], loc, d) for v in vehiculos for d in DAYS for loc in set(v['plan'].get(d, [])))
    rutas, dias_carga = [], []
    def carga(cs):
        medidas = {'bultos': 'drop', 'hl': 'drop_hl', 'pallets': 'drop_pallets'}
        habituales = {u: round(sum(max(0, actual.get(c['id'], {}).get(k, 0)) for c in cs), 4) for u, k in medidas.items()}
        completa = bool(cs) and all(altas[c['id']]['bultos'] is not None for c in cs)
        alta = {u: round(sum(altas[c['id']][u] for c in cs), 4) if completa else None for u in UNIDADES}
        return {**habituales, 'alta': alta, 'sin_base': sum(not actual.get(c['id'], {}).get('compras') for c in cs),
                'bultos_sin_bxp': sum(actual.get(c['id'], {}).get('bultos_sin_bxp', 0) for c in cs)}
    for d in DAYS:
        cs_dia = [c for c in activos if d in c['d']]
        dias_carga.append({'dia': d, 'clientes': len(cs_dia), **carga(cs_dia)})
        for c in cs_dia:
            if not usos[(c['suc'], c['loc'], d)]:
                alerta('sin_camion', 'media', c, f'{d}: localidad sin camión asignado.', 'Revisar el plan del día.')
        for v in vehiculos:
            cs = [c for c in cs_dia if c['suc'] == v['deposito'] and c['loc'] in v['plan'].get(d, [])]
            if not v['plan'].get(d):
                continue
            compartida = any(usos[(v['deposito'], loc, d)] > 1 for loc in v['plan'][d])
            pesos = sorted([max(0, actual.get(c['id'], {}).get('drop', 0)) for c in cs], reverse=True)
            cap = v.get('capacidad_clientes')
            rutas.append({'id': v['id'], 'nombre': v['nombre'], 'suc': v['deposito'], 'dia': d,
                          'clientes': len(cs), 'capacidad_clientes': cap, 'compartida': compartida,
                          'ocupacion_clientes': len(cs) / cap if cap and cap > 0 and not compartida else None,
                          'top3_pct': sum(pesos[:3]) / sum(pesos) if sum(pesos) else None, **carga(cs)})
            rc = {'suc': v['deposito'], 'n': v['nombre']}
            if compartida:
                alerta('compartida', 'media', rc, f'{d}: localidades compartidas entre camiones; carga no atribuible a uno solo.',
                       'Definir qué clientes atiende cada camión antes de sumar capacidades.', clientes_afectados=[c['id'] for c in cs])
            elif cap and cap > 0 and len(cs) > cap:
                alerta('capacidad', 'alta', rc, f'{d}: {len(cs)} clientes asignados para un tope orientativo de {cap}.',
                       'Revisar distribución de paradas y tiempos; no implica exceso físico de peso.', clientes_afectados=[c['id'] for c in cs], **carga(cs))
    alertas.sort(key=lambda a: (a['nivel'] != 'alta', -max(a['bultos'], 0), a['suc'], a['nombre']))
    resumen = []
    for tipo in dict.fromkeys(a['tipo'] for a in alertas):
        aa = [a for a in alertas if a['tipo'] == tipo]
        ids = {a['id'] for a in aa if a['id'] is not None}
        ids.update(cid for a in aa for cid in a.get('clientes_afectados', []))
        resumen.append({'tipo': tipo, 'alertas': len(aa), 'clientes': len(ids), **volumen([actual.get(cid, {}) for cid in ids])})
    return {'disponible': True, 'dias': dias, 'suc': suc, **meta, 'clientes': len(activos), 'alertas': alertas,
            'resumen': resumen, 'localidades': locs, 'rutas': rutas, 'dias_carga': dias_carga,
            'volumen': volumen([actual.get(c['id'], {}) for c in activos]),
            'anterior': volumen([anterior.get(c['id'], {}) for c in activos]),
            'rechazos': [{'suc': s, 'dia': d, 'motivo': m, 'bultos': round(v['bultos'], 2),
                          'comprobantes': len(v['comprobantes']), 'clientes': len(v['clientes'])}
                         for (s, d, m), v in sorted(rechazos.items())]}
