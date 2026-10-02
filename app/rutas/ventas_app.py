"""Pedidos y volumen por cliente desde ventas_detalle, la tabla de ventas que ya carga el portal.

Mismas reglas que Drop Size y Días Pico:
  * se excluyen remitos (REMIT) y comodatos (COMOD);
  * bultos y HL cuentan solo artículos de tipo mercadería (sin envases ni esqueletos);
  * un pedido es un comprobante (detalle_documento) y una entrega, un día con comprobantes del cliente.
RMCYO cuenta como pedido y volumen; no tiene importe, así que no suma venta en $.
"""
import statistics as st
import time
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import inspect, text

from .db import Session
from .ventas import WD, estado

DOC_VENTA = {'FCVTA', 'PRVTA'}
TTL = 600  # segundos; ventas_detalle cambia solo cuando se importa
_cache = {}

MERC = "LOWER(TRIM(COALESCE(a.tipo_producto, ''))) = 'mercaderia'"
DOC_KEY = ("COALESCE(NULLIF(TRIM(v.detalle_documento), ''), "
           "TRIM(COALESCE(v.documento, '')) || '-' || TRIM(COALESCE(v.letra, '')) || '-' || "
           "TRIM(COALESCE(v.serie, '')) || '-' || TRIM(COALESCE(v.numero, '')))")
FILTROS = """
  v.fecha BETWEEN :desde AND :hasta
  AND NULLIF(TRIM(v.cliente), '') IS NOT NULL
  AND LOWER(TRIM(COALESCE(v.documento, ''))) NOT LIKE :remit
  AND LOWER(TRIM(COALESCE(v.documento, ''))) NOT LIKE :comod
  AND LOWER(TRIM(COALESCE(v.detalle_documento, ''))) NOT LIKE :remit
  AND LOWER(TRIM(COALESCE(v.detalle_documento, ''))) NOT LIKE :comod
"""
SQL_DOCS = f"""
SELECT TRIM(v.cliente) AS cliente, v.fecha AS fecha, {DOC_KEY} AS doc,
       MAX(UPPER(TRIM(COALESCE(v.documento, '')))) AS tipo,
       MAX(TRIM(COALESCE(v.origen, ''))) AS origen,
       SUM(CASE WHEN {MERC} THEN COALESCE(v.bultos, 0) ELSE 0 END) AS bultos,
       SUM(CASE WHEN {MERC} THEN COALESCE(v.unidad_medida, 0) ELSE 0 END) AS hl,
       SUM(COALESCE(v.importe_neto, 0)) AS neto,
       SUM(CASE WHEN {MERC} THEN COALESCE(v.bultos_rechazados, 0) ELSE 0 END) AS rech,
       MAX(NULLIF(TRIM(COALESCE(v.motivo_rechazo, '')), '')) AS motivo
FROM ventas_detalle v
LEFT JOIN articulos a ON a.id_articulo = v.id_articulo
WHERE {FILTROS} {{extra}}
GROUP BY TRIM(v.cliente), v.fecha, {DOC_KEY}
"""
SQL_ARTICULOS = f"""
SELECT COALESCE(NULLIF(TRIM(v.descripcion_articulo), ''), 'Artículo ' || COALESCE(v.id_articulo, 0)) AS articulo,
       SUM(COALESCE(v.bultos, 0)) AS bultos, SUM(COALESCE(v.unidad_medida, 0)) AS hl
FROM ventas_detalle v
LEFT JOIN articulos a ON a.id_articulo = v.id_articulo
WHERE {FILTROS} AND TRIM(v.cliente) = :cliente AND {MERC}
GROUP BY 1
ORDER BY 2 DESC
LIMIT 8
"""


def _d(v):
    if v is None or isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _params(desde, hasta, **extra):
    return dict(desde=desde, hasta=hasta, remit='remit%', comod='comod%', **extra)


def _memo(key, fn):
    """Valor cacheado por TTL (evita idas a la base en cada consulta del mapa)."""
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < TTL:
        return hit[1]
    value = fn()
    _cache[key] = (time.monotonic(), value)
    return value


def disponible():
    def check():
        insp = inspect(Session().get_bind())
        return insp.has_table('ventas_detalle') and insp.has_table('articulos')
    return _memo('disponible', check)


def ultima_fecha():
    return _memo('ultima', lambda: _d(Session().execute(text('SELECT MAX(fecha) FROM ventas_detalle')).scalar()))


def _ventana(dias, hasta=None):
    hasta = hasta or ultima_fecha() or date.today()
    return hasta - timedelta(days=dias - 1), hasta


def comprobantes(desde, hasta, cliente=None):
    """Un registro por comprobante con su volumen de mercadería, importe y rechazo."""
    extra, params = '', _params(desde, hasta)
    if cliente is not None:
        extra, params['cliente'] = 'AND TRIM(v.cliente) = :cliente', str(cliente)
    out = []
    for r in Session().execute(text(SQL_DOCS.format(extra=extra)), params).mappings():
        cid = str(r['cliente'] or '').strip()
        if not cid.isdecimal():
            continue
        out.append({'cliente': int(cid), 'fecha': _d(r['fecha']), 'doc': r['doc'] or '', 'tipo': r['tipo'] or '',
                    'origen': r['origen'] or '', 'bultos': float(r['bultos'] or 0), 'hl': float(r['hl'] or 0),
                    'neto': float(r['neto'] or 0), 'rech': float(r['rech'] or 0), 'motivo': r['motivo']})
    return out


