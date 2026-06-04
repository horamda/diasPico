from flask import Blueprint, jsonify, request

from app.services import cache_svc, rechazos_svc


bp = Blueprint('rechazos', __name__, url_prefix='/api/rechazos')


def _clear_dashboard_caches():
    cache_svc.clear('picos:')
    cache_svc.clear('portal:')


@bp.get('')
def listar():
    try:
        return jsonify(rechazos_svc.list_rechazos())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('/sync')
def sync():
    try:
        result = rechazos_svc.sync_from_detalle()
        _clear_dashboard_caches()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.patch('/<path:motivo_key>')
def update(motivo_key):
    data = request.get_json(force=True) or {}
    try:
        result = rechazos_svc.update_tomar(motivo_key, bool(data.get('tomar', False)))
        if result.get('updated', 0) == 0:
            return jsonify({'error': 'Motivo no encontrado'}), 404
        _clear_dashboard_caches()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
