from flask import Blueprint, request, jsonify
from app.services import upload_svc, sheets_svc, cache_svc, dropsize_svc

bp = Blueprint('upload', __name__, url_prefix='/api/upload')


def _refresh_dropsize_history(months: list[str], sucursal: str | None) -> list[dict]:
    refreshed = []
    target_sucursal = sucursal or 'TODAS'
    for mes in months:
        item = {'mes': mes, 'sucursal': target_sucursal}
        try:
            item.update(dropsize_svc.recalcular_historico(sucursal=target_sucursal, mes=mes))
        except Exception as e:
            item['error'] = str(e)
        refreshed.append(item)
    return refreshed


@bp.post('/articulos')
def articulos():
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file'}), 400
    try:
        result = upload_svc.load_articulos(f.read())
        cache_svc.clear()
        return jsonify(result.to_dict())
    except Exception as e:
        return jsonify({'error': str(e)}), 422


@bp.post('/resumen')
def resumen():
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file'}), 400
    force    = request.form.get('force', 'false').lower() == 'true'
    sucursal = request.form.get('sucursal') or None
    try:
        result = upload_svc.load_resumen(f.read(), force=force, sucursal=sucursal)
        cache_svc.clear()
        return jsonify(result.to_dict())
    except ValueError as e:
        return jsonify({'error': str(e)}), 422
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('/detalle')
def detalle():
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file'}), 400
    force    = request.form.get('force', 'false').lower() == 'true'
    sucursal = request.form.get('sucursal') or None
    try:
        result = upload_svc.load_detalle(f.read(), force=force, sucursal=sucursal)
        cache_svc.clear()
        return jsonify(result.to_dict())
    except ValueError as e:
        return jsonify({'error': str(e)}), 422
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('/ventas-detalle')
def ventas_detalle():
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file'}), 400
    force    = request.form.get('force', 'false').lower() == 'true'
    sucursal = request.form.get('sucursal') or None
    try:
        result = upload_svc.load_ventas_detalle(f.read(), force=force, sucursal=sucursal)
        payload = result.to_dict()
        payload['dropsize_recalc'] = _refresh_dropsize_history(result.months_in_file, sucursal)
        cache_svc.clear()
        return jsonify(payload)
    except ValueError as e:
        return jsonify({'error': str(e)}), 422
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('/clientes')
def clientes():
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file'}), 400
    try:
        result = upload_svc.load_clientes(f.read())
        cache_svc.clear()
        return jsonify(result.to_dict())
    except ValueError as e:
        return jsonify({'error': str(e)}), 422
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('/transportes')
def transportes():
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file'}), 400
    try:
        result = upload_svc.load_transportes(f.read())
        cache_svc.clear()
        return jsonify(result.to_dict())
    except ValueError as e:
        return jsonify({'error': str(e)}), 422
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('/rechazos')
def rechazos():
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file'}), 400
    try:
        result = upload_svc.load_rechazos(f.read())
        cache_svc.clear()
        return jsonify(result.to_dict())
    except ValueError as e:
        return jsonify({'error': str(e)}), 422
    except Exception as e:
        return jsonify({'error': str(e)}), 500
