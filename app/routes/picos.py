from datetime import date
from flask import Blueprint, request, jsonify, send_file
from app.services import pico_svc, cache_svc

bp = Blueprint('picos', __name__, url_prefix='/api/picos')


def _cached(key: str, factory):
    params = '&'.join(f'{k}={v}' for k, v in sorted(request.args.items()))
    return cache_svc.get_or_set(f'picos:{key}:{params}', factory, ttl_seconds=120)


def _clear_dashboard_caches():
    cache_svc.clear('picos:')
    cache_svc.clear('portal:')


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
    umbral   = request.args.get('umbral', type=float)
    metrica  = request.args.get('metrica')
    try:
        return jsonify(_cached('historico', lambda: pico_svc.get_historico(sucursal, n_meses, umbral, metrica)))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/venta-dia')
def venta_dia():
    sucursal = request.args.get('sucursal', 'TODAS')
    desde    = request.args.get('desde') or None
    hasta    = request.args.get('hasta') or None
    umbral   = request.args.get('umbral', type=float)
    metrica  = request.args.get('metrica')
    heatmap_metrica = request.args.get('heatmap_metrica') or None
    periodo_tipo = request.args.get('periodo_tipo') or None
    anio = request.args.get('anio', type=int)
    mes = request.args.get('mes') or None
    semana = request.args.get('semana', type=int)
    anio_comparativo = request.args.get('anio_comparativo', type=int)
    try:
        return jsonify(_cached(
            'venta-dia',
            lambda: pico_svc.get_venta_por_dia(
                sucursal=sucursal,
                desde=desde,
                hasta=hasta,
                umbral_override=umbral,
                metrica_override=metrica,
                heatmap_metrica=heatmap_metrica,
                periodo_tipo=periodo_tipo,
                anio=anio,
                mes=mes,
                semana=semana,
                anio_comparativo=anio_comparativo,
            ),
        ))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/venta-dia/export')
def export_venta_dia():
    sucursal = request.args.get('sucursal', 'TODAS')
    desde    = request.args.get('desde') or None
    hasta    = request.args.get('hasta') or None
    umbral   = request.args.get('umbral', type=float)
    metrica  = request.args.get('metrica')
    heatmap_metrica = request.args.get('heatmap_metrica') or None
    periodo_tipo = request.args.get('periodo_tipo') or None
    anio = request.args.get('anio', type=int)
    mes = request.args.get('mes') or None
    semana = request.args.get('semana', type=int)
    anio_comparativo = request.args.get('anio_comparativo', type=int)
    formato  = request.args.get('formato', 'xlsx')
    try:
        stream, filename, mimetype = pico_svc.export_venta_por_dia(
            sucursal=sucursal,
            desde=desde,
            hasta=hasta,
            umbral_override=umbral,
            metrica_override=metrica,
            heatmap_metrica=heatmap_metrica,
            periodo_tipo=periodo_tipo,
            anio=anio,
            mes=mes,
            semana=semana,
            anio_comparativo=anio_comparativo,
            formato=formato,
        )
        return send_file(stream, as_attachment=True, download_name=filename, mimetype=mimetype)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/experiencia-clientes')
def experiencia_clientes():
    sucursal = request.args.get('sucursal', 'TODAS')
    periodo = request.args.get('periodo') or None
    anio = request.args.get('anio', type=int)
    mes = request.args.get('mes', type=int)
    localidad = request.args.get('localidad') or None
    tipo_negocio = request.args.get('tipo_negocio') or None
    estado = request.args.get('estado') or None
    metrica = request.args.get('metrica') or None
    try:
        return jsonify(_cached(
            'experiencia-clientes',
            lambda: pico_svc.get_experiencia_clientes(
                sucursal=sucursal,
                periodo=periodo,
                anio=anio,
                mes=mes,
                localidad=localidad,
                tipo_negocio=tipo_negocio,
                estado=estado,
                metrica=metrica,
            ),
        ))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
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


