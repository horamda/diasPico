from flask import Blueprint, jsonify, request

from app.services import cache_svc, rechazos_svc


bp = Blueprint('rechazos', __name__, url_prefix='/api/rechazos')


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
        cache_svc.clear('picos:')
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
        cache_svc.clear('picos:')
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
