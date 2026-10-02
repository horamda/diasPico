"""Lógica de negocio: vista de clientes, alertas, carga por camión y export BEES."""
import csv
import io
import math
from collections import defaultdict
from datetime import datetime
from statistics import median

from . import dias as D
from .db import Session
from .models import CambioLog, Cliente, ClienteEntrega, Deposito, Localidad, Vehiculo
from .localidades import normalizar_nombre, sucursal_entrega, SUCURSAL_POR_LOCALIDAD

LEJOS_KM = 15            # distancia al centro de la localidad para marcar "ubicación a revisar"
BEES_DDC_ID = "1369280004"
BEES_PREFIJO = 13692800000000  # Vendor_Account_ID = prefijo + nº de cliente


def _km(a, b):
    dlat = (a[0] - b[0]) * 111.0
    dlng = (a[1] - b[1]) * 111.0 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dlat, dlng)


def _valida(lat, lng):
    # Rango amplio de la provincia de Buenos Aires; descarta 0,0 y coordenadas invertidas.
    return lat is not None and lng is not None and -41.5 < lat < -33 and -63.5 < lng < -56


def clientes_vista(incluir_anulados=True):
    """Lista de dicts lista para el mapa, con la ubicación/días efectivos y banderas de alerta."""
    s = Session()
    locs = {normalizar_nombre(l.nombre): l for l in s.query(Localidad)}
    out = []
    for c in s.query(Cliente).all():
        if c.anulado and not incluir_anulados:
            continue
        e = c.entrega
        lat = e.lat if e and e.lat is not None else c.lat
        lng = e.lng if e and e.lng is not None else c.lng
        nombre_localidad = normalizar_nombre(c.localidad_erp)
        loc = locs.get(nombre_localidad)
        out.append({
            "id": c.id_cliente, "n": c.fantasia or c.razon_social or "", "rs": c.razon_social or "",
            "dom": c.domicilio or "", "loc": nombre_localidad or "SIN LOCALIDAD",
            "suc": sucursal_entrega(nombre_localidad, loc.deposito.nombre if loc and loc.deposito else None),
            "d": D.normalizar(e.dias) if e else "", "de": c.dias_erp or "",
            "an": c.anulado, "ven": c.vendedor or "", "rv": c.ruta_venta or "",
            "h": c.horario or "", "pl": bool(e and e.en_planilla),
            "lat": lat if _valida(lat, lng) else None, "lng": lng if _valida(lat, lng) else None,
            "geo_mal": lat is not None and not _valida(lat, lng),
            "corr": bool(e and e.lat is not None), "pend": bool(e and e.pendiente_bees),
            "nota": (e.nota if e else None) or "",
        })
    # ubicación a revisar: lejos de la mediana de su localidad
    por_loc = defaultdict(list)
    for c in out:
        if c["lat"] is not None:
            por_loc[c["loc"]].append((c["lat"], c["lng"]))
    centro = {k: (median(p[0] for p in v), median(p[1] for p in v)) for k, v in por_loc.items() if len(v) >= 3}
    for c in out:
        c["far"] = bool(c["geo_mal"] or (c["lat"] is not None and not c["corr"] and c["loc"] in centro
                                       and _km((c["lat"], c["lng"]), centro[c["loc"]]) > LEJOS_KM))
    return out


