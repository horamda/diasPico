from functools import wraps

from flask import abort, current_app, jsonify, render_template, request

from . import bp, import_bp, services as S
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
        try:
            return (deco(f) if deco else f)(*a, **kw)
        except ValueError as exc:
            Session().rollback()
            return jsonify(error=str(exc)), 400
        except Exception as exc:
            from sqlalchemy.exc import IntegrityError
            Session().rollback()
            if isinstance(exc, IntegrityError):
                return jsonify(error='El registro está duplicado o la referencia no existe.'), 400
            raise
    return wrapper


def _json():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "Se esperaba un JSON")
    from .validation import validar
    validar(request.endpoint, data)
    return data


def audit_fields(entity, obj, data, fields):
    for key in fields:
        if key in data:
            before = getattr(obj, key)
            after = data[key]
            if before != after:
                Session().add(CambioLog(entidad=entity, campo=f'{key}:{obj.id}',
                                       antes=str(before), despues=str(after), usuario=_usuario()))
            setattr(obj, key, after)


@import_bp.errorhandler(500)
@bp.errorhandler(500)
def internal_error(e):
    Session().rollback()
    return jsonify(error='No se pudo completar la operación. Reintentá en unos segundos.'), 500


@import_bp.post('/api/actualizar-maestro')
@protegido
def actualizar_maestro():
    from .maestro import actualizar_desde_maestro
    try:
        return jsonify(ok=True, **actualizar_desde_maestro(_usuario()))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@import_bp.errorhandler(400)
@import_bp.errorhandler(404)
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


@import_bp.get('/dias')
@protegido
def importar_dias_page():
    return render_template('rutas/importar_dias.html')


@import_bp.post('/api/importar-dias/preview')
@protegido
def importar_dias_preview():
    from .importar_dias import MAX_BYTES, preparar
    from flask import g
    from werkzeug.formparser import parse_form_data
    _, form, files = parse_form_data(request.environ, max_content_length=MAX_BYTES + 65536,
                                    max_form_memory_size=128 * 1024)
    file = files.get('archivo')
    try:
        if not file or not file.filename.lower().endswith('.csv'):
            return jsonify(error='Seleccioná un archivo CSV.'), 400
        return jsonify(preparar(file.read(MAX_BYTES + 1), file.filename, str(g.portal_user['id']),
                               form.get('modo', 'vacios'), actor=_usuario()))
    finally:
        for _, uploaded in files.items(multi=True):
            uploaded.close()


@import_bp.post('/api/importar-dias/confirmar')
@protegido
def importar_dias_confirmar():
    from .importar_dias import confirmar, VistaDesactualizada
    from flask import g
    try:
        return jsonify(confirmar(_json().get('token'), str(g.portal_user['id'])))
    except VistaDesactualizada as exc:
        return jsonify(error=str(exc)), 409


# ---------- API de lectura ----------
@import_bp.get('/recorridos')
@protegido
def importar_rutas_page():
    return render_template('rutas/importar_rutas.html')


@import_bp.get('/recorridos/plantilla.csv')
@protegido
def plantilla_rutas():
    from flask import Response
    content = ('\ufeffSUCURSAL;VEHICULO;DIA;LOCALIDAD;ORDEN\r\n'
               'CHASCOMUS;CAMION 1;LUNES;CASTELLI;1\r\n'
               'CHASCOMUS;CAMION 1;LUNES;LEZAMA;2\r\n'
               'DOLORES;CAMION 2;MARTES;MAIPU;1\r\n')
    return Response(content, mimetype='text/csv',
                    headers={'Content-Disposition':'attachment; filename="plantilla_recorridos.csv"'})


@import_bp.post('/api/importar-rutas/preview')
@protegido
def importar_rutas_preview():
    from .importar_rutas import preparar
    from .importar_dias import MAX_BYTES
    from flask import g
    from werkzeug.formparser import parse_form_data
    _, form, files = parse_form_data(request.environ, max_content_length=MAX_BYTES+65536,
                                    max_form_memory_size=128*1024)
    try:
        file=files.get('archivo')
        if not file or not file.filename.lower().endswith('.csv'):
            return jsonify(error='Seleccioná un archivo CSV.'),400
        return jsonify(preparar(file.read(MAX_BYTES+1),file.filename,str(g.portal_user['id']),
                               form.get('modo','vacios'),actor=_usuario()))
    finally:
        for _, uploaded in files.items(multi=True):
            uploaded.close()


@import_bp.post('/api/importar-rutas/confirmar')
@protegido
def importar_rutas_confirmar():
    from .importar_rutas import confirmar
    from .importar_dias import VistaDesactualizada
    from flask import g
    try:
        return jsonify(confirmar(_json().get('token'),str(g.portal_user['id'])))
    except VistaDesactualizada as exc:
        return jsonify(error=str(exc)),409


def clientes_filtrados():
    activos = request.args.get('activos', 'si').lower()
    dias = request.args.get('dias_asignados', 'todos').lower()
    if activos not in {'si', 'no', 'todos'} or dias not in {'si', 'no', 'todos'}:
        raise ValueError('Filtro inválido: usá si, no o todos.')
    return [c for c in S.clientes_vista(incluir_anulados=True)
            if (activos == 'todos' or (not c['an']) == (activos == 'si'))
            and (dias == 'todos' or bool(c['d']) == (dias == 'si'))]


@bp.get("/api/datos")
@protegido
def api_datos():
    """Todo lo que necesita el mapa en un solo pedido."""
    cl = clientes_filtrados()
    plan = S.plan_vista()
    ultima = Session().query(SyncLog).filter(SyncLog.error.is_(None)).order_by(SyncLog.fin.desc()).first()
    return jsonify(clientes=cl, plan=plan, resumen=S.resumen(cl, incluir_inactivos=True), carga=S.carga_por_dia(cl, plan, incluir_inactivos=True),
                   ultima_sync={"origen": ultima.origen, "fin": ultima.fin.isoformat() if ultima and ultima.fin else None}
                   if ultima else None)


@bp.get("/api/resumen")
@protegido
def api_resumen():
    return jsonify(S.resumen(clientes_filtrados(), incluir_inactivos=True))


@bp.get("/api/clientes/<int:cid>/historial")
@protegido
def api_historial(cid):
    rows = (Session().query(CambioLog).filter_by(id_cliente=cid).order_by(CambioLog.fecha.desc()).limit(50))
    return jsonify([{"campo": r.campo, "antes": r.antes, "despues": r.despues, "usuario": r.usuario,
                     "fecha": r.fecha.isoformat()} for r in rows])


