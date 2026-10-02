"""Ventas: carga desde ChessERP (o archivo JSON de la API) y métricas de comportamiento por cliente.

La API de comprobantes de Chess:
  * acepta como máximo un mes calendario por consulta  -> se parte el rango por mes
  * pagina de a 1000 comprobantes (nroLote)           -> se recorren todos los lotes
  * resumen = un registro por comprobante; detallado = un registro por artículo (trae bultos y HL)
"""
import calendar
import json
import re
import statistics as st
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from . import dias as D
from .db import Session
from .models import SyncLog, Venta, VentaArticulo

DOC_FACTURA = {"FCVTA", "PRVTA"}
DOC_NC = {"DVVTA", "PRDVO"}
RECHAZO_LOGISTICO = {"CERRADO", "SIN DINERO", "MERCADERIA CRUZADA ENTREGA", "NO PIDIO", "DIRECCION ERRONEA"}
WD = ["LU", "MA", "MI", "JU", "VI", "SA", "DO"]


# ---------------------------------------------------------------- carga
def _d(v):
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _key(x):
    return f"{x.get('idDocumento')}-{x.get('letra')}-{x.get('serie')}-{x.get('nrodoc')}"


def _filas(payload):
    if isinstance(payload, list):
        return payload
    ds = payload.get("dsReporteComprobantesApi", payload) if isinstance(payload, dict) else {}
    return ds.get("VentasResumen", []) if isinstance(ds, dict) else []


def guardar_filas(filas, sucursales=None):
    """Upsert de comprobantes. Acepta filas de resumen o de detalle (se detecta por 'idArticulo')."""
    s = Session()
    sucursales = {int(x) for x in sucursales or []}
    resumen, detalle = {}, defaultdict(list)
    for x in filas:
        if sucursales and _int(x.get("idSucursal")) not in sucursales:
            continue
        k = _key(x)
        if "idArticulo" in x:
            detalle[k].append(x)
        resumen.setdefault(k, x)
    existentes = {}
    claves = list(resumen)
    for i in range(0, len(claves), 500):
        existentes.update((v.id, v) for v in s.query(Venta).filter(Venta.id.in_(claves[i:i + 500])))
    if detalle:
        ids = list(detalle)
        for i in range(0, len(ids), 500):
            s.query(VentaArticulo).filter(VentaArticulo.venta_id.in_(ids[i:i + 500])).delete(synchronize_session=False)
    nuevos = 0
    for k, x in resumen.items():
        v = existentes.get(k)
        if v is None:
            v = Venta(id=k); s.add(v); nuevos += 1
        doc = x.get("idDocumento") or ""
        v.id_cliente = int(x.get("idCliente") or 0)
        v.id_sucursal = _int(x.get("idSucursal"))
        v.documento, v.es_nc = doc, doc in DOC_NC
        v.fecha = _d(x.get("fechaComprobate")) or _d(x.get("fechaAlta"))
        v.fecha_pedido, v.fecha_entrega = _d(x.get("fechaPedido")), _d(x.get("fechaEntrega"))
        v.origen = (x.get("origen") or "").strip()[:30] or None
        v.vendedor = (x.get("dsVendedor") or "").strip()[:120] or None
        v.fletero = (x.get("dsFleteroCarga") or "").strip()[:120] or None
        v.rechazo = (x.get("dsRechazo") or "").strip()[:120] or None
        v.anulado = str(x.get("anulado") or "").upper() == "SI"
        if k in detalle:   # en el detalle los importes vienen por línea: se suman
            lineas = detalle[k]
            v.neto = sum(float(l.get("subtotalNeto") or 0) for l in lineas)
            v.total = sum(float(l.get("subtotalFinal") or 0) for l in lineas)
            v.bultos = sum(float(l.get("cantidadesTotal") or 0) for l in lineas)
            v.hl = sum(float(l.get("unimedtotal") or 0) for l in lineas)
            arts = defaultdict(lambda: [0.0, 0.0, 0.0])
            for l in lineas:
                nom = (l.get("dsArticuloEstadistico") or l.get("dsArticulo") or "").strip()
                if not nom:
                    continue
                a = arts[nom[:160]]
                a[0] += float(l.get("cantidadesTotal") or 0); a[1] += float(l.get("unimedtotal") or 0); a[2] += float(l.get("subtotalNeto") or 0)
            for nom, (b, h, n) in arts.items():
                s.add(VentaArticulo(venta_id=k, articulo=nom, bultos=b, hl=h, neto=n))
        else:
            v.neto = float(x.get("subtotalNeto") or 0)
            v.total = float(x.get("subtotalFinal") or 0)
    s.commit()
    _cache.clear()
    return {"comprobantes": len(resumen), "nuevos": nuevos, "con_detalle": len(detalle)}


