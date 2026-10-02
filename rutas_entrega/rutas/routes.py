import hmac
import os
from datetime import date
from functools import wraps

from flask import Response, abort, current_app, jsonify, render_template, request

from . import bp, services as S
from .db import Session
from .models import CambioLog, Deposito, Localidad, SyncLog, Vehiculo


def _usuario():
    fn = current_app.config.get("RUTAS_USUARIO")
    try:
        return fn() if fn else request.headers.get("X-User") or request.remote_addr
    except Exception:
        return None


def protegido(f):
    """Aplica el decorador de login de la app anfitriona si se configuró."""
    @wraps(f)
    def wrapper(*a, **kw):
        deco = current_app.config.get("RUTAS_LOGIN_REQUIRED")
        return (deco(f) if deco else f)(*a, **kw)
    return wrapper


def _json():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "Se esperaba un JSON")
    return data


@bp.errorhandler(400)
@bp.errorhandler(404)
def _err(e):
    if "/api/" in request.path:
        return jsonify(error=getattr(e, "description", str(e))), e.code
    return e


# ---------- páginas ----------
@bp.get("/")
@protegido
def mapa():
    return render_template("rutas/mapa.html")


@bp.get("/plan")
@protegido
def plan_page():
    return render_template("rutas/plan.html")


# ---------- API de lectura ----------
@bp.get("/api/datos")
@protegido
def api_datos():
    """Todo lo que necesita el mapa en un solo pedido."""
    cl = S.clientes_vista()
    plan = S.plan_vista()
    ultima = Session().query(SyncLog).filter(SyncLog.error.is_(None)).order_by(SyncLog.fin.desc()).first()
    return jsonify(clientes=cl, plan=plan, resumen=S.resumen(cl), carga=S.carga_por_dia(cl, plan),
                   ultima_sync={"origen": ultima.origen, "fin": ultima.fin.isoformat() if ultima and ultima.fin else None}
                   if ultima else None)


@bp.get("/api/resumen")
@protegido
def api_resumen():
    return jsonify(S.resumen(S.clientes_vista()))


@bp.get("/api/clientes/<int:cid>/historial")
@protegido
def api_historial(cid):
    rows = (Session().query(CambioLog).filter_by(id_cliente=cid).order_by(CambioLog.fecha.desc()).limit(50))
    return jsonify([{"campo": r.campo, "antes": r.antes, "despues": r.despues, "usuario": r.usuario,
                     "fecha": r.fecha.isoformat()} for r in rows])


# ---------- API de edición ----------
@bp.patch("/api/clientes/<int:cid>")
@protegido
def api_cliente(cid):
    try:
        S.actualizar_cliente(cid, _json(), usuario=_usuario())
    except KeyError:
        abort(404, "Cliente inexistente")
    except ValueError as e:
        abort(400, str(e))
    return jsonify(ok=True, cliente=next(c for c in S.clientes_vista() if c["id"] == cid))


@bp.put("/api/vehiculos/<int:vid>/plan")
@protegido
def api_plan(vid):
    try:
        S.guardar_plan_vehiculo(vid, _json(), usuario=_usuario())
    except KeyError:
        abort(404, "Vehículo inexistente")
    except ValueError as e:
        abort(400, str(e))
    return jsonify(ok=True)


@bp.post("/api/vehiculos")
@protegido
def api_vehiculo_nuevo():
    d = _json()
    s = Session()
    dep = s.get(Deposito, d.get("deposito_id"))
    if not dep or not d.get("nombre"):
        abort(400, "Falta depósito o nombre")
    v = Vehiculo(deposito_id=dep.id, nombre=d["nombre"], patente=d.get("patente"),
                 capacidad_clientes=d.get("capacidad_clientes"), color=d.get("color") or "#c4561e")
    s.add(v); s.commit()
    return jsonify(ok=True, id=v.id)


@bp.patch("/api/vehiculos/<int:vid>")
@protegido
def api_vehiculo(vid):
    s = Session()
    v = s.get(Vehiculo, vid) or abort(404)
    d = _json()
    for k in ("nombre", "patente", "capacidad_clientes", "color", "activo"):
        if k in d:
            setattr(v, k, d[k])
    s.commit()
    return jsonify(ok=True)


@bp.put("/api/localidades/<int:lid>")
@protegido
def api_localidad(lid):
    s = Session()
    l = s.get(Localidad, lid) or abort(404)
    d = _json()
    for k in ("deposito_id", "lat", "lng"):
        if k in d:
            setattr(l, k, d[k])
    s.commit()
    return jsonify(ok=True)


@bp.post("/api/localidades")
@protegido
def api_localidad_nueva():
    d = _json()
    s = Session()
    if not d.get("nombre"):
        abort(400, "Falta nombre")
    l = Localidad(nombre=d["nombre"].strip().upper(), deposito_id=d.get("deposito_id"), lat=d.get("lat"), lng=d.get("lng"))
    s.add(l); s.commit()
    return jsonify(ok=True, id=l.id)


@bp.put("/api/depositos/<int:did>")
@protegido
def api_deposito(did):
    s = Session()
    dep = s.get(Deposito, did) or abort(404)
    d = _json()
    for k in ("direccion", "lat", "lng"):
        if k in d:
            setattr(dep, k, d[k])
    s.commit()
    return jsonify(ok=True)


# ---------- export BEES ----------
@bp.get("/export/bees.<fmt>")
@protegido
def export_bees(fmt):
    solo = request.args.get("solo_pendientes") == "1"
    nombre = f"bees_dias_entrega_{date.today():%Y%m%d}{'_cambios' if solo else ''}"
    if fmt == "csv":
        out = Response(S.bees_csv(solo_pendientes=solo), mimetype="text/csv")
    elif fmt == "xlsx":
        out = Response(S.bees_xlsx(solo_pendientes=solo),
                       mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        abort(404)
    out.headers["Content-Disposition"] = f'attachment; filename="{nombre}.{fmt}"'
    return out


@bp.post("/api/bees/marcar-exportados")
@protegido
def api_marcar_exportados():
    S.marcar_exportados()
    return jsonify(ok=True)


# ---------- sync por HTTP (para cron de Railway) ----------
@bp.post("/api/sync")
def api_sync():
    token = current_app.config.get("RUTAS_SYNC_TOKEN") or os.environ.get("RUTAS_SYNC_TOKEN")
    dado = request.headers.get("X-Sync-Token", "")
    if not token or not hmac.compare_digest(token, dado):
        abort(403)
    from .sync import sincronizar_chess
    return jsonify(sincronizar_chess())
