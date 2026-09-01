from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, jsonify, request

from app.services import cache_svc
from app.services import frescura_svc as svc

bp = Blueprint('frescura', __name__, url_prefix='/api/frescura')


def _cache_key(prefix: str) -> str:
    args = '&'.join(f'{k}={v}' for k, v in sorted(request.args.items()))
    return f'frescura:{prefix}:{args}'


def _json_call(factory, status: int = 200):
    try:
        return jsonify({'ok': True, 'data': factory()}), status
    except svc.FrescuraApiError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), exc.status_code
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


def _clear_cache() -> None:
    cache_svc.clear('frescura:')


@bp.get('/errores-stock')
def errores_stock():
    sucursal = request.args.get('sucursal') or None
    return _json_call(
        lambda: cache_svc.get_or_set(
            _cache_key(f'errores-stock:{sucursal or "TODAS"}'),
            lambda: svc.list_errores_stock(sucursal=sucursal),
            ttl_seconds=300,
        )
    )


@bp.get('/config')
def get_config():
    return _json_call(lambda: svc.get_config())


@bp.post('/config')
def save_config():
    data = request.get_json(silent=True) or {}
    try:
        result = svc.save_config(data)
        _clear_cache()
        return jsonify({'ok': True, 'data': result}), 200
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@bp.get('/sync')
def sync():
    try:
        payload = svc.sync_frescura_from_api(fecha_stock=request.args.get('fecha') or request.args.get('fecha_stock'))
        _clear_cache()
        return jsonify({'ok': True, 'data': payload})
    except svc.FrescuraApiError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), exc.status_code
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@bp.get('/articulos')
def articulos():
    args = request.args.to_dict(flat=True)
    return _json_call(
        lambda: cache_svc.get_or_set(
            _cache_key('articulos'),
            lambda: svc.list_articulos(**args),
            ttl_seconds=300,
        )
    )


@bp.get('/articulos/criticos')
def articulos_criticos():
    args = request.args.to_dict(flat=True)
    args['estado'] = 'CRITICO,ALERTA'
    return _json_call(
        lambda: cache_svc.get_or_set(
            _cache_key('articulos_criticos'),
            lambda: svc.list_articulos(**args),
            ttl_seconds=180,
        )
    )


@bp.get('/articulos/<codigo_articulo>/resumen')
def articulo_resumen(codigo_articulo: str):
    sucursal = request.args.get('sucursal') or None
    args = request.args.to_dict(flat=True)
    args.pop('sucursal', None)
    return _json_call(
        lambda: cache_svc.get_or_set(
            _cache_key(f'resumen:{codigo_articulo}:{sucursal or "TODAS"}'),
            lambda: svc.get_articulo_resumen(codigo_articulo, sucursal=sucursal, **args),
            ttl_seconds=300,
        )
    )


@bp.get('/articulos/<codigo_articulo>/clientes')
def articulo_clientes(codigo_articulo: str):
    sucursal = request.args.get('sucursal') or None
    args = request.args.to_dict(flat=True)
    args.pop('sucursal', None)
    return _json_call(
        lambda: cache_svc.get_or_set(
            _cache_key(f'clientes:{codigo_articulo}:{sucursal or "TODAS"}'),
            lambda: svc.get_articulo_clientes(codigo_articulo, sucursal=sucursal, **args),
            ttl_seconds=300,
        )
    )


@bp.get('/articulos/<codigo_articulo>/oportunidades')
def articulo_oportunidades(codigo_articulo: str):
    sucursal = request.args.get('sucursal') or None
    limit = request.args.get('limit', 50, type=int)
    args = request.args.to_dict(flat=True)
    args.pop('sucursal', None)
    args.pop('limit', None)
    return _json_call(
        lambda: cache_svc.get_or_set(
            _cache_key(f'oportunidades:{codigo_articulo}:{sucursal or "TODAS"}:{limit}'),
            lambda: svc.get_articulo_oportunidades(codigo_articulo, sucursal=sucursal, limit=limit, **args),
            ttl_seconds=300,
        )
    )


@bp.get('/articulos/<codigo_articulo>/clientes/export')
def articulo_clientes_export(codigo_articulo: str):
    sucursal = request.args.get('sucursal') or None
    tipo = request.args.get('tipo', 'nunca_compraron')
    args = request.args.to_dict(flat=True)
    args.pop('sucursal', None)
    args.pop('tipo', None)
    try:
        payload = svc.get_articulo_clientes(codigo_articulo, sucursal=sucursal, **args)
        clientes_dict = payload.get('clientes') or {}
        if tipo == 'nunca_compraron':
            rows = clientes_dict.get('nunca_compraron', [])
        elif tipo == 'inactivos':
            rows = clientes_dict.get('compradores_inactivos', [])
        elif tipo == 'recientes':
            rows = clientes_dict.get('compradores_recientes', [])
        else:
            rows = (
                clientes_dict.get('compradores_recientes', [])
                + clientes_dict.get('compradores_inactivos', [])
                + clientes_dict.get('nunca_compraron', [])
            )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Cliente', 'Nombre', 'Localidad', 'Cluster', 'Score',
            'Sucursal', 'Ultima Venta', 'Dias Sin Comprar', 'Prioridad',
        ])
        for row in rows:
            writer.writerow([
                row.get('cliente', ''),
                row.get('cliente_nombre', ''),
                row.get('localidad', ''),
                row.get('cluster_dpo', ''),
                row.get('score_total', ''),
                row.get('sucursal_nombre', ''),
                row.get('ultima_venta', ''),
                row.get('dias_desde_ultima_venta', ''),
                row.get('prioridad_accion', ''),
            ])
        filename = f'{codigo_articulo}_{tipo}.csv'
        return Response(
            '' + output.getvalue(),
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@bp.post('/articulos/<codigo_articulo>/plan-accion')
def articulo_plan_accion(codigo_articulo: str):
    sucursal = request.args.get('sucursal') or None
    data = request.get_json(silent=True) or {}
    try:
        payload = svc.guardar_plan_accion(codigo_articulo, sucursal=sucursal, data=data)
        _clear_cache()
        return jsonify({'ok': True, 'data': payload}), 201
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500