def importar_json(paths, sucursales=None):
    tot = Counter()
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            r = guardar_filas(_filas(json.load(fh)), sucursales)
        tot.update(r)
    return dict(tot)


def _meses(desde: date, hasta: date):
    d = desde
    while d <= hasta:
        fin = date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
        yield d, min(fin, hasta)
        d = fin + timedelta(days=1)


def sincronizar(desde: date, hasta: date, sucursales=None, detalle=False, client=None):
    from .chess import ChessClient
    client = client or ChessClient()
    s = Session()
    log = SyncLog(origen="chess-ventas" + ("-detalle" if detalle else ""), inicio=datetime.utcnow(),
                  leidos=0, nuevos=0, actualizados=0)
    s.add(log); s.commit()
    tot = Counter()
    try:
        client.login()
        for d1, d2 in _meses(desde, hasta):
            lote, total_lotes, pendiente = 1, None, []
            while total_lotes is None or lote <= total_lotes:
                payload = client.ventas_lote(d1, d2, lote, detalle)
                nuevas = _filas(payload)
                m = re.search(r"(\d+)\s*/\s*(\d+)", str(payload.get("cantComprobantesVentas", ""))) if isinstance(payload, dict) else None
                total_lotes = int(m.group(2)) if m else (lote if not nuevas else lote + 1)
                log.leidos += len(nuevas)
                filas = pendiente + nuevas
                pendiente = []
                if nuevas and detalle and lote < total_lotes:
                    # Las líneas del último comprobante pueden seguir en el lote siguiente:
                    # se guardan juntas para no sumar importes parciales.
                    ultima = _key(filas[-1])
                    pendiente = [f for f in filas if _key(f) == ultima]
                    filas = [f for f in filas if _key(f) != ultima]
                if filas:
                    tot.update(guardar_filas(filas, sucursales))
                if not nuevas:
                    break
                lote += 1
        log.nuevos = tot["nuevos"]
        log.actualizados = tot["comprobantes"] - tot["nuevos"]
        log.fin = datetime.utcnow()
        s.add(log); s.commit()
    except Exception as e:
        s.rollback()
        log = s.merge(log); log.error, log.fin = repr(e)[:2000], datetime.utcnow(); s.commit()
        raise
    return dict(tot)


# ---------------------------------------------------------------- métricas
_cache = {}


def _ventana(dias, hasta=None):
    s = Session()
    if hasta is None:
        ult = s.query(Venta.fecha).filter(Venta.fecha.isnot(None)).order_by(Venta.fecha.desc()).first()
        hasta = ult[0] if ult else date.today()
    return hasta - timedelta(days=dias - 1), hasta


