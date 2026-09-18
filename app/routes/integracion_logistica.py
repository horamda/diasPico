from __future__ import annotations

import hmac
from datetime import date, datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from app.services import integracion_logistica_svc as svc
from app.services import integracion_rechazos_svc
from app.services import integracion_pedidos_svc


bp = Blueprint(
    "integracion_logistica_v1",
    __name__,
    url_prefix="/api/v1/integracion/logistica",
)

MAX_RANGE_DAYS = 31
MAX_LIMIT = 1000
MAX_LIMIT_WITH_CLIENTS = 200


@bp.get('/pedidos')
def pedidos():
    try:
        desde, hasta = _periodo()
        sucursal = str(request.args.get('sucursal', 'TODAS')).strip()
        limit = _parse_int(request.args.get('limit'), 'limit', 200)
        offset = _parse_int(request.args.get('offset'), 'offset', 0)
        if 'empresa_id' in request.args:
            raise ValueError('El detalle de repartos no tiene empresa_id; filtrar por sucursal.')
        if not sucursal or not 1 <= limit <= MAX_LIMIT or offset < 0:
            raise ValueError('Sucursal requerida; limit entre 1 y 1000; offset mayor o igual a 0.')
    except ValueError as exc:
        return _error(str(exc), 400, 'invalid_request')
    try:
        result = integracion_pedidos_svc.get_pedidos(
            desde=desde, hasta=hasta, sucursal=sucursal, limit=limit, offset=offset)
    except Exception:
        current_app.logger.exception('Error en integración de pedidos')
        return _error('No se pudieron consultar los pedidos.', 500, 'integration_query_failed')
    datos, total = result['datos'], int(result['total'])
    response = jsonify({
        'api_version': 'v1',
        'generado_en': datetime.now(timezone.utc).isoformat(),
        'filtros': dict(desde=desde.isoformat(), hasta=hasta.isoformat(), sucursal=sucursal),
        'cobertura': {'ultima_fecha_disponible': result['ultima_fecha_disponible']},
        'paginacion': dict(limit=limit, offset=offset, devueltos=len(datos), total=total,
                           hay_mas=offset + len(datos) < total),
        'criterios': {
            'fuente': 'repartos_detalle',
            'unidad': 'pedido (o comprobante) por sucursal, cliente y fecha de entrega de planilla',
            'estado': 'derivado de los estados registrados de todas las líneas; no compara cantidades pedidas',
            'fecha_entrega': 'fecha de entrega de planilla; no acredita por sí sola entrega efectiva',
            'vinculo_foxtrot': 'referencias de origen para cruce; no es un ID externo confirmado',
            'ausencia': 'sin fila significa sin datos',
        },
        'datos': datos,
    })
    response.headers['X-Total-Count'] = str(total)
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.get('/rechazos/clientes-diario')
def rechazos_clientes_diario():
    try:
        desde, hasta = _periodo()
        empresa_id = str(request.args.get('empresa_id', '1')).strip()
        sucursal = str(request.args.get('sucursal', 'TODAS')).strip()
        limit = _parse_int(request.args.get('limit'), 'limit', 200)
        offset = _parse_int(request.args.get('offset'), 'offset', 0)
        if not empresa_id or not sucursal:
            raise ValueError('empresa_id y sucursal no pueden quedar vacíos.')
        if limit < 1 or limit > MAX_LIMIT or offset < 0:
            raise ValueError('limit debe estar entre 1 y 1000; offset debe ser mayor o igual a 0.')
    except ValueError as exc:
        return _error(str(exc), 400, 'invalid_request')
    try:
        result = integracion_rechazos_svc.get_clientes_diario(
            empresa_id=empresa_id, sucursal=sucursal, desde=desde, hasta=hasta,
            limit=limit, offset=offset,
        )
    except Exception:
        current_app.logger.exception('Error en integración de rechazos por cliente')
        return _error('No se pudieron consultar los rechazos.', 500, 'integration_query_failed')
    datos = result['datos']
    total = result['total']
    response = jsonify({
        'api_version': 'v1',
        'generado_en': datetime.now(timezone.utc).isoformat(),
        'filtros': dict(empresa_id=empresa_id, sucursal=sucursal,
                        desde=desde.isoformat(), hasta=hasta.isoformat()),
        'paginacion': dict(limit=limit, offset=offset, devueltos=len(datos),
                           total=total, hay_mas=offset + len(datos) < total),
        'criterios': {
            'clave': ['empresa_id', 'fecha', 'cliente_id'],
            'fecha': 'fecha del movimiento de ventas; no acredita fecha de entrega',
            'alcance': 'mercadería con movimiento registrado, excluye remitos y comodatos',
            'incluye_sin_rechazo': True,
            'computable': 'rechazo con cantidad positiva y motivo configurado con tomar=true',
            'volumen': 'cantidades de origen; no se infieren cantidades pedidas ni entregadas',
            'ausencia': 'sin fila significa sin datos, no entrega exitosa',
            'otif_calculable': False,
        },
        'datos': datos,
    })
    response.headers['X-Total-Count'] = str(total)
    response.headers['Cache-Control'] = 'no-store'
    return response


def _error(message: str, status: int, code: str):
    return jsonify({"error": message, "codigo": code}), status


@bp.before_request
def require_integration_api_key():
    accepted_keys = [
        str(current_app.config.get(name) or "").strip()
        for name in ("LOGISTICS_INTEGRATION_API_KEY", "INTEGRATION_API_KEY")
    ]
    accepted_keys = [key for key in accepted_keys if key]
    if not accepted_keys:
        return _error(
            "La integración logística no está habilitada.",
            503,
            "integration_not_configured",
        )
    provided = str(request.headers.get("X-API-Key") or "").strip()
    auth = str(request.headers.get("Authorization") or "").strip()
    if not provided and auth.lower().startswith("bearer "):
        provided = auth[7:].strip()
    # Compare every configured key, retaining compatibility with existing clients.
    matches = [hmac.compare_digest(provided.encode("utf-8"), key.encode("utf-8"))
               for key in accepted_keys]
    if not provided or not any(matches):
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
