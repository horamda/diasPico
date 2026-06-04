from flask import Blueprint, request, jsonify
from app.services import cache_svc, pico_svc, sucursales_svc

bp = Blueprint('parametros', __name__, url_prefix='/api')


@bp.get('/sucursales')
def sucursales():
    empresa_id = request.args.get('empresa_id')
    return jsonify(sucursales_svc.get_sucursales_select(empresa_id=empresa_id))


@bp.post('/sucursales')
def guardar_sucursal():
    data = request.get_json(force=True) or {}
    try:
        result = sucursales_svc.guardar(data)
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.delete('/sucursales/<sucursal_id>')
def eliminar_sucursal(sucursal_id: str):
    try:
        ok = sucursales_svc.eliminar(sucursal_id)
        return jsonify({'ok': ok})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/parametros')
def get_parametros():
    sucursal = request.args.get('sucursal', 'TODAS')
    return jsonify(pico_svc.get_params(sucursal))


@bp.post('/parametros')
def set_parametros():
    data = request.json or {}
    sucursal   = data.get('sucursal', 'TODAS')
    umbral_pct = float(data.get('umbral_pct', 1.20))
    metrica    = data.get('metrica', 'bultos')
    try:
        pico_svc.save_params(sucursal, umbral_pct, metrica)
        cache_svc.clear('picos:')
        cache_svc.clear('portal:')
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
