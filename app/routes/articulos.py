from flask import Blueprint, jsonify, request

from app.services import articulos_svc


bp = Blueprint('articulos', __name__, url_prefix='/api/articulos')


@bp.get('/count')
def count():
    try:
        return jsonify({'total': articulos_svc.get_count()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/sin-clasificar')
def sin_clasificar():
    try:
        return jsonify(articulos_svc.get_sin_clasificar(
            mes=request.args.get('mes'),
            sucursal=request.args.get('sucursal', 'TODAS'),
            limit=request.args.get('limit', 20, type=int),
        ))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
