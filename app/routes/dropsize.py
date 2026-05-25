from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file, send_from_directory
from openpyxl import Workbook

from app.services import dropsize_svc, cache_svc


bp = Blueprint('dropsize', __name__)


def _cached(key: str, factory):
    return cache_svc.get_or_set(f'dropsize:{key}:{request.full_path}', factory, ttl_seconds=120)


def _args_period() -> dict:
    return {
        'sucursal': request.args.get('sucursal', 'TODAS'),
        'fecha_desde': request.args.get('fecha_desde') or None,
        'fecha_hasta': request.args.get('fecha_hasta') or None,
        'mes': request.args.get('mes') or None,
    }


@bp.get('/admin/dropsize')
def admin_dropsize():
    project_root = Path(__file__).resolve().parent.parent.parent
    return send_from_directory(project_root, 'panel_dias_pico_v3.html')


@bp.get('/api/dropsize/resumen')
def resumen():
    try:
        p = _args_period()
        return jsonify(_cached('resumen', lambda: dropsize_svc.get_resumen(**p)))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/api/dropsize/evolucion_diaria')
def evolucion_diaria():
    try:
        p = _args_period()
        return jsonify(_cached('diaria', lambda: dropsize_svc.get_evolucion_diaria(**p)))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/api/dropsize/evolucion_mensual')
def evolucion_mensual():
    try:
        sucursal = request.args.get('sucursal', 'TODAS')
        meses = request.args.get('meses', 12, type=int)
        mes_hasta = request.args.get('mes') or None
        return jsonify(_cached('mensual', lambda: dropsize_svc.get_evolucion_mensual(sucursal, meses, mes_hasta)))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/api/dropsize/ranking_sucursales')
def ranking_sucursales():
    try:
        p = _args_period()
        unidad = request.args.get('unidad', 'bultos')
        p.pop('sucursal', None)
        return jsonify(_cached('ranking', lambda: dropsize_svc.get_ranking_sucursales(**p, unidad=unidad)))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/api/dropsize/comparativo')
def comparativo():
    try:
        sucursal = request.args.get('sucursal', 'TODAS')
        mes = request.args.get('mes') or date.today().strftime('%Y-%m')
        return jsonify(_cached('comparativo', lambda: dropsize_svc.get_comparativo(sucursal, mes)))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/api/dropsize/dias_pico')
def dias_pico():
    try:
        p = _args_period()
        metrica = request.args.get('metrica', 'todos')
        umbral = request.args.get('umbral', type=float)
        return jsonify(_cached('picos', lambda: dropsize_svc.get_dias_pico(**p, metrica=metrica, umbral=umbral)))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/api/dropsize/objetivos')
def objetivos_api():
    try:
        sucursal = request.args.get('sucursal')
        return jsonify(_cached('objetivos', lambda: dropsize_svc.list_objetivos(sucursal)))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('/api/dropsize/objetivos')
@bp.post('/admin/dropsize/objetivos')
def guardar_objetivo():
    data = request.get_json(force=True) or {}
    try:
        result = dropsize_svc.save_objetivo(data)
        cache_svc.clear('dropsize:')
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.delete('/api/dropsize/objetivos/<int:objetivo_id>')
def eliminar_objetivo(objetivo_id):
    try:
        result = dropsize_svc.delete_objetivo(objetivo_id)
        cache_svc.clear('dropsize:')
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/admin/dropsize/objetivos')
def admin_dropsize_objetivos():
    project_root = Path(__file__).resolve().parent.parent.parent
    return send_from_directory(project_root, 'panel_dias_pico_v3.html')


@bp.post('/api/dropsize/recalcular')
def recalcular():
    data = request.get_json(silent=True) or {}
    try:
        result = dropsize_svc.recalcular_historico(
            sucursal=data.get('sucursal', 'TODAS'),
            fecha_desde=data.get('fecha_desde') or None,
            fecha_hasta=data.get('fecha_hasta') or None,
            mes=data.get('mes') or None,
        )
        cache_svc.clear('dropsize:')
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/api/dropsize/export')
def exportar():
    try:
        p = _args_period()
        resumen_data = dropsize_svc.get_resumen(**p)
        diaria = dropsize_svc.get_evolucion_diaria(**p)
        wb = Workbook()
        ws = wb.active
        ws.title = 'Dropsize'
        ws.append(['Indicador', 'Valor'])
        for key in [
            'clientes_entregados', 'total_bultos', 'total_hl', 'total_pallets',
            'dropsize_bultos', 'dropsize_hl', 'dropsize_pallets',
        ]:
            ws.append([key, resumen_data.get(key)])
        ws2 = wb.create_sheet('Diario')
        ws2.append(['fecha', 'clientes_entregados', 'total_bultos', 'total_hl', 'total_pallets',
                    'dropsize_bultos', 'dropsize_hl', 'dropsize_pallets'])
        for row in diaria['dias']:
            ws2.append([
                row.get('fecha'), row.get('clientes_entregados'), row.get('total_bultos'),
                row.get('total_hl'), row.get('total_pallets'), row.get('dropsize_bultos'),
                row.get('dropsize_hl'), row.get('dropsize_pallets'),
            ])
        bio = BytesIO()
        wb.save(bio)
        bio.seek(0)
        return send_file(
            bio,
            as_attachment=True,
            download_name='dropsize.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500
