from __future__ import annotations

import hmac
from datetime import date, datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from app.services import integracion_logistica_svc as svc


bp = Blueprint(
    "integracion_logistica_v1",
    __name__,
    url_prefix="/api/v1/integracion/logistica",
)

MAX_RANGE_DAYS = 31
MAX_LIMIT = 1000
MAX_LIMIT_WITH_CLIENTS = 200


def _error(message: str, status: int, code: str):
    return jsonify({"error": message, "codigo": code}), status


@bp.before_request
def require_integration_api_key():
    expected = str(current_app.config.get("INTEGRATION_API_KEY") or "").strip()
    if not expected:
        return _error(
            "La integración logística no está habilitada.",
            503,
            "integration_not_configured",
        )
    provided = str(request.headers.get("X-API-Key") or "").strip()
    auth = str(request.headers.get("Authorization") or "").strip()
    if not provided and auth.lower().startswith("bearer "):
        provided = auth[7:].strip()
    if not provided or not hmac.compare_digest(provided, expected):
        response, status = _error("API key inválida o ausente.", 401, "unauthorized")
        response.headers["WWW-Authenticate"] = "ApiKey"
        return response, status
    return None


def _parse_date(value: str | None, name: str) -> date:
    if not value:
        raise ValueError(f"{name} requerido en formato YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} inválido; usar YYYY-MM-DD.") from exc


def _parse_int(value: str | None, name: str, default: int) -> int:
    if value in {None, ""}:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} debe ser un número entero.") from exc


def _parse_bool(value: str | None) -> bool:
    if value in {None, ""}:
        return False
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "si", "sí", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError("incluir_clientes debe ser 1 o 0.")


def _periodo() -> tuple[date, date]:
    fecha = request.args.get("fecha")
    desde_raw = request.args.get("desde")
    hasta_raw = request.args.get("hasta")
    if fecha and (desde_raw or hasta_raw):
        raise ValueError("Usar fecha o desde/hasta, no ambos formatos.")
    if fecha:
        parsed = _parse_date(fecha, "fecha")
        return parsed, parsed
    if bool(desde_raw) != bool(hasta_raw):
        raise ValueError("desde y hasta deben enviarse juntos.")
    desde = _parse_date(desde_raw, "desde")
    hasta = _parse_date(hasta_raw, "hasta")
    if desde > hasta:
        raise ValueError("desde no puede ser posterior a hasta.")
    if (hasta - desde).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f"El rango máximo permitido es de {MAX_RANGE_DAYS} días.")
    return desde, hasta


@bp.get("/diaria")
def logistica_diaria():
    try:
        desde, hasta = _periodo()
        empresa_id = str(request.args.get("empresa_id") or "1").strip()
        sucursal = str(request.args.get("sucursal") or "TODAS").strip()
        incluir_clientes = _parse_bool(request.args.get("incluir_clientes"))
        default_limit = 100 if incluir_clientes else 500
        limit = _parse_int(request.args.get("limit"), "limit", default_limit)
        offset = _parse_int(request.args.get("offset"), "offset", 0)
        max_limit = MAX_LIMIT_WITH_CLIENTS if incluir_clientes else MAX_LIMIT
        if not empresa_id:
            raise ValueError("empresa_id no puede quedar vacío.")
        if not sucursal:
            raise ValueError("sucursal no puede quedar vacía.")
        if limit < 1 or limit > max_limit:
            raise ValueError(f"limit debe estar entre 1 y {max_limit}.")
        if offset < 0:
            raise ValueError("offset no puede ser negativo.")
    except ValueError as exc:
        return _error(str(exc), 400, "invalid_request")

    try:
        result = svc.get_logistica_diaria(
            empresa_id=empresa_id,
            sucursal=sucursal,
            desde=desde,
            hasta=hasta,
            incluir_clientes=incluir_clientes,
            limit=limit,
            offset=offset,
        )
    except Exception:
        current_app.logger.exception("Error en integración logística diaria")
        return _error(
            "No se pudo consultar la integración logística.",
            500,
            "integration_query_failed",
        )

    total = int(result.get("total") or 0)
    datos = result.get("datos") or []
    payload = {
        "api_version": "v1",
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "filtros": {
            "empresa_id": empresa_id,
            "sucursal": sucursal,
            "desde": desde.isoformat(),
            "hasta": hasta.isoformat(),
            "incluir_clientes": incluir_clientes,
        },
        "cobertura_resultado": {
            "fecha_min": result.get("fecha_min"),
            "fecha_max": result.get("fecha_max"),
        },
        "paginacion": {
            "limit": limit,
            "offset": offset,
            "devueltos": len(datos),
            "total": total,
            "hay_mas": offset + len(datos) < total,
        },
        "calidad_datos": {
            "fuente_volumen": "ventas_detalle",
            "fuente_chofer": "ventas_detalle",
            "fuente_flota": "flota_vehiculos/transportes",
            "pallets": "estimados como bultos / bultos_por_pallet",
            "alcance": "solo movimientos de mercadería con venta registrada",
        },
        "datos": datos,
    }
    response = jsonify(payload)
    response.headers["X-Total-Count"] = str(total)
    response.headers["Cache-Control"] = "private, max-age=60"
    return response
