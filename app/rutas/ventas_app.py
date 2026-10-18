"""Pedidos y volumen por cliente desde ventas_detalle, la tabla de ventas que ya carga el portal.

Mismas reglas que Drop Size y Días Pico:
  * se excluyen remitos (REMIT) y comodatos (COMOD);
  * bultos y HL cuentan solo artículos de tipo mercadería (sin envases ni esqueletos);
  * una compra es un día con comprobantes del cliente: varios comprobantes el mismo día son UNA compra.
    La cantidad de comprobantes queda como dato secundario.
RMCYO cuenta como compra y volumen; no tiene importe, así que no suma venta en $.
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
PALLETS = f"CASE WHEN {MERC} AND COALESCE(a.bultos_por_pallet, 0) > 0 THEN 1.0 * COALESCE(v.bultos, 0) / a.bultos_por_pallet ELSE 0 END"
SIN_BXP = f"CASE WHEN {MERC} AND COALESCE(a.bultos_por_pallet, 0) <= 0 THEN ABS(COALESCE(v.bultos, 0)) ELSE 0 END"
SQL_DOCS = f"""
SELECT TRIM(v.cliente) AS cliente, v.fecha AS fecha, {DOC_KEY} AS doc,
       MAX(UPPER(TRIM(COALESCE(v.documento, '')))) AS tipo,
       MAX(TRIM(COALESCE(v.origen, ''))) AS origen,
       SUM(CASE WHEN {MERC} THEN COALESCE(v.bultos, 0) ELSE 0 END) AS bultos,
       SUM(CASE WHEN {MERC} THEN COALESCE(v.unidad_medida, 0) ELSE 0 END) AS hl,
       SUM({PALLETS}) AS pallets, SUM({SIN_BXP}) AS bultos_sin_bxp,
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
       SUM(COALESCE(v.bultos, 0)) AS bultos, SUM(COALESCE(v.unidad_medida, 0)) AS hl,
       SUM({PALLETS}) AS pallets, SUM({SIN_BXP}) AS bultos_sin_bxp
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
                    'pallets': float(r['pallets'] or 0), 'bultos_sin_bxp': float(r['bultos_sin_bxp'] or 0),
                    'neto': float(r['neto'] or 0), 'rech': float(r['rech'] or 0), 'motivo': r['motivo']})
    return out