@bp.get('/dias-detalle/export')
def export_dias_detalle():
    sucursal = request.args.get('sucursal', 'TODAS')
    desde    = request.args.get('desde', '2025-01')
    hasta    = request.args.get('hasta', date.today().strftime('%Y-%m'))
    umbral   = request.args.get('umbral', type=float)
    metrica  = request.args.get('metrica')
    try:
        stream, filename, mimetype = pico_svc.export_dias_detalle_periodo(
            sucursal=sucursal,
            desde=desde,
            hasta=hasta,
            umbral_override=umbral,
            metrica_override=metrica,
        )
        return send_file(stream, as_attachment=True, download_name=filename, mimetype=mimetype)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/rechazos-dolores/diario')
def rechazos_dolores_diario():
    desde_s = request.args.get('desde') or '2026-01-01'
    hasta_s = request.args.get('hasta') or date.today().isoformat()
    formato = (request.args.get('formato') or 'json').lower()
    try:
        desde = date.fromisoformat(desde_s)
        hasta = date.fromisoformat(hasta_s)
        if formato == 'csv':
            stream, filename, mimetype = pico_svc.export_rechazos_dolores_diario_csv(desde, hasta)
            return send_file(stream, as_attachment=True, download_name=filename, mimetype=mimetype)
        return jsonify(pico_svc.get_rechazos_dolores_diario(desde, hasta))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
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


@bp.get('/venta-anual')
def venta_anual():
    sucursal  = request.args.get('sucursal', 'TODAS')
    anio      = request.args.get('anio',      date.today().year, type=int)
    anio_base = request.args.get('anio_base', anio - 1,          type=int)
    division  = request.args.get('division') or None
    unidad_negocio = request.args.get('unidad_negocio') or None
    metrica   = request.args.get('metrica') or None
    periodo_tipo = request.args.get('periodo_tipo') or None
    mes = request.args.get('mes') or None
    desde = request.args.get('desde') or None
    hasta = request.args.get('hasta') or None
    try:
        return jsonify(pico_svc.get_venta_anual(
            sucursal,
            anio,
            anio_base,
            division=division,
            unidad_negocio=unidad_negocio,
            metrica=metrica,
            periodo_tipo=periodo_tipo,
            mes=mes,
            desde=desde,
            hasta=hasta,
        ))
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


@bp.get('/cobertura-dotacion')
def cobertura_dotacion():
    empresa_id  = request.args.get('empresa_id', '1')
    sucursal_id = request.args.get('sucursal_id', request.args.get('sucursal', 'TODAS'))
    anio = request.args.get('anio', type=int)
    mes  = request.args.get('mes', type=int)
    if not anio or not mes:
        return jsonify({'error': 'anio y mes requeridos'}), 400
    try:
        return jsonify(pico_svc.get_cobertura_picos(empresa_id, sucursal_id, anio, mes))
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
        _clear_dashboard_caches()
        return jsonify({'ok': True, 'meses': rows})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('/ausentismo-mensual/import')
def ausentismo_mensual_import():
    try:
        if request.files.get('file'):
            file = request.files['file']
            raw = file.read()
            try:
                text = raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = raw.decode('latin-1')
            data = {
                'empresa_id': request.form.get('empresa_id', '1'),
                'sucursal_id': request.form.get('sucursal_id', request.form.get('sucursal', 'TODAS')),
                'texto': text,
            }
        else:
            data = request.get_json(force=True) or {}
        result = pico_svc.importar_ausentismo_historico(data)
        _clear_dashboard_caches()
        return jsonify({'ok': True, **result})
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
        aus_mensual_ant = pico_svc.get_ausentismo_mensual(empresa_id, sucursal_id, anio - 1)
        return jsonify({
            'periodos': periodos,
            'sugeridos': sugeridos,
            'ausentismo_mensual': aus_mensual,
            'ausentismo_mensual_anterior': aus_mensual_ant,
            'anio': anio,
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
        _clear_dashboard_caches()
        return jsonify(saved), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.delete('/periodos-criticos/<int:periodo_id>')
def periodos_criticos_delete(periodo_id: int):
    try:
        pico_svc.eliminar_periodo_critico(periodo_id)
        _clear_dashboard_caches()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
