from datetime import date
from flask import Blueprint, request, jsonify
from app.services import pico_svc, cache_svc

bp = Blueprint('picos', __name__, url_prefix='/api/picos')


def _cached(key: str, factory):
    return cache_svc.get_or_set(f'picos:{key}:{request.full_path}', factory, ttl_seconds=120)


@bp.get('/calendario')
def calendario():
    sucursal = request.args.get('sucursal', 'TODAS')
    mes      = request.args.get('mes', date.today().strftime('%Y-%m'))
    umbral   = request.args.get('umbral', type=float)
    metrica  = request.args.get('metrica')
    try:
        return jsonify(_cached('calendario', lambda: pico_svc.get_calendario(sucursal, mes, umbral, metrica)))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/kpis')
def kpis():
    sucursal = request.args.get('sucursal', 'TODAS')
    mes      = request.args.get('mes', date.today().strftime('%Y-%m'))
    try:
        return jsonify(_cached('kpis', lambda: pico_svc.get_kpis(sucursal, mes)))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/historico')
def historico():
    sucursal = request.args.get('sucursal', 'TODAS')
    n_meses  = request.args.get('meses', 12, type=int)
    try:
        return jsonify(_cached('historico', lambda: pico_svc.get_historico(sucursal, n_meses)))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/analisis-hl')
@bp.get('/analisis-rechazos')
def analisis_hl():
    sucursal = request.args.get('sucursal', 'TODAS')
    n_meses  = request.args.get('meses', 12, type=int)
    try:
        return jsonify(_cached('analisis', lambda: pico_svc.get_analisis_hl(sucursal, n_meses)))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/dia')
def dia():
    sucursal  = request.args.get('sucursal', 'TODAS')
    fecha_str = request.args.get('fecha')
    if not fecha_str:
        return jsonify({'error': 'fecha requerida'}), 400
    try:
        fecha = date.fromisoformat(fecha_str)
        return jsonify(_cached('dia', lambda: pico_svc.get_detalle_dia(sucursal, fecha)))
    except ValueError:
        return jsonify({'error': 'fecha inválida (usar YYYY-MM-DD)'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
