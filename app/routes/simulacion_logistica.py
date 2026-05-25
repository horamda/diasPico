from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services import simulacion_logistica_service as svc
from app.repositories import simulacion_logistica_repository as repo

bp = Blueprint("simulacion_logistica", __name__)


def _json_call(fn, ok_status: int = 200):
    try:
        return jsonify(fn()), ok_status
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Calcular (sin guardar) ───────────────────────────────────────────────────

@bp.post("/api/simulaciones/calcular")
def calcular():
    data = request.get_json(force=True) or {}
    return _json_call(lambda: svc.simular(data))


# ── Guardar simulación ───────────────────────────────────────────────────────

@bp.post("/api/simulaciones/guardar")
def guardar():
    data = request.get_json(force=True) or {}
    return _json_call(lambda: svc.guardar(data), ok_status=201)


# ── Listar simulaciones ──────────────────────────────────────────────────────

@bp.get("/api/simulaciones")
def listar():
    empresa_id  = request.args.get("empresa_id", "1")
    sucursal_id = request.args.get("sucursal_id", request.args.get("sucursal"))
    limit       = request.args.get("limit", 30, type=int)
    return _json_call(lambda: {
        "simulaciones": repo.list_simulaciones(empresa_id, sucursal_id, limit)
    })


# ── Detalle de simulación ────────────────────────────────────────────────────

@bp.get("/api/simulaciones/<int:simulacion_id>")
def detalle(simulacion_id: int):
    return _json_call(lambda: svc.detalle(simulacion_id))


# ── Registrar avance mensual ─────────────────────────────────────────────────

@bp.post("/api/simulaciones/<int:simulacion_id>/avance")
def avance(simulacion_id: int):
    data = request.get_json(force=True) or {}
    return _json_call(lambda: svc.registrar_avance(simulacion_id, data))


# ── Cerrar simulación ────────────────────────────────────────────────────────

@bp.post("/api/simulaciones/<int:simulacion_id>/cerrar")
def cerrar(simulacion_id: int):
    data = request.get_json(force=True) or {}
    return _json_call(lambda: svc.cerrar(simulacion_id, data))


# ── Sugerencias automáticas ──────────────────────────────────────────────────

@bp.get("/api/simulaciones/sugerir")
def sugerir():
    empresa_id  = request.args.get("empresa_id", "1")
    sucursal_id = request.args.get("sucursal_id", request.args.get("sucursal", "TODAS"))
    anio = request.args.get("anio", type=int)
    mes  = request.args.get("mes", type=int)
    if not anio or not mes:
        return jsonify({"error": "anio y mes requeridos"}), 400
    return _json_call(lambda: svc.sugerir_parametros(empresa_id, sucursal_id, anio, mes))


# ── Aprendizaje ──────────────────────────────────────────────────────────────

@bp.get("/api/simulaciones/aprendizaje")
def aprendizaje():
    empresa_id  = request.args.get("empresa_id", "1")
    sucursal_id = request.args.get("sucursal_id", request.args.get("sucursal", "TODAS"))
    mes         = request.args.get("mes", type=int)
    if not mes:
        return jsonify({"error": "mes requerido"}), 400
    return _json_call(lambda: repo.get_aprendizaje(empresa_id, sucursal_id, mes))
