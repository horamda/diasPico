from __future__ import annotations

from io import BytesIO

from flask import Blueprint, jsonify, render_template, request, send_file

from app.services import cache_svc, planificacion_picos_service as svc


bp = Blueprint("planificacion_picos", __name__)


def _panel():
    return render_template("panel_dias_pico_v3.html")


def _filters() -> dict:
    return {
        "empresa_id": request.args.get("empresa_id", "1"),
        "sucursal_id": request.args.get("sucursal_id", request.args.get("sucursal", "TODAS")),
        "anio": request.args.get("anio", type=int),
        "mes": request.args.get("mes", type=int),
    }


def _json_call(fn, ok_status: int = 200):
    try:
        return jsonify(fn()), ok_status
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except NotImplementedError as e:
        return jsonify({"error": str(e), "todo": True}), 501
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _planificacion_id_from_request() -> int | None:
    planificacion_id = request.args.get("planificacion_id", type=int)
    if planificacion_id:
        return planificacion_id

    args = _filters()
    if not args.get("anio") or not args.get("mes"):
        return None

    plan = svc.repo.obtener_planificacion_por_periodo(
        args["empresa_id"],
        args["sucursal_id"],
        args["anio"],
        args["mes"],
    )
    return int(plan["id"]) if plan else None


@bp.get("/admin/planificacion_picos")
def admin_planificacion_picos():
    return _panel()


@bp.get("/admin/planificacion_picos/simulador")
def admin_planificacion_picos_simulador():
    return _panel()


@bp.post("/admin/planificacion_picos/generar")
@bp.post("/api/planificacion_picos/generar")
def generar():
    data = request.get_json(force=True) or {}
    def _run():
        result = svc.generar_planificacion(data)
        cache_svc.clear("planificacion_picos:")
        return result
    return _json_call(_run)


@bp.get("/admin/planificacion_picos/<int:planificacion_id>")
@bp.get("/api/planificacion_picos/<int:planificacion_id>")
def detalle(planificacion_id: int):
    return _json_call(lambda: svc.obtener_resumen(planificacion_id=planificacion_id))


@bp.post("/admin/planificacion_picos/<int:planificacion_id>/recalcular")
@bp.post("/api/planificacion_picos/<int:planificacion_id>/recalcular")
def recalcular(planificacion_id: int):
    def _run():
        result = svc.recalcular_planificacion(planificacion_id)
        cache_svc.clear("planificacion_picos:")
        return result
    return _json_call(_run)


@bp.post("/admin/planificacion_picos/<int:planificacion_id>/actualizar_real")
@bp.post("/api/planificacion_picos/<int:planificacion_id>/actualizar_real")
def actualizar_real(planificacion_id: int):
    def _run():
        result = svc.actualizar_real(planificacion_id)
        cache_svc.clear("planificacion_picos:")
        return result
    return _json_call(_run)


@bp.get("/api/planificacion_picos/<int:planificacion_id>/escenarios")
def escenarios_get(planificacion_id: int):
    def _run():
        resumen = svc.obtener_resumen(planificacion_id=planificacion_id)
        return {"escenarios": resumen.get("escenarios", []), "activo": resumen.get("escenario_activo")}
    return _json_call(_run)


@bp.post("/api/planificacion_picos/<int:planificacion_id>/escenarios")
def escenarios_post(planificacion_id: int):
    data = request.get_json(force=True) or {}
    def _run():
        result = svc.guardar_escenario(planificacion_id, data)
        cache_svc.clear("planificacion_picos:")
        return result
    return _json_call(_run)


@bp.post("/api/planificacion_picos/<int:planificacion_id>/escenarios/<int:escenario_id>/activar")
def escenarios_activar(planificacion_id: int, escenario_id: int):
    def _run():
        result = svc.activar_escenario(planificacion_id, escenario_id)
        cache_svc.clear("planificacion_picos:")
        return result
    return _json_call(_run)


@bp.get("/api/planificacion_picos/variables")
def variables_get():
    empresa_id = request.args.get("empresa_id", "1")
    sucursal_id = request.args.get("sucursal_id", request.args.get("sucursal", "TODAS"))
    solo_activas = request.args.get("solo_activas", "0") in {"1", "true", "TRUE", "si", "SI"}
    return _json_call(lambda: {
        "variables": svc.listar_variables(empresa_id, sucursal_id, solo_activas=solo_activas)
    })


@bp.post("/api/planificacion_picos/variables")
def variables_post():
    data = request.get_json(force=True) or {}
    def _run():
        result = svc.guardar_variable(data)
        cache_svc.clear("planificacion_picos:")
        return result
    return _json_call(_run)


@bp.get("/api/planificacion_picos/<int:planificacion_id>/variables")
def variables_plan_get(planificacion_id: int):
    return _json_call(lambda: svc.obtener_variables_plan(planificacion_id))


@bp.post("/api/planificacion_picos/variables/valores")
def variables_valores_post():
    data = request.get_json(force=True) or {}
    def _run():
        result = svc.guardar_variable_valor(data)
        cache_svc.clear("planificacion_picos:")
        return result
    return _json_call(_run)


@bp.get("/admin/planificacion_picos/configuracion")
@bp.get("/api/planificacion_picos/configuracion")
def configuracion_get():
    empresa_id = request.args.get("empresa_id", "1")
    sucursal_id = request.args.get("sucursal_id", request.args.get("sucursal", "TODAS"))
    return _json_call(lambda: svc.repo.obtener_configuracion(empresa_id, sucursal_id))