def plan_vista():
    s = Session()
    plan = {
        "depositos": [d.to_dict() for d in s.query(Deposito).order_by(Deposito.nombre)],
        "localidades": [l.to_dict() for l in s.query(Localidad).order_by(Localidad.nombre)],
        "vehiculos": [v.to_dict() for v in s.query(Vehiculo).filter_by(activo=True).order_by(Vehiculo.deposito_id, Vehiculo.nombre)],
        "dias": D.DIAS,
    }
    deps = {normalizar_nombre(d['nombre']): d for d in plan['depositos']}
    for name in sorted(set(SUCURSAL_POR_LOCALIDAD.values())):
        if name not in deps:
            dep = {'id': None, 'nombre': name, 'direccion': None, 'lat': None, 'lng': None}
            plan['depositos'].append(dep)
            deps[name] = dep
    for dep in plan['depositos']:
        dep['nombre'] = normalizar_nombre(dep['nombre'])
    locs = {}
    for loc in plan['localidades']:
        loc['nombre'] = normalizar_nombre(loc['nombre'])
        branch = sucursal_entrega(loc['nombre'], loc['deposito'])
        loc['deposito'] = branch
        loc['deposito_id'] = deps.get(branch, {}).get('id')
        locs[loc['nombre']] = loc
    for name, branch in SUCURSAL_POR_LOCALIDAD.items():
        if name not in locs:
            locs[name] = {'id': None, 'nombre': name, 'deposito': branch,
                          'deposito_id': deps[branch]['id'], 'lat': None, 'lng': None}
    plan['localidades'] = sorted(locs.values(), key=lambda l: l['nombre'])
    for vehicle in plan['vehiculos']:
        vehicle['deposito'] = normalizar_nombre(vehicle['deposito'])
        vehicle['plan'] = {day: list(dict.fromkeys(normalizar_nombre(l) for l in names))
                           for day, names in vehicle['plan'].items()}
    return plan


def resumen(clientes, incluir_inactivos=False):
    """Totales generales y por localidad (lo que pedía la planilla)."""
    act = [c for c in clientes if incluir_inactivos or not c["an"]]
    filas = {}
    for c in act:
        f = filas.setdefault((c["suc"], c["loc"]), {"suc": c["suc"], "loc": c["loc"], "clientes": 0, "geo": 0,
                                                    "sin_geo": 0, "sin_dias": 0, "revisar": 0, **{d: 0 for d in D.DIAS}})
        f["clientes"] += 1
        f["geo" if c["lat"] is not None else "sin_geo"] += 1
        f["sin_dias"] += not c["d"]
        f["revisar"] += c["far"]
        for d in D.lista(c["d"]):
            f[d] += 1
    return {
        "activos": sum(not c["an"] for c in act),
        "clientes": len(act),
        "geolocalizados": sum(c["lat"] is not None for c in act),
        "sin_geo": sum(c["lat"] is None for c in act),
        "sin_dias": sum(not c["d"] for c in act),
        "revisar": sum(c["far"] for c in act),
        "anulados_con_dias": sum(1 for c in clientes if c["an"] and c["d"]),
        "distinto_erp": sum(1 for c in act if c["d"] != c["de"]),
        "pendientes_bees": sum(1 for c in act if c["pend"]),
        "por_localidad": sorted(filas.values(), key=lambda f: (f["suc"], -f["clientes"])),
    }


def carga_por_dia(clientes, plan, incluir_inactivos=False):
    """Clientes a entregar por vehículo y día, y los que tienen día pero ningún camión pasa por su localidad."""
    act = [c for c in clientes if incluir_inactivos or not c["an"]]
    res = {}
    for dia in D.DIAS:
        cubiertas, vehs = set(), []
        usos = defaultdict(int)
        for v in plan["vehiculos"]:
            for l in v["plan"].get(dia, []):
                usos[(v['deposito'], l)] += 1
        for v in plan["vehiculos"]:
            paradas = v["plan"].get(dia, [])
            cubiertas.update((v['deposito'], l) for l in paradas)
            det = [{"loc": l, "n": sum(1 for c in act if c['suc'] == v['deposito'] and c["loc"] == l and dia in c["d"]), "compartida": usos[(v['deposito'], l)] > 1}
                   for l in paradas]
            vehs.append({"id": v["id"], "nombre": v["nombre"], "deposito": v["deposito"], "color": v["color"],
                         "capacidad": v["capacidad_clientes"], "paradas": det, "total": sum(x["n"] for x in det)})
        huerf = defaultdict(int)
        for c in act:
            if dia in c["d"] and (c['suc'], c["loc"]) not in cubiertas:
                huerf[c["loc"]] += 1
        res[dia] = {"vehiculos": vehs, "sin_camion": [{"loc": k, "n": v} for k, v in sorted(huerf.items())]}
    return res