def comportamiento(dias=60, hasta=None):
    """Métricas por cliente en la ventana [hasta-dias+1, hasta]. Devuelve dict con 'clientes' y 'resumen'."""
    desde, hasta = _ventana(dias, hasta)
    s = Session()
    n_ventas = s.query(Venta).count()
    ck = (dias, hasta, n_ventas)
    if ck in _cache:
        return _cache[ck]
    filas = (s.query(Venta).filter(Venta.fecha >= desde, Venta.fecha <= hasta, Venta.anulado.is_(False)).all())
    por = defaultdict(list)
    for v in filas:
        por[v.id_cliente].append(v)
    # bultos solo si casi todo el período se cargó con detalle (si no, los totales engañan)
    hay_bultos = bool(filas) and sum(v.bultos is not None for v in filas) / len(filas) >= .8
    mitad = hasta - timedelta(days=dias // 2)
    out = {}
    for cid, vs in por.items():
        fac = [v for v in vs if v.documento in DOC_FACTURA and v.neto > 0]
        nc = [v for v in vs if v.es_nc]
        fechas = sorted({v.fecha for v in fac})
        gaps = [(b - a).days for a, b in zip(fechas, fechas[1:])]
        neto_fac = sum(v.neto for v in fac)
        ent = Counter(WD[(v.fecha_entrega or v.fecha).weekday()] for v in fac)
        ped = Counter(WD[v.fecha_pedido.weekday()] for v in fac if v.fecha_pedido)
        rech = Counter(v.rechazo for v in nc if v.rechazo)
        rec = sum(v.neto for v in fac if v.fecha > mitad)
        ant = sum(v.neto for v in fac if v.fecha <= mitad)
        out[cid] = {
            "compras": len(fechas),
            "neto": round(neto_fac + sum(v.neto for v in nc)),
            "neto_fac": round(neto_fac),
            "nc": round(-sum(v.neto for v in nc)), "nc_n": len(nc),
            "ticket": round(neto_fac / len(fechas)) if fechas else 0,
            "bultos": round(sum(v.bultos or 0 for v in fac) + sum(v.bultos or 0 for v in nc), 1) if hay_bultos else None,
            "ultima": fechas[-1].isoformat() if fechas else None,
            "dias_sin": (hasta - fechas[-1]).days if fechas else None,
            "frec": round(st.median(gaps), 1) if gaps else None,
            "ent": dict(ent), "ped": dict(ped),
            "bees": round(sum(1 for v in fac if (v.origen or "") == "BEES") / len(fac), 2) if fac else 0,
            "tend": round((rec - ant) / ant, 2) if ant > 0 else None,
            "rech": dict(rech.most_common(4)),
            "fallidas": sum(n for r, n in rech.items() if r in RECHAZO_LOGISTICO),
        }
    # ABC por venta neta (80 / 15 / 5)
    orden = sorted((c for c in out.values() if c["neto"] > 0), key=lambda c: -c["neto"])
    total = sum(c["neto"] for c in orden) or 1
    acum = 0
    for c in orden:
        acum += c["neto"]
        c["abc"] = "A" if acum <= .8 * total else "B" if acum <= .95 * total else "C"
    for c in out.values():
        c.setdefault("abc", "-")
        c["estado"] = estado(c, dias)
    res = {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "dias": dias, "hay_bultos": hay_bultos,
           "comprobantes": len(filas), "clientes": out}
    _cache.clear(); _cache[ck] = res
    return res


def estado(c, dias):
    if not c["compras"]:
        return "sin_compras"
    lim_inactivo = min(45, dias - 7)
    if c["dias_sin"] is not None and c["dias_sin"] > lim_inactivo:
        return "inactivo"
    if c["frec"] and c["dias_sin"] > max(2.5 * c["frec"], 21):
        return "riesgo"
    return "activo"


def detalle_cliente(cid, dias=90, hasta=None):
    """Serie semanal, últimos comprobantes y artículos más comprados (para la ficha)."""
    desde, hasta = _ventana(dias, hasta)
    s = Session()
    vs = (s.query(Venta).filter(Venta.id_cliente == cid, Venta.fecha >= desde, Venta.fecha <= hasta,
                                Venta.anulado.is_(False)).order_by(Venta.fecha).all())
    hay_bultos = bool(vs) and sum(v.bultos is not None for v in vs) / len(vs) >= .8
    lunes0 = desde - timedelta(days=desde.weekday())
    semanas = []
    d = lunes0
    while d <= hasta:
        semanas.append({"desde": d.isoformat(), "neto": 0, "bultos": 0, "compras": 0})
        d += timedelta(days=7)
    for v in vs:
        i = (v.fecha - lunes0).days // 7
        if 0 <= i < len(semanas):
            semanas[i]["neto"] += round(v.neto)
            semanas[i]["bultos"] += round(v.bultos or 0, 1)
            if v.documento in DOC_FACTURA and v.neto > 0:
                semanas[i]["compras"] += 1
    ids = [v.id for v in vs]
    arts = Counter()
    if ids:
        for a in s.query(VentaArticulo).filter(VentaArticulo.venta_id.in_(ids)):
            arts[a.articulo] += a.bultos
    ult = [{"fecha": v.fecha.isoformat(), "entrega": v.fecha_entrega.isoformat() if v.fecha_entrega else None,
            "doc": v.documento, "nc": v.es_nc, "neto": round(v.neto), "bultos": v.bultos, "origen": v.origen,
            "rechazo": v.rechazo, "fletero": v.fletero} for v in reversed(vs[-12:])]
    return {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "hay_bultos": hay_bultos, "semanas": semanas, "ultimos": ult,
            "articulos": [{"articulo": k, "bultos": round(b, 1)} for k, b in arts.most_common(8)]}


def sugerencia_dias(c, asignados):
    """Días en los que más recibe (≥20% de sus entregas) y si la frecuencia justifica los días asignados."""
    ent = c.get("ent") or {}
    tot = sum(ent.values())
    if tot < 3:
        return None
    top = [d for d in D.DIAS if ent.get(d, 0) / tot >= .2]
    en_dia = sum(n for d, n in ent.items() if d in asignados) / tot
    return {"dias": "".join(top), "en_dia": round(en_dia, 2)}
