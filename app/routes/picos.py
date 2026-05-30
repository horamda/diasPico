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


@bp.get('/comparativo-anual')
def comparativo_anual():
    sucursal  = request.args.get('sucursal', 'TODAS')
    anio      = request.args.get('anio',      date.today().year, type=int)
    anio_base = request.args.get('anio_base', anio - 1,          type=int)
    try:
        return jsonify(pico_svc.get_comparativo_anual(sucursal, anio, anio_base))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/dotacion-diaria')
def dotacion_diaria():
    empresa_id  = request.args.get('empresa_id', '1')
    sucursal_id = request.args.get('sucursal_id', request.args.get('sucursal', 'TODAS'))
    fecha_ini_s = request.args.get('fecha_ini')
    fecha_fin_s = request.args.get('fecha_fin')
    try:
        if fecha_ini_s:
            fi = date.fromisoformat(fecha_ini_s)
        else:
            hoy = date.today()
            fi  = date(hoy.year, hoy.month, 1)
        ff = date.fromisoformat(fecha_fin_s) if fecha_fin_s else date.today()
        return jsonify(pico_svc.get_dotacion_diaria(empresa_id, sucursal_id, fi, ff))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/ausentismo-mensual')
def ausentismo_mensual_get():
    empresa_id  = request.args.get('empresa_id', '1')
    sucursal_id = request.args.get('sucursal_id', request.args.get('sucursal', 'TODAS'))
    anio        = request.args.get('anio', date.today().year, type=int)
    try:
        rows = pico_svc.get_ausentismo_mensual(empresa_id, sucursal_id, anio)
        return jsonify({'anio': anio, 'meses': rows})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('/ausentismo-mensual')
def ausentismo_mensual_post():
    data = request.get_json(force=True) or {}
    try:
        rows = pico_svc.guardar_ausentismo_mensual(data)
        return jsonify({'ok': True, 'meses': rows})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/periodos-criticos')
def periodos_criticos_get():
    empresa_id  = request.args.get('empresa_id', '1')
    sucursal_id = request.args.get('sucursal_id', request.args.get('sucursal', 'TODAS'))
    anio        = request.args.get('anio', date.today().year, type=int)
    try:
        periodos       = pico_svc.get_periodos_criticos(empresa_id, sucursal_id, anio)
        sugeridos      = pico_svc.sugerir_periodos_criticos(sucursal_id, anio)
        aus_mensual    = pico_svc.get_ausentismo_mensual(empresa_id, sucursal_id, anio)
        return jsonify({
            'periodos': periodos,
            'sugeridos': sugeridos,
            'ausentismo_mensual': aus_mensual,
            'total': len(periodos),
            'cumple_minimo': len(periodos) >= 3,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('/periodos-criticos')
def periodos_criticos_post():
    data = request.get_json(force=True) or {}
    try:
        saved = pico_svc.guardar_periodo_critico(data)
        return jsonify(saved), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.delete('/periodos-criticos/<int:periodo_id>')
def periodos_criticos_delete(periodo_id: int):
    try:
        pico_svc.eliminar_periodo_critico(periodo_id)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
