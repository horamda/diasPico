from datetime import date

from flask import Blueprint, jsonify, request

from app.services import cache_svc, rechazos_svc


bp = Blueprint('rechazos', __name__, url_prefix='/api/rechazos')


def _clear_dashboard_caches():
    cache_svc.clear('picos:')
    cache_svc.clear('portal:')


def _parse_rango():
    desde_s = request.args.get('desde') or date(date.today().year, 1, 1).isoformat()
    hasta_s = request.args.get('hasta') or date.today().isoformat()
    desde = date.fromisoformat(desde_s)
    hasta = date.fromisoformat(hasta_s)
    return desde, hasta


@bp.get('')
def listar():
    try:
        return jsonify(rechazos_svc.list_rechazos())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/diario/resumen')
def diario_resumen():
    try:
        desde, hasta = _parse_rango()
        sucursal = request.args.get('sucursal', 'TODAS')
        return jsonify(rechazos_svc.get_resumen_diario(desde, hasta, sucursal))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/diario/detalle')
def diario_detalle():
    try:
        desde, hasta = _parse_rango()
        sucursal = request.args.get('sucursal', 'TODAS')
        return jsonify(rechazos_svc.get_detalle_diario(desde, hasta, sucursal))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/por-cliente')
def por_cliente():
    try:
        desde, hasta = _parse_rango()
        sucursal = request.args.get('sucursal', 'TODAS')
        limit = request.args.get('limit', type=int) or 50
        return jsonify(rechazos_svc.get_rechazos_por_cliente(desde, hasta, sucursal, limit))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/por-motivo')
def por_motivo():
    try:
        desde, hasta = _parse_rango()
        sucursal = request.args.get('sucursal', 'TODAS')
        limit = request.args.get('limit', type=int) or 50
        return jsonify(rechazos_svc.get_rechazos_por_motivo(desde, hasta, sucursal, limit))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/diario/integracion')
def diario_integracion():
    try:
        desde, hasta = _parse_rango()
        sucursal = request.args.get('sucursal', 'TODAS')
        return jsonify(rechazos_svc.get_integracion_diaria(desde, hasta, sucursal))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
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
