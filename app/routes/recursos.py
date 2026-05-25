from flask import Blueprint, request, jsonify, current_app
from app.services import sheets_svc
from app.services.flota_service import capacidad_flota_mes

bp = Blueprint('recursos', __name__, url_prefix='/api/recursos')


@bp.get('/equipos')
def equipos():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'url requerida'}), 400
    try:
        data = sheets_svc.get_equipos(
            url,
            fecha_filtro=request.args.get('fecha'),
            sucursal_filtro=request.args.get('sucursal'),
        )
        return jsonify({'total': len(data), 'equipos': data})
    except Exception as e:
        return jsonify({'error': str(e)}), 503


@bp.get('/disponibles')
def disponibles():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'url requerida'}), 400
    try:
        data = sheets_svc.get_disponibles(
            url,
            fecha_filtro=request.args.get('fecha'),
            sucursal_filtro=request.args.get('sucursal'),
        )
        return jsonify({'total': len(data), 'disponibles': data})
    except Exception as e:
        return jsonify({'error': str(e)}), 503


@bp.get('/dotacion-entrega')
def dotacion_entrega():
    url = request.args.get('url') or current_app.config.get('DOTACION_ENTREGA_URL')
    recargas_url = request.args.get('recargas_url') or current_app.config.get('DOTACION_RECARGAS_URL')
    try:
        data = sheets_svc.get_dotacion_entrega(
            url,
            recargas_url=recargas_url,
            fecha_filtro=request.args.get('fecha'),
            sucursal_filtro=request.args.get('sucursal'),
            mes_filtro=request.args.get('mes'),
        )
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 503


