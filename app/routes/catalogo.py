from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.services import external_catalog_svc as svc


bp = Blueprint("catalogo", __name__, url_prefix="/api/catalogo")


def _json_call(fn):
    try:
        return jsonify(fn())
    except svc.ExternalCatalogError as exc:
        return jsonify({"error": str(exc), "configured": False}), exc.status_code
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.get("/status")
def status():
    def _run():
        base = current_app.config.get("EXTERNAL_API_BASE_URL")
        configured = bool(base and current_app.config.get("EXTERNAL_API_KEY"))
        return {"ok": configured, "base_url": base, "configured": configured}
    return _json_call(_run)


@bp.get("/empresas")
def empresas():
    activa = request.args.get("activa", "1")
    return _json_call(lambda: svc.get_empresas(activa=activa))


@bp.get("/sucursales")
def sucursales():
    return _json_call(lambda: svc.get_sucursales(
        empresa_id=request.args.get("empresa_id"),
        activa=request.args.get("activa", "1"),
    ))


@bp.get("/empleados")
def empleados():
    return _json_call(lambda: svc.get_empleados(dict(request.args)))


@bp.get("/catalogo")
def catalogo():
    return _json_call(lambda: svc.get_catalogo(dict(request.args)))


@bp.get("/dotacion_operativa")
def dotacion_operativa():
    return _json_call(lambda: svc.get_dotacion_operativa(dict(request.args)))
