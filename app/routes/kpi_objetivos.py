from flask import Blueprint, jsonify, request

from app.services import cache_svc, kpi_objetivos_svc

bp = Blueprint('kpi_objetivos', __name__, url_prefix='/api/kpi-objetivos')


@bp.get('/indicadores')
def indicadores():
    return jsonify(kpi_objetivos_svc.list_indicadores())


@bp.get('')
def listar():
    try:
        sucursal = request.args.get('sucursal')
        return jsonify(kpi_objetivos_svc.list_objetivos(sucursal))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('')
def guardar():
    data = request.get_json(force=True) or {}
    try:
        result = kpi_objetivos_svc.save_objetivo(data)
        cache_svc.clear('picos:')
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.delete('/<int:objetivo_id>')
def eliminar(objetivo_id):
    try:
        result = kpi_objetivos_svc.delete_objetivo(objetivo_id)
        cache_svc.clear('picos:')
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