def _metricas(ds, dias, hasta):
    pedidos = [d for d in ds if d['tipo'] in DOC_VENTA | {'RMCYO'} and (d['bultos'] > 0 or d['neto'] > 0)]
    fechas = sorted({d['fecha'] for d in pedidos})
    gaps = [(b - a).days for a, b in zip(fechas, fechas[1:])]
    dias_venta = {d['fecha'] for d in pedidos if d['tipo'] in DOC_VENTA}
    bultos, hl = sum(d['bultos'] for d in ds), sum(d['hl'] for d in ds)
    pallets = sum(d['pallets'] for d in ds)
    sin_bxp = sum(d['bultos_sin_bxp'] for d in ds)
    neto, rech = sum(d['neto'] for d in ds), sum(d['rech'] for d in ds)
    mitad = hasta - timedelta(days=dias // 2)
    rec = sum(d['bultos'] for d in ds if d['fecha'] > mitad)
    ant = sum(d['bultos'] for d in ds if d['fecha'] <= mitad)
    motivos = Counter(d['motivo'] for d in ds if d['motivo'] and d['rech'] > 0)
    return {
        'compras': len(fechas),                      # días con comprobantes: 1 compra por día
        'comprobantes': len({d['doc'] for d in ds}),
        'bultos': round(bultos, 1), 'hl': round(hl, 2), 'neto': round(neto),
        'ticket': round(neto / len(dias_venta)) if dias_venta else 0,   # venta neta por compra
        'drop': round(bultos / len(fechas), 1) if fechas else 0,
        'drop_hl': round(hl / len(fechas), 2) if fechas else 0,
        'pallets': round(pallets, 4), 'bultos_sin_bxp': round(sin_bxp, 2),
        'drop_pallets': round(pallets / len(fechas), 4) if fechas else 0,
        'hl_sem': round(hl / (dias / 7), 2),
        'pallets_sem': round(pallets / (dias / 7), 4),
        'bultos_sem': round(bultos / (dias / 7), 1),
        'rech': round(rech, 1), 'rech_pct': round(rech / bultos, 3) if bultos else 0,
        'motivos': dict(motivos.most_common(3)),
        'ultima': fechas[-1].isoformat() if fechas else None,
        'dias_sin': (hasta - fechas[-1]).days if fechas else None,
        'frec': round(st.median(gaps), 1) if gaps else None,
        'ent': dict(Counter(WD[f.weekday()] for f in fechas)),
        'bees': round(len({d['fecha'] for d in pedidos if d['origen'] == 'BEES'}) / len(fechas), 2) if fechas else 0,
        'tend': round((rec / (dias // 2)) / (ant / (dias - dias // 2)) - 1, 2) if ant > 0 else None,
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
    historial = historial_actividad(hasta)
    for cid in historial:
        out.setdefault(cid, _metricas([], dias, hasta))
    for cid, c in out.items():
        c.setdefault('abc', '-')
        h = historial.get(cid, {})
        c['ultima'] = h.get('ultima')
        c['dias_sin'] = h.get('dias_sin')
        c['frec_hist'] = h.get('frec')
        c['estado'] = estado({'compras': bool(h), 'dias_sin': c['dias_sin'], 'frec': c['frec_hist']}, dias)
    return {'desde': desde.isoformat(), 'hasta': hasta.isoformat(), 'dias': dias, 'comprobantes': len(docs),
            'clientes': out, 'fuente': 'ventas_detalle'}


def historial_actividad(hasta):
    """Última compra histórica y frecuencia en 120 días; independientes del selector."""
    def calcular():
        sql = f"""SELECT TRIM(v.cliente) AS cliente, MAX(v.fecha) AS ultima
            FROM ventas_detalle v WHERE {FILTROS}
            AND UPPER(TRIM(v.documento)) IN ('FCVTA', 'PRVTA', 'RMCYO')
            AND (COALESCE(v.bultos, 0) > 0 OR COALESCE(v.importe_neto, 0) > 0)
            GROUP BY TRIM(v.cliente)"""
        out = {}
        for r in Session().execute(text(sql), _params(date(1900, 1, 1), hasta)).mappings():
            cid = str(r['cliente'] or '').strip()
            if cid.isdecimal():
                ultima = _d(r['ultima'])
                out[int(cid)] = {'ultima': ultima.isoformat(), 'dias_sin': (hasta - ultima).days, 'frec': None}
        por = defaultdict(set)
        for d in comprobantes(hasta - timedelta(days=119), hasta):
            if d['tipo'] in DOC_VENTA | {'RMCYO'} and (d['bultos'] > 0 or d['neto'] > 0):
                por[d['cliente']].add(d['fecha'])
        for cid, fs in por.items():
            fs = sorted(fs)
            if cid in out and len(fs) >= 3:
                out[cid]['frec'] = round(st.median((b - a).days for a, b in zip(fs, fs[1:])), 1)
        return out
    return _memo(('actividad', hasta), calcular)


def fechas_compra(dias=90, hasta=None):
    """Días con venta (factura o pedido) de cada cliente, para medir la efectividad de visita.
    Cada día va como [fecha, 1 si todas las ventas de ese día entraron por BEES]."""
    if not disponible():
        return {'desde': None, 'hasta': None, 'dias': dias, 'clientes': {}}
    desde, hasta = _ventana(dias, hasta)

    def calcular():
        por = defaultdict(dict)
        for d in comprobantes(desde, hasta):
            if d['tipo'] not in DOC_VENTA:
                continue
            f = d['fecha'].isoformat()
            por[d['cliente']][f] = por[d['cliente']].get(f, True) and d['origen'] == 'BEES'
        return {'desde': desde.isoformat(), 'hasta': hasta.isoformat(), 'dias': dias,
                'clientes': {cid: [[f, int(b)] for f, b in sorted(fs.items())] for cid, fs in por.items()}}
    return _memo(('fechas', dias, hasta), calcular)


def detalle_cliente(cid, dias=90, hasta=None):
    """Serie semanal, últimas compras (una por día) y artículos más comprados del cliente."""
    if not disponible():
        return {'desde': None, 'hasta': None, 'semanas': [], 'ultimos': [], 'articulos': []}
    desde, hasta = _ventana(dias, hasta)
    ds = sorted(comprobantes(desde, hasta, cid), key=lambda d: (d['fecha'], d['doc']))
    lunes0 = desde - timedelta(days=desde.weekday())
    semanas, d = [], lunes0
    while d <= hasta:
        semanas.append({'desde': d.isoformat(), 'bultos': 0.0, 'hl': 0.0, 'pallets': 0.0, 'bultos_sin_bxp': 0.0, 'neto': 0, 'compras': set()})
        d += timedelta(days=7)
    # Una compra por día: se agrupan los comprobantes del mismo día.
    por_dia = {}
    for x in ds:
        s = semanas[(x['fecha'] - lunes0).days // 7]
        s['bultos'] += x['bultos']; s['hl'] += x['hl']; s['neto'] += x['neto']
        if x['tipo'] in DOC_VENTA | {'RMCYO'} and (x['bultos'] > 0 or x['neto'] > 0):
            s['compras'].add(x['fecha'])
        c = por_dia.setdefault(x['fecha'], {'fecha': x['fecha'].isoformat(), 'docs': [], 'tipos': set(), 'origenes': set(),
                                            'bultos': 0.0, 'hl': 0.0, 'pallets': 0.0, 'bultos_sin_bxp': 0.0, 'neto': 0.0, 'rech': 0.0, 'motivos': set()})
        for key in ('pallets', 'bultos_sin_bxp'):
            s[key] += x[key]
            c[key] += x[key]
        c['docs'].append(x['doc']); c['tipos'].add(x['tipo']); c['origenes'].add(x['origen'])
        c['bultos'] += x['bultos']; c['hl'] += x['hl']; c['neto'] += x['neto']; c['rech'] += x['rech']
        if x['motivo'] and x['rech'] > 0:
            c['motivos'].add(x['motivo'])
    for s in semanas:
        s['pallets'] = round(s['pallets'], 4)
        s['bultos_sin_bxp'] = round(s['bultos_sin_bxp'], 2)
        s['bultos'], s['hl'], s['neto'], s['compras'] = round(s['bultos'], 1), round(s['hl'], 2), round(s['neto']), len(s['compras'])
    ultimos = [{'fecha': c['fecha'], 'comprobantes': len(c['docs']), 'docs': c['docs'],
                'tipo': '+'.join(sorted(c['tipos'])), 'origen': ', '.join(sorted(o for o in c['origenes'] if o)),
                'bultos': round(c['bultos'], 1), 'hl': round(c['hl'], 2), 'neto': round(c['neto']),
                'pallets': round(c['pallets'], 4), 'bultos_sin_bxp': round(c['bultos_sin_bxp'], 2),
                'rech': round(c['rech'], 1), 'motivo': ', '.join(sorted(c['motivos'])) or None}
               for c in sorted(por_dia.values(), key=lambda c: c['fecha'], reverse=True)[:10]]
    arts = Session().execute(text(SQL_ARTICULOS), _params(desde, hasta, cliente=str(cid))).mappings()
    return {'desde': desde.isoformat(), 'hasta': hasta.isoformat(), 'semanas': semanas, 'ultimos': ultimos,
            'articulos': [{'articulo': a['articulo'], 'bultos': round(float(a['bultos'] or 0), 1),
                           'hl': round(float(a['hl'] or 0), 2),
                           'pallets': round(float(a['pallets'] or 0), 4),
                           'bultos_sin_bxp': round(float(a['bultos_sin_bxp'] or 0), 2)} for a in arts]}
