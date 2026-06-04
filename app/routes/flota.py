from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services import cache_svc, flota_service as svc


bp = Blueprint("flota", __name__, url_prefix="/api/flota")


def _json_call(fn, ok_status: int = 200):
    try:
        return jsonify(fn()), ok_status
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _with_planificacion_cache_clear(fn):
    result = fn()
    cache_svc.clear("planificacion_picos:")
    return result


@bp.get("/vehiculos")
def vehiculos():
    return _json_call(lambda: svc.listar_vehiculos(
        empresa_id=request.args.get("empresa_id", "1"),
        sucursal_id=request.args.get("sucursal_id", request.args.get("sucursal", "TODAS")),
        anio=request.args.get("anio", type=int),
        mes=request.args.get("mes", type=int),
        incluir_anulados=request.args.get("incluir_anulados", "0") in {"1", "true", "TRUE", "si", "SI"},
    ))


@bp.post("/vehiculos")
def guardar_vehiculo():
    data = request.get_json(force=True) or {}
    return _json_call(lambda: _with_planificacion_cache_clear(lambda: svc.guardar_vehiculo(data)))


@bp.post("/disponibilidad")
def guardar_disponibilidad():
    data = request.get_json(force=True) or {}
    return _json_call(lambda: _with_planificacion_cache_clear(lambda: svc.guardar_disponibilidad(data)))


@bp.delete("/vehiculos/<int:vehiculo_id>")
def eliminar_vehiculo(vehiculo_id: int):
    return _json_call(lambda: _with_planificacion_cache_clear(lambda: svc.eliminar_vehiculo(vehiculo_id)))


@bp.post("/sync-transportes")
def sync_transportes():
    data = request.get_json(force=True) or {}
    empresa_id = str(data.get("empresa_id") or "1")
    return _json_call(lambda: _with_planificacion_cache_clear(lambda: svc.sync_desde_transportes(empresa_id)))
