from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.routes.portal import login_required
from app.services import control_stock_svc


bp = Blueprint("control_stock", __name__, url_prefix="/api/control-stock")


@bp.get("/abc")
@login_required
def abc():
    try:
        data = control_stock_svc.get_abc_articulos(
            mes=request.args.get("mes"),
            limit=request.args.get("limit", type=int),
            sucursal=request.args.get("sucursal", "1"),
        )
        return jsonify(data)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/planilla")
@login_required
def planilla():
    try:
        data = control_stock_svc.get_planilla(
            mes=request.args.get("mes"),
            semana=request.args.get("semana", "TODAS"),
            dia=request.args.get("dia", "TODOS"),
            abc=request.args.get("abc", "TODOS"),
            sucursal=request.args.get("sucursal", "1"),
        )
        return jsonify(data)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/control-externo/sorteo")
@login_required
def control_externo_sorteo():
    try:
        data = control_stock_svc.generar_control_externo(
            mes=request.args.get("mes"),
            sucursal=request.args.get("sucursal", "1"),
            cantidad=request.args.get("cantidad", type=int) or 6,
        )
        return jsonify(data)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/planificacion")
@login_required
def planificacion():
    try:
        data = control_stock_svc.get_planificacion(
            mes=request.args.get("mes"),
            sucursal=request.args.get("sucursal", "1"),
        )
        return jsonify(data)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/resumen-mensual")
@login_required
def resumen_mensual():
    try:
        data = control_stock_svc.get_resumen_mensual(
            mes=request.args.get("mes"),
            sucursal=request.args.get("sucursal", "1"),
        )
        return jsonify(data)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/articulos-controlados")
@login_required
def articulos_controlados():
    try:
        data = control_stock_svc.get_articulos_controlados(
            mes=request.args.get("mes"),
            sucursal=request.args.get("sucursal", "1"),
        )
        return jsonify(data)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/resumen-articulo")
@login_required
def resumen_articulo():
    try:
        data = control_stock_svc.get_resumen_por_articulo(
            fecha_control=request.args.get("fecha"),
            sucursal=request.args.get("sucursal", "1"),
            responsable=request.args.get("responsable", ""),
        )
        return jsonify(data)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/abc-mensual")
@login_required
def abc_mensual():
    try:
        data = control_stock_svc.get_abc_mensual(
            anio=request.args.get("anio", type=int),
            sucursal=request.args.get("sucursal", "1"),
        )
        return jsonify(data)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/frescura-status")
@login_required
def frescura_status():
    try:
        return jsonify(control_stock_svc.get_frescura_status(request.args.get("fecha")))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.post("/conteos")
@login_required
def guardar_conteo():
    try:
        user = getattr(g, "portal_user", None) or {}
        data = control_stock_svc.guardar_conteo(
            request.get_json(force=True) or {},
            responsable_default=str(user.get("nombre") or user.get("username") or ""),
        )
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.post("/conteos/validar-dispersion")
@login_required
def validar_dispersion_conteo():
    try:
        data = control_stock_svc.validar_dispersion_conteo(request.get_json(force=True) or {})
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/responsables")
@login_required
def responsables():
    try:
        return jsonify({
            "ok": True,
            "data": control_stock_svc.list_responsables(
                sucursal=request.args.get("sucursal", "1"),
                incluir_inactivos=request.args.get("incluir_inactivos", "0") in {"1", "true", "TRUE", "si", "SI"},
            ),
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.post("/responsables")
@login_required
def responsables_create():
    try:
        data = control_stock_svc.save_responsable(request.get_json(force=True) or {})
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.put("/responsables/<int:responsable_id>")
@login_required
def responsables_update(responsable_id: int):
    try:
        data = control_stock_svc.update_responsable(responsable_id, request.get_json(force=True) or {})
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