@bp.post('/sync-capacidad')
def sync_capacidad():
    """Sincroniza dotación de las 4 hojas a capacidad_operativa y estadistica_diaria.

    Lee DOTACION_ENTREGA_URL (reparto CC + Dolores) y DOTACION_RECARGAS_URL (recargas CC + Dolores).
    - camiones_disponibles en capacidad_operativa = flota activa del mes (desde flota_vehiculos)
    - estadistica_diaria recibe: camiones_reales, recargas_count, personas_recargas

    Body: {empresa_id, anio, mes, url?, recargas_url?, sucursal_id?}
    """
    data = request.get_json(force=True) or {}
    empresa_id = str(data.get('empresa_id') or '1')
    sucursal_id = str(data.get('sucursal_id') or data.get('sucursal') or 'TODAS')
    anio = int(data.get('anio') or 0)
    mes = int(data.get('mes') or 0)
    url = data.get('url') or current_app.config.get('DOTACION_ENTREGA_URL')
    recargas_url = data.get('recargas_url') or current_app.config.get('DOTACION_RECARGAS_URL')

    if not anio or not mes:
        return jsonify({'error': 'anio y mes requeridos'}), 400
    if not url:
        return jsonify({'error': 'url del sheet requerida'}), 400

    try:
        mes_filtro = f'{anio:04d}-{mes:02d}'
        sucursal_filtro = sucursal_id if sucursal_id != 'TODAS' else None
        dias_data = sheets_svc.get_camiones_diarios(
            url=url, recargas_url=recargas_url,
            mes_filtro=mes_filtro, sucursal_filtro=sucursal_filtro,
        )

        from app.repositories import planificacion_picos_repository as repo
        actualizados_estadistica = repo.sync_empleados_desde_sheets(empresa_id, dias_data)

        # Obtener flota activa por sucursal para ese mes (fuente de verdad de camiones disponibles)
        flota_por_suc: dict[str, int] = {}
        sucursales_en_datos = {str(d.get('sucursal_id') or sucursal_id) for d in dias_data}
        for suc in sucursales_en_datos:
            if suc and suc != 'DESCONOCIDA':
                try:
                    cap_flota = capacidad_flota_mes(empresa_id=empresa_id, sucursal_id=suc, anio=anio, mes=mes)
                    flota_por_suc[suc] = cap_flota.get('total_activos', 0)
                except Exception:
                    flota_por_suc[suc] = 0

        for dia in dias_data:
            suc = str(dia.get('sucursal_id') or sucursal_id)
            # camiones_disponibles = flota activa del mes; si no hay flota cargada, usar conteo del sheet
            camiones_disp = flota_por_suc.get(suc) or dia['camiones']
            repo.guardar_capacidad({
                'empresa_id': empresa_id,
                'sucursal_id': suc,
                'fecha': dia['fecha'],
                'camiones_disponibles': camiones_disp,
                'choferes': dia['choferes'],
                'acompanantes': dia['ayudantes'],
                'operarios_almacen': 0,
                'capacidad_hl': 0,
                'capacidad_pallets': 0,
            })

        sucursales_sincronizadas = sorted({dia.get('sucursal_id', '?') for dia in dias_data})
        return jsonify({
            'dias_procesados': len(dias_data),
            'sucursales': sucursales_sincronizadas,
            'estadistica_actualizada': actualizados_estadistica,
            'capacidad_operativa_actualizada': len(dias_data),
            'flota_activa_por_sucursal': flota_por_suc,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 503


@bp.get('/flota-operacion')
def flota_operacion():
    """Cruce entre la flota activa del mes y los camiones realmente usados (desde Sheets).

    Parámetros: mes=YYYY-MM, sucursal=ID, empresa_id=1, url?, recargas_url?
    Retorna por día: camiones de la flota activa, cuántos salieron (según sheet),
    cuántos no salieron, recargas del día, personas reparto y recargas.
    """
    mes_param = request.args.get('mes', '')
    sucursal_id = request.args.get('sucursal', request.args.get('sucursal_id', 'TODAS'))
    empresa_id = request.args.get('empresa_id', '1')
    url = request.args.get('url') or current_app.config.get('DOTACION_ENTREGA_URL')
    recargas_url = request.args.get('recargas_url') or current_app.config.get('DOTACION_RECARGAS_URL')

    if not mes_param or len(mes_param) != 7:
        return jsonify({'error': 'mes requerido en formato YYYY-MM'}), 400

    try:
        anio, mes = int(mes_param[:4]), int(mes_param[5:7])
    except (ValueError, IndexError):
        return jsonify({'error': 'mes invalido'}), 400

    try:
        # 1. Datos del sheet (qué salió realmente)
        sucursal_filtro = sucursal_id if sucursal_id != 'TODAS' else None
        dias_data = sheets_svc.get_camiones_diarios(
            url=url, recargas_url=recargas_url,
            mes_filtro=mes_param, sucursal_filtro=sucursal_filtro,
        )

        # 2. Flota activa del mes por sucursal
        sucursales = {str(d.get('sucursal_id') or 'DESCONOCIDA') for d in dias_data}
        if not sucursales and sucursal_id != 'TODAS':
            sucursales = {sucursal_id}

        flota_map: dict[str, dict] = {}
        for suc in sucursales:
            if suc == 'DESCONOCIDA':
                continue
            cap = capacidad_flota_mes(empresa_id=empresa_id, sucursal_id=suc, anio=anio, mes=mes)
            flota_map[suc] = cap

        # 3. Cruzar por día
        dias_result = []
        for dia in dias_data:
            suc = str(dia.get('sucursal_id') or 'DESCONOCIDA')
            cap = flota_map.get(suc, {})
            flota_activa = cap.get('total_activos', 0)
            codigos_flota_activos = {v['codigo'] for v in cap.get('vehiculos_activos', [])}
            codigos_usados = dia.get('_camiones_usados', set())
            camiones_no_usados_codigos = sorted(codigos_flota_activos - codigos_usados)

            dias_result.append({
                'fecha': dia['fecha'],
                'sucursal_id': suc,
                # flota
                'flota_activa': flota_activa,
                'flota_inactiva': cap.get('total_inactivos', 0),
                # sheets reparto
                'camiones_salieron_reparto': dia['camiones_reparto'],
                'personas_reparto': dia['personas_reparto'],
                # sheets recargas
                'recargas_count': dia['recargas_count'],
                'camiones_salieron_recarga': dia['camiones_recarga'],
                'personas_recargas': dia['personas_recargas'],
                # cruce
                'camiones_usados_total': dia['camiones'],
                'camiones_no_usados': len(camiones_no_usados_codigos),
                'camiones_no_usados_codigos': camiones_no_usados_codigos,
            })

        return jsonify({
            'mes': mes_param,
            'sucursal_id': sucursal_id,
            'flota': {suc: {
                'total_activos': v.get('total_activos', 0),
                'total_inactivos': v.get('total_inactivos', 0),
                'por_sucursal': v.get('por_sucursal', []),
            } for suc, v in flota_map.items()},
            'dias': dias_result,
            'totales': {
                'dias_con_datos': len(dias_result),
                'personas_reparto': sum(d['personas_reparto'] for d in dias_result),
                'personas_recargas': sum(d['personas_recargas'] for d in dias_result),
                'recargas_total': sum(d['recargas_count'] for d in dias_result),
            },
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 503
