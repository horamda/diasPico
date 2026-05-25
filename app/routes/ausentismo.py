from flask import Blueprint, jsonify, request

from app.services import ausentismo_svc


bp = Blueprint('ausentismo', __name__, url_prefix='/api')


@bp.get('/ausentismo')
def ausentismo():
    try:
        result = ausentismo_svc.get_ausentismo(
            sucursal=request.args.get('sucursal'),
            fecha=request.args.get('fecha'),
            mes=request.args.get('mes'),
        )
        status = 400 if result.get('error') == 'fecha o mes requerido' else 200
        return jsonify(result), status
    except Exception as e:
        return jsonify({'data': [], 'disponible': False, 'error': str(e)})