@bp.post("/admin/planificacion_picos/configuracion")
@bp.post("/api/planificacion_picos/configuracion")
def configuracion_post():
    data = request.get_json(force=True) or {}
    return _json_call(lambda: svc.repo.guardar_configuracion(data))


@bp.get("/api/planificacion_picos/resumen")
def resumen():
    args = _filters()
    planificacion_id = request.args.get("planificacion_id", type=int)
    cache_key = f'planificacion_picos:resumen:{args}:{planificacion_id}'
    return _json_call(lambda: cache_svc.get_or_set(
        cache_key,
        lambda: svc.obtener_resumen(planificacion_id=planificacion_id, **args),
        ttl_seconds=300,
    ))


@bp.get("/api/planificacion_picos/comparativo")
def comparativo():
    args = _filters()
    planificacion_id = request.args.get("planificacion_id", type=int)
    return _json_call(lambda: svc.obtener_comparativo(planificacion_id=planificacion_id, **args))


@bp.get("/api/planificacion_picos/evolucion_diaria")
def evolucion_diaria():
    planificacion_id = _planificacion_id_from_request()
    if not planificacion_id:
        return _json_call(lambda: {"items": [], "mensaje": "No hay planificacion generada."})
    return _json_call(lambda: svc.obtener_evolucion_diaria(planificacion_id))


@bp.get("/api/planificacion_picos/dias_pico")
def dias_pico():
    planificacion_id = _planificacion_id_from_request()
    if not planificacion_id:
        return _json_call(lambda: {"items": [], "mensaje": "No hay planificacion generada."})
    return _json_call(lambda: svc.detectar_dias_pico(planificacion_id))


@bp.get("/api/planificacion_picos/alertas")
def alertas():
    planificacion_id = _planificacion_id_from_request()
    if not planificacion_id:
        return _json_call(lambda: [{"tipo": "SIN_PLAN", "estado": "ALERTA", "mensaje": "No hay planificacion generada."}])
    return _json_call(lambda: svc.obtener_alertas(planificacion_id))


@bp.get("/api/planificacion_picos/capacidad")
def capacidad():
    planificacion_id = _planificacion_id_from_request()
    if not planificacion_id:
        return _json_call(lambda: {"disponible": False, "items": [], "resumen": {}})
    return _json_call(lambda: svc.obtener_resumen(planificacion_id=planificacion_id)["capacidad"])


@bp.post("/api/planificacion_picos/capacidad")
def guardar_capacidad():
    data = request.get_json(force=True) or {}
    return _json_call(lambda: svc.repo.guardar_capacidad(data))


@bp.get("/api/planificacion_picos/simulador")
def simulador_get():
    data = dict(request.args)
    return _json_call(lambda: svc.simular(data))


@bp.post("/api/planificacion_picos/simulador")
def simulador_post():
    data = request.get_json(force=True) or {}
    return _json_call(lambda: svc.simular(data))


@bp.get("/api/planificacion_picos/capacidad_mensual")
def capacidad_mensual_get():
    empresa_id = request.args.get("empresa_id", "1")
    sucursal_id = request.args.get("sucursal_id", request.args.get("sucursal", "TODAS"))
    anio = request.args.get("anio", type=int)
    mes = request.args.get("mes", type=int)
    if not anio or not mes:
        return _json_call(lambda: {"error": "anio y mes requeridos"}), 400
    return _json_call(lambda: svc.repo.obtener_capacidad_mensual(empresa_id, sucursal_id, anio, mes) or {})


@bp.post("/api/planificacion_picos/capacidad_mensual")
def capacidad_mensual_post():
    data = request.get_json(force=True) or {}
    def _run():
        result = svc.guardar_capacidad_mensual(data)
        cache_svc.clear("planificacion_picos:")
        return result
    return _json_call(_run)


@bp.post("/api/planificacion_picos/sync_empleados_sheets")
def sync_empleados_sheets():
    data = request.get_json(force=True) or {}
    def _run():
        empresa_id = str(data.get("empresa_id") or "1")
        sucursal_id = str(data.get("sucursal_id") or data.get("sucursal") or "TODAS")
        anio = int(data.get("anio") or 0)
        mes = int(data.get("mes") or 0)
        url = data.get("url") or ""
        if not anio or not mes:
            raise ValueError("anio y mes requeridos")
        if not url:
            raise ValueError("url del sheet requerida")
        return svc.sync_empleados_sheets(empresa_id, sucursal_id, anio, mes, url, data.get("recargas_url"))
    return _json_call(_run)


@bp.get("/api/planificacion_picos/export")
def exportar():
    planificacion_id = request.args.get("planificacion_id", type=int)
    if not planificacion_id:
        return jsonify({"error": "planificacion_id requerido"}), 400
    formato = request.args.get("formato", "xlsx")
    try:
        stream, filename, mimetype = svc.exportar(planificacion_id, formato)
        if not isinstance(stream, BytesIO):
            stream = BytesIO(stream.getvalue().encode("utf-8-sig"))
        stream.seek(0)
        return send_file(stream, as_attachment=True, download_name=filename, mimetype=mimetype)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except NotImplementedError as e:
        return jsonify({"error": str(e), "todo": True}), 501
    except Exception as e:
        return jsonify({"error": str(e)}), 500