def _metricas(ds, dias, hasta):
    fechas = sorted({d['fecha'] for d in ds})
    gaps = [(b - a).days for a, b in zip(fechas, fechas[1:])]
    ventas = [d for d in ds if d['tipo'] in DOC_VENTA]
    bultos, hl = sum(d['bultos'] for d in ds), sum(d['hl'] for d in ds)
    neto, rech = sum(d['neto'] for d in ds), sum(d['rech'] for d in ds)
    mitad = hasta - timedelta(days=dias // 2)
    rec = sum(d['bultos'] for d in ds if d['fecha'] > mitad)
    ant = sum(d['bultos'] for d in ds if d['fecha'] <= mitad)
    motivos = Counter(d['motivo'] for d in ds if d['motivo'] and d['rech'] > 0)
    return {
        'pedidos': len({d['doc'] for d in ds}),
        'compras': len(fechas),                      # entregas: días con comprobantes
        'bultos': round(bultos, 1), 'hl': round(hl, 2), 'neto': round(neto),
        'ticket': round(neto / len(ventas)) if ventas else 0,
        'drop': round(bultos / len(fechas), 1) if fechas else 0,
        'drop_hl': round(hl / len(fechas), 2) if fechas else 0,
        'bultos_sem': round(bultos / (dias / 7), 1),
        'rech': round(rech, 1), 'rech_pct': round(rech / bultos, 3) if bultos else 0,
        'motivos': dict(motivos.most_common(3)),
        'ultima': fechas[-1].isoformat() if fechas else None,
        'dias_sin': (hasta - fechas[-1]).days if fechas else None,
        'frec': round(st.median(gaps), 1) if gaps else None,
        'ent': dict(Counter(WD[f.weekday()] for f in fechas)),
        'bees': round(sum(1 for d in ds if d['origen'] == 'BEES') / len(ds), 2) if ds else 0,
        'tend': round((rec - ant) / ant, 2) if ant > 0 else None,
    }


def comportamiento(dias=60, hasta=None):
    """Métricas por cliente en [hasta-dias+1, hasta]. 'hasta' es la última fecha cargada."""
    if not disponible():
        return {'desde': None, 'hasta': None, 'dias': dias, 'comprobantes': 0, 'clientes': {}, 'fuente': 'ventas_detalle'}
    desde, hasta = _ventana(dias, hasta)
    return _memo(('comportamiento', dias, hasta), lambda: _calcular(desde, hasta, dias))


def _calcular(desde, hasta, dias):
    docs = comprobantes(desde, hasta)
    por = defaultdict(list)
    for d in docs:
        por[d['cliente']].append(d)
    out = {cid: _metricas(ds, dias, hasta) for cid, ds in por.items()}
    # ABC por venta neta (80 / 15 / 5)
    orden = sorted((c for c in out.values() if c['neto'] > 0), key=lambda c: -c['neto'])
    total, acum = sum(c['neto'] for c in orden) or 1, 0
    for c in orden:
        acum += c['neto']
        c['abc'] = 'A' if acum <= .8 * total else 'B' if acum <= .95 * total else 'C'
    for c in out.values():
        c.setdefault('abc', '-')
        c['estado'] = estado(c, dias)
    return {'desde': desde.isoformat(), 'hasta': hasta.isoformat(), 'dias': dias, 'comprobantes': len(docs),
            'clientes': out, 'fuente': 'ventas_detalle'}


def detalle_cliente(cid, dias=90, hasta=None):
    """Serie semanal, últimos pedidos y artículos más comprados del cliente."""
    if not disponible():
        return {'desde': None, 'hasta': None, 'semanas': [], 'ultimos': [], 'articulos': []}
    desde, hasta = _ventana(dias, hasta)
    ds = sorted(comprobantes(desde, hasta, cid), key=lambda d: (d['fecha'], d['doc']))
    lunes0 = desde - timedelta(days=desde.weekday())
    semanas, d = [], lunes0
    while d <= hasta:
        semanas.append({'desde': d.isoformat(), 'bultos': 0.0, 'hl': 0.0, 'neto': 0, 'pedidos': 0})
        d += timedelta(days=7)
    for x in ds:
        s = semanas[(x['fecha'] - lunes0).days // 7]
        s['bultos'] += x['bultos']; s['hl'] += x['hl']; s['neto'] += x['neto']; s['pedidos'] += 1
    for s in semanas:
        s['bultos'], s['hl'], s['neto'] = round(s['bultos'], 1), round(s['hl'], 2), round(s['neto'])
    ultimos = [{'fecha': x['fecha'].isoformat(), 'doc': x['doc'], 'tipo': x['tipo'], 'origen': x['origen'],
                'bultos': round(x['bultos'], 1), 'hl': round(x['hl'], 2), 'neto': round(x['neto']),
                'rech': round(x['rech'], 1), 'motivo': x['motivo'] if x['rech'] > 0 else None} for x in reversed(ds[-10:])]
    arts = Session().execute(text(SQL_ARTICULOS), _params(desde, hasta, cliente=str(cid))).mappings()
    return {'desde': desde.isoformat(), 'hasta': hasta.isoformat(), 'semanas': semanas, 'ultimos': ultimos,
            'articulos': [{'articulo': a['articulo'], 'bultos': round(float(a['bultos'] or 0), 1),
                           'hl': round(float(a['hl'] or 0), 2)} for a in arts]}