def actualizar_cliente(id_cliente, data, usuario=None):
    """data puede traer: dias, lat, lng (None para volver a la del ERP), nota."""
    s = Session()
    c = s.get(Cliente, id_cliente)
    if c is None:
        raise KeyError(id_cliente)
    e = c.entrega or ClienteEntrega(id_cliente=id_cliente, dias="", en_planilla=False)
    s.add(e)

    def log(campo, antes, despues):
        if str(antes) != str(despues):
            s.add(CambioLog(id_cliente=id_cliente, campo=campo, antes=None if antes is None else str(antes),
                            despues=None if despues is None else str(despues), usuario=usuario))
            return True
        return False

    if "dias" in data:
        nuevo = D.normalizar(data["dias"])
        if log("dias", e.dias, nuevo):
            e.dias = nuevo
            e.pendiente_bees = True
    if "lat" in data or "lng" in data:
        lat, lng = data.get("lat"), data.get("lng")
        if lat is not None and lng is not None and not _valida(float(lat), float(lng)):
            raise ValueError("Coordenadas fuera de la provincia de Buenos Aires")
        log("ubicacion", f"{e.lat},{e.lng}", f"{lat},{lng}")
        e.lat = None if lat is None else float(lat)
        e.lng = None if lng is None else float(lng)
    if "nota" in data:
        log("nota", e.nota, data["nota"])
        e.nota = data["nota"] or None
    e.actualizado, e.actualizado_por = datetime.utcnow(), usuario
    s.commit()
    return True


def guardar_plan_vehiculo(vehiculo_id, plan: dict, usuario=None):
    """plan = {"LU": ["DOLORES", ...], ...}. Reemplaza el plan completo del vehículo."""
    from .models import PlanRuta
    s = Session()
    v = s.get(Vehiculo, vehiculo_id)
    if v is None:
        raise KeyError(vehiculo_id)
    locs = {l.nombre: l for l in s.query(Localidad)}
    antes = v.to_dict()["plan"]
    for dia, nombres in plan.items():
        for nombre in nombres:
            if nombre not in locs:
                raise ValueError(f"Localidad desconocida: {nombre}")
            if locs[nombre].deposito_id not in (None, v.deposito_id):
                raise ValueError(f"La localidad {nombre} pertenece a otro depósito")
    v.paradas.clear()
    s.flush()
    for dia, lista in plan.items():
        if dia not in D.DIAS:
            continue
        for i, nombre in enumerate(lista, 1):
            if nombre not in locs:
                raise ValueError(f"Localidad desconocida: {nombre}")
            v.paradas.append(PlanRuta(dia=dia, localidad_id=locs[nombre].id, orden=i))
    s.add(CambioLog(entidad="vehiculo", campo=f"plan:{v.id}", antes=str(antes), despues=str(plan), usuario=usuario))
    s.commit()


# ---------- export BEES (mismo formato que la hoja subirModificado) ----------
BEES_HEAD = (["DDC_ID", "ERP_POC_ID", "Vendor_Account_ID", "Settings_Type"] + D.BEES_COLS
             + [f"Minimum_Order_Value_{d}" for d in D.BEES_COLS] + [f"Additional_Fee_{d}" for d in D.BEES_COLS]
             + ["Delivery_Frequency", "Reference_Date", "Click_And_Collect", "Audience_Name"])


def filas_bees(solo_pendientes=False, minimo=0, fee=0):
    out = []
    for c in clientes_vista(incluir_anulados=False):
        if solo_pendientes and not c["pend"]:
            continue
        out.append([BEES_DDC_ID, "", BEES_PREFIJO + c["id"], "POC-level", *D.a_bees(c["d"]),
                    *([minimo] * 7), *([fee] * 7), "WEEKLY", "", "NO", ""])
    return out


def bees_csv(**kw):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(BEES_HEAD)
    w.writerows(filas_bees(**kw))
    return buf.getvalue()


def bees_xlsx(**kw):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "subirModificado"
    ws.append(BEES_HEAD)
    for r in filas_bees(**kw):
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def marcar_exportados():
    s = Session()
    s.query(ClienteEntrega).filter_by(pendiente_bees=True).update({"pendiente_bees": False})
    s.commit()
