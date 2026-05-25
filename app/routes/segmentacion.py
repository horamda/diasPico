"""
Blueprint: /api/segmentacion
Endpoints para el módulo de segmentación logística-comercial DPO 2026.
"""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from app.services import segmentacion_svc as svc

bp = Blueprint('segmentacion', __name__, url_prefix='/api/segmentacion')


def _ok(data, **extra):
    return jsonify({'ok': True, 'data': data, **extra})


def _err(msg: str, code: int = 400):
    return jsonify({'ok': False, 'error': str(msg)}), code


# ─────────────────────────────────────────────────────────────
# Parámetros del modelo
# ─────────────────────────────────────────────────────────────

@bp.get('/parametros')
def get_parametros():
    try:
        return _ok(svc.get_parametros())
    except Exception as e:
        return _err(e, 500)


@bp.put('/parametros')
def update_parametros():
    try:
        data = request.get_json(force=True) or {}
        updated = svc.update_parametros(data)
        return _ok(updated)
    except ValueError as e:
        return _err(e)
    except Exception as e:
        return _err(e, 500)


# ─────────────────────────────────────────────────────────────
# Atributos de clientes
# ─────────────────────────────────────────────────────────────

@bp.post('/clientes/atributos')
def upsert_atributos():
    """Actualiza o crea atributos de un cliente (NPS, RMD, autoelevador, etc.)."""
    try:
        data = request.get_json(force=True) or {}
        cliente = (data.pop('cliente', None) or '').strip()
        if not cliente:
            return _err('cliente requerido')
        row = svc.upsert_atributos_cliente(cliente, data)
        return _ok(row)
    except Exception as e:
        return _err(e, 500)


@bp.post('/clientes/atributos/bulk')
def bulk_atributos():
    """Carga masiva: array de objetos con campo 'cliente' obligatorio."""
    try:
        registros = request.get_json(force=True) or []
        if not isinstance(registros, list):
            return _err('Se esperaba una lista JSON')
        n = svc.bulk_upsert_atributos(registros)
        return _ok({'actualizados': n})
    except Exception as e:
        return _err(e, 500)


# ─────────────────────────────────────────────────────────────
# Métricas y clasificación (vistas en vivo)
# ─────────────────────────────────────────────────────────────

@bp.get('/metricas')
def metricas():
    """
    Métricas calculadas por cliente.
    Query params: sucursal, limit (default 500), offset (default 0)
    """
    try:
        rows = svc.get_metricas_clientes(
            sucursal=request.args.get('sucursal'),
            limit=int(request.args.get('limit', 500)),
            offset=int(request.args.get('offset', 0)),
        )
        return _ok(rows, total=len(rows))
    except Exception as e:
        return _err(e, 500)


@bp.get('/clusters')
def clusters():
    """
    Clasificación DPO por cliente.
    Query params: sucursal, cluster (Ganador|En crecimiento|Básico|Ventas bajas),
                  limit, offset
    """
    try:
        rows = svc.get_clusters(
            sucursal=request.args.get('sucursal'),
            cluster=request.args.get('cluster'),
            limit=int(request.args.get('limit', 500)),
            offset=int(request.args.get('offset', 0)),
        )
        return _ok(rows, total=len(rows))
    except Exception as e:
        return _err(e, 500)


@bp.get('/plan-servicio')
def plan_servicio():
    """
    Plan de servicio sugerido + alertas operativas.
    Query params: sucursal, cluster, solo_alertas (bool), limit, offset
    """
    try:
        rows = svc.get_plan_servicio(
            sucursal=request.args.get('sucursal'),
            cluster=request.args.get('cluster'),
            solo_alertas=request.args.get('solo_alertas', '').lower() in ('1', 'true'),
            limit=int(request.args.get('limit', 500)),
            offset=int(request.args.get('offset', 0)),
        )
        return _ok(rows, total=len(rows))
    except Exception as e:
        return _err(e, 500)


@bp.get('/cliente/<cliente>')
def cliente_detalle(cliente: str):
    """Detalle completo de un cliente específico."""
    try:
        row = svc.get_cliente_detalle(cliente)
        if not row:
            return _err('Cliente no encontrado', 404)
        return _ok(row)
    except Exception as e:
        return _err(e, 500)


@bp.get('/cliente/<cliente>/evolucion')
def cliente_evolucion(cliente: str):
    """Historial mensual de clusters para un cliente."""
    try:
        return _ok(svc.get_evolucion_cluster(cliente))
    except Exception as e:
        return _err(e, 500)


# ─────────────────────────────────────────────────────────────
# Resúmenes para dashboard
# ─────────────────────────────────────────────────────────────

@bp.get('/resumen/sucursal')
def resumen_sucursal():
    try:
        return _ok(svc.get_resumen_sucursal())
    except Exception as e:
        return _err(e, 500)


@bp.get('/resumen/localidad')
def resumen_localidad():
    try:
        return _ok(svc.get_resumen_localidad(
            sucursal=request.args.get('sucursal')
        ))
    except Exception as e:
        return _err(e, 500)


@bp.get('/evolucion-mensual')
def evolucion_mensual():
    """
    Evolución mensual de clientes por cluster (desde historico).
    Query params: anio, sucursal
    """
    try:
        anio_str = request.args.get('anio')
        return _ok(svc.get_evolucion_mensual_clusters(
            anio=int(anio_str) if anio_str else None,
            sucursal=request.args.get('sucursal'),
        ))
    except Exception as e:
        return _err(e, 500)


# ─────────────────────────────────────────────────────────────
# Auditoría
# ─────────────────────────────────────────────────────────────

@bp.get('/auditoria')
def auditoria():
    try:
        return _ok(svc.get_auditoria(
            limit=int(request.args.get('limit', 50))
        ))
    except Exception as e:
        return _err(e, 500)


# ─────────────────────────────────────────────────────────────
# Recálculo
# ─────────────────────────────────────────────────────────────

@bp.post('/recalcular')
def recalcular():
    """
    Dispara el recálculo de clusters y guarda snapshot en el histórico.

    Body JSON (opcional):
        {
          "periodo_anio": 2026,      -- default: año corriente
          "periodo_mes": 5,          -- default: 0 = anual
          "ejecutado_por": "admin"   -- default: "api"
        }
    """
    try:
        body = request.get_json(force=True) or {}
        anio = int(body.get('periodo_anio', datetime.now().year))
        mes  = int(body.get('periodo_mes', 0))
        user = str(body.get('ejecutado_por', 'api'))
        resultado = svc.recalcular_clusters(anio, mes, user)
        return _ok(resultado)
    except Exception as e:
        return _err(e, 500)
