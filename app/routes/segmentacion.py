"""
Blueprint: /api/segmentacion
Endpoints para el módulo de segmentación logística-comercial DPO 2026.
"""

from __future__ import annotations

import csv
import io
import unicodedata
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file

from app.services import segmentacion_svc as svc

bp = Blueprint('segmentacion', __name__, url_prefix='/api/segmentacion')


def _ok(data, **extra):
    return jsonify({'ok': True, 'data': data, **extra})


def _err(msg: str, code: int = 400):
    return jsonify({'ok': False, 'error': str(msg)}), code


_AUTO_CLIENT_KEYS = (
    'iscliente',
    'cliente',
    'clienteid',
    'idcliente',
    'codcliente',
    'codigocliente',
    'codigodecliente',
    'codigo',
    'nrocliente',
    'numerocliente',
)

_AUTO_FLAG_KEYS = (
    'autoelevador',
    'autoelevadores',
    'tieneautoelevador',
    'auto',
    'forklift',
)

_PROMOTOR_KEYS = (
    'fuerzaventa1descripcionpersonalcomercial',
    'fuerzadeventa1descripcionpersonalcomercial',
    'fuerzaventa1descripcion',
    'descripcionvendedor',
    'promotor',
    'vendedor',
    'fuerza',
)

_OTIF_KEYS = (
    'otif',
    'otifvalor',
    'otifpct',
    'otifporcentaje',
    'porcentajeotif',
    'ontimeinfull',
)

_RMD_KEYS = (
    'rmd',
    'rmdvalor',
    'rmdpct',
    'porcentajermd',
)

_NPS_KEYS = (
    'nps',
    'npsvalor',
    'npspuntaje',
)

_FECHA_KEYS = (
    'fecha',
    'fechamedicion',
    'periodo',
)

_OTIF_FECHA_KEYS = ('fechaotif', 'otiffecha')
_RMD_FECHA_KEYS = ('fecharmd', 'rmdfecha')
_NPS_FECHA_KEYS = ('fechanps', 'npsfecha')


def _parse_promotor_csv(raw: str) -> list[dict]:
    try:
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(raw), dialect=dialect)
    fieldnames = [f for f in (reader.fieldnames or []) if f]
    if not fieldnames:
        return []

    by_key = {_norm_csv_key(name): name for name in fieldnames}
    cliente_col = next((by_key[k] for k in _AUTO_CLIENT_KEYS if k in by_key), None)
    promotor_col = next((by_key[k] for k in _PROMOTOR_KEYS if k in by_key), None)

    if not cliente_col or not promotor_col:
        return []

    rows = []
    for row in reader:
        cliente = str(row.get(cliente_col) or '').strip()
        if not cliente:
            continue
        prom = str(row.get(promotor_col) or '').strip() if promotor_col else ''
        rows.append({'cliente': cliente, 'promotor': prom})
    return rows


def _norm_csv_key(value: str | None) -> str:
    raw = unicodedata.normalize('NFD', str(value or ''))
    raw = ''.join(ch for ch in raw if unicodedata.category(ch) != 'Mn')
    return ''.join(ch for ch in raw.lower() if ch.isalnum())


def _decode_csv_upload(raw: bytes) -> str:
    for encoding in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8-sig', errors='replace')


def _parse_metric_number(value: str | None) -> float | None:
    raw = str(value or '').strip()
    if not raw:
        return None
    raw = raw.replace('%', '').replace(' ', '')
    if ',' in raw and '.' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    else:
        raw = raw.replace(',', '.')
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_metric_date(value: str | None) -> str | None:
    raw = str(value or '').strip()
    if not raw:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(raw[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return raw[:10] if len(raw) >= 10 else None


def _parse_servicio_csv(raw: str) -> list[dict]:
    try:
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(raw), dialect=dialect)
    fieldnames = [f for f in (reader.fieldnames or []) if f]
    if not fieldnames:
        return []

    by_key = {_norm_csv_key(name): name for name in fieldnames}
    cliente_col = next((by_key[k] for k in _AUTO_CLIENT_KEYS if k in by_key), None)
    otif_col = next((by_key[k] for k in _OTIF_KEYS if k in by_key), None)
    rmd_col = next((by_key[k] for k in _RMD_KEYS if k in by_key), None)
    nps_col = next((by_key[k] for k in _NPS_KEYS if k in by_key), None)
    fecha_col = next((by_key[k] for k in _FECHA_KEYS if k in by_key), None)
    otif_fecha_col = next((by_key[k] for k in _OTIF_FECHA_KEYS if k in by_key), fecha_col)
    rmd_fecha_col = next((by_key[k] for k in _RMD_FECHA_KEYS if k in by_key), fecha_col)
    nps_fecha_col = next((by_key[k] for k in _NPS_FECHA_KEYS if k in by_key), fecha_col)

    if not cliente_col or not any((otif_col, rmd_col, nps_col)):
        return []

    rows = []
    for row in reader:
        cliente = str(row.get(cliente_col) or '').strip()
        if not cliente:
            continue
        item = {'cliente': cliente}
        if otif_col:
            val = _parse_metric_number(row.get(otif_col))
            if val is not None:
                item['otif_valor'] = val
                if otif_fecha_col:
                    item['otif_fecha'] = _parse_metric_date(row.get(otif_fecha_col))
        if rmd_col:
            val = _parse_metric_number(row.get(rmd_col))
            if val is not None:
                item['rmd_valor'] = val
                if rmd_fecha_col:
                    item['rmd_fecha'] = _parse_metric_date(row.get(rmd_fecha_col))
        if nps_col:
            val = _parse_metric_number(row.get(nps_col))
            if val is not None:
                item['nps_valor'] = val
                if nps_fecha_col:
                    item['nps_fecha'] = _parse_metric_date(row.get(nps_fecha_col))
        if len(item) > 1:
            rows.append(item)
    return rows


def _parse_autoelevador_csv(raw: str) -> list[dict]:
    try:
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(raw), dialect=dialect)
    fieldnames = [f for f in (reader.fieldnames or []) if f]
    if not fieldnames:
        return []

    by_key = {_norm_csv_key(name): name for name in fieldnames}
    cliente_col = next((by_key[k] for k in _AUTO_CLIENT_KEYS if k in by_key), None)
    auto_col = next((by_key[k] for k in _AUTO_FLAG_KEYS if k in by_key), None)
    if not cliente_col and len(fieldnames) == 1:
        cliente_col = fieldnames[0]
    if not cliente_col:
        return []

    rows = []
    for row in reader:
        cliente = str(row.get(cliente_col) or '').strip()
        if not cliente:
            continue
        item = {'is_cliente': cliente, 'autoelevador': True}
        if auto_col:
            item['autoelevador'] = row.get(auto_col)
        rows.append(item)
    return rows


@bp.get('/sop/pdf')
def descargar_sop_pdf():
    try:
        pdf_path = Path(current_app.root_path).parent / 'docs' / 'SOP_Segmentacion_Clientes_DPO.pdf'
        if not pdf_path.exists():
            return _err('No existe SOP PDF generado', 404)
        return send_file(
            str(pdf_path),
            mimetype='application/pdf',
            as_attachment=True,
            download_name='SOP_Segmentacion_Clientes_DPO.pdf',
            max_age=0,
        )
    except Exception as e:
        return _err(e, 500)


# ─────────────────────────────────────────────────────────────
# Parámetros del modelo
# ─────────────────────────────────────────────────────────────

@bp.get('/parametros')
def get_parametros():
    try:
        return _ok(svc.get_parametros())
    except Exception as e:
        return _err(e, 500)


@bp.put('/parametros')
def update_parametros():
    try:
        data = request.get_json(force=True) or {}
        updated = svc.update_parametros(data)
        return _ok(updated)
    except ValueError as e:
        return _err(e)
    except Exception as e:
        return _err(e, 500)


# ─────────────────────────────────────────────────────────────
# Atributos de clientes
# ─────────────────────────────────────────────────────────────

@bp.get('/periodo')
def get_periodo():
    try:
        return _ok(svc.get_periodo_activo(request.args.get('empresa_id', '1')))
    except Exception as e:
        return _err(e, 500)


@bp.put('/periodo')
def set_periodo():
    try:
        data = request.get_json(force=True) or {}
        return _ok(svc.set_periodo_calculo(data))
    except ValueError as e:
        return _err(e)
    except Exception as e:
        return _err(e, 500)


@bp.get('/score-pesos')
def get_score_pesos():
    try:
        return _ok(svc.list_score_pesos())
    except Exception as e:
        return _err(e, 500)


@bp.put('/score-pesos')
def update_score_pesos():
    try:
        data = request.get_json(force=True) or []
        if not isinstance(data, list):
            return _err('Se esperaba una lista JSON')
        return _ok({'actualizados': svc.update_score_pesos(data)})
    except ValueError as e:
        return _err(e)
    except Exception as e:
        return _err(e, 500)


@bp.get('/cache')
@bp.get('/cache/status')
def cache_status():
    try:
        return _ok(svc.get_cache_status())
    except Exception as e:
        return _err(e, 500)


@bp.post('/cache/refresh')
def refresh_cache():
    try:
        body = request.get_json(silent=True) or {}
        user = str(body.get('ejecutado_por', 'api'))
        return _ok(svc.refresh_segmentacion_cache(user))
    except Exception as e:
        return _err(e, 500)


@bp.post('/cache/repair-scores')
def repair_cache_scores():
    try:
        body = request.get_json(silent=True) or {}
        user = str(body.get('ejecutado_por', 'api'))
        return _ok(svc.repair_segmentacion_cache_scores(user))
    except Exception as e:
        return _err(e, 500)


@bp.post('/clientes/atributos')
def upsert_atributos():
    """Actualiza o crea atributos de un cliente (NPS, RMD, autoelevador, etc.)."""
    try:
        data = request.get_json(force=True) or {}
        cliente = (data.pop('cliente', None) or '').strip()
        if not cliente:
            return _err('cliente requerido')
        row = svc.upsert_atributos_cliente(cliente, data)
        return _ok(row)
    except Exception as e:
        return _err(e, 500)


@bp.post('/clientes/atributos/bulk')
def bulk_atributos():
    """Carga masiva: array de objetos con campo 'cliente' obligatorio."""
    try:
        registros = request.get_json(force=True) or []
        if not isinstance(registros, list):
            return _err('Se esperaba una lista JSON')
        n = svc.bulk_upsert_atributos(registros)
        return _ok({'actualizados': n})
    except Exception as e:
        return _err(e, 500)


# ─────────────────────────────────────────────────────────────
# Métricas y clasificación (vistas en vivo)
# ─────────────────────────────────────────────────────────────

@bp.post('/autoelevador/import')
def import_autoelevador():
    """Carga masiva de clientes autoelevador (JSON o CSV)."""
    try:
        registros: list[dict | str]
        fuente = 'api'
        if request.files.get('file'):
            raw = _decode_csv_upload(request.files['file'].read())
            registros = _parse_autoelevador_csv(raw)
            fuente = str(request.form.get('fuente') or 'csv_upload')
        else:
            payload = request.get_json(force=True, silent=True)
            if isinstance(payload, dict) and isinstance(payload.get('clientes'), list):
                registros = payload['clientes']
                fuente = str(payload.get('fuente') or 'json')
            elif isinstance(payload, list):
                registros = payload
                fuente = 'json'
            else:
                return _err('Se esperaba CSV (file) o JSON lista de clientes')
        if not registros:
            return _err('No se encontraron clientes validos para importar')
        actualizados = svc.bulk_upsert_autoelevador(registros, fuente=fuente)
        payload = {
            'leidos': len(registros),
            'actualizados': actualizados,
            'fuente': fuente,
        }
        try:
            payload['segmentacion_cache'] = svc.refresh_segmentacion_cache('upload_autoelevador')
        except Exception as cache_error:
            payload['segmentacion_cache_error'] = str(cache_error)
        return _ok(payload)
    except Exception as e:
        return _err(e, 500)


@bp.post('/geografia/bulk')
def bulk_geografia():
    try:
        rows = request.get_json(force=True) or []
        if not isinstance(rows, list):
            return _err('Se esperaba una lista JSON')
        actualizados = svc.bulk_upsert_cliente_geografia(rows)
        return _ok({'actualizados': actualizados})
    except Exception as e:
        return _err(e, 500)


@bp.get('/metricas')
def metricas():
    """
    Métricas calculadas por cliente.
    Query params: sucursal, limit (default 500), offset (default 0)
    """
    try:
        rows = svc.get_metricas_clientes(
            sucursal=request.args.get('sucursal'),
            limit=int(request.args.get('limit', 500)),
            offset=int(request.args.get('offset', 0)),
        )
        return _ok(rows, total=len(rows))
    except Exception as e:
        return _err(e, 500)


@bp.get('/clientes-activos')
def clientes_activos():
    try:
        rows = svc.get_clientes_activos_dpo(
            sucursal=request.args.get('sucursal'),
            limit=int(request.args.get('limit', 1000)),
        )
        return _ok(rows, total=len(rows))
    except Exception as e:
        return _err(e, 500)


@bp.get('/clusters')
def clusters():
    """
    Clasificación DPO por cliente.
    Query params: sucursal, cluster (Ganador|En crecimiento|Básico|Ventas bajas),
                  limit, offset
    """
    try:
        rows = svc.get_clusters(
            sucursal=request.args.get('sucursal'),
            cluster=request.args.get('cluster'),
            limit=int(request.args.get('limit', 500)),
            offset=int(request.args.get('offset', 0)),
        )
        return _ok(rows, total=len(rows))
    except Exception as e:
        return _err(e, 500)


@bp.get('/mapa/clientes')
def mapa_clientes():
    try:
        rows = svc.get_clientes_mapa(
            sucursal=request.args.get('sucursal'),
            cluster=request.args.get('cluster'),
            peso=request.args.get('peso', 'hl'),
            limit=int(request.args.get('limit', 5000)),
        )
        return _ok(rows, total=len(rows))
    except Exception as e:
        return _err(e, 500)


@bp.post('/promotor/import')
def import_promotor():
    """Importa asignación cliente → promotor desde CSV. Actualiza campo activo."""
    try:
        if request.files.get('file'):
            raw = _decode_csv_upload(request.files['file'].read())
            rows = _parse_promotor_csv(raw)
        else:
            return _err('Se esperaba un archivo CSV')
        if not rows:
            return _err('No se encontraron clientes válidos en el CSV')
        resultado = svc.bulk_upsert_promotores(rows)
        payload = {'leidos': len(rows), **resultado}
        try:
            payload['segmentacion_cache'] = svc.refresh_segmentacion_cache('upload_promotor')
        except Exception as cache_error:
            payload['segmentacion_cache_error'] = str(cache_error)
        return _ok(payload)
    except Exception as e:
        return _err(e, 500)


@bp.post('/servicio/import')
def import_metricas_servicio():
    """Importa OTIF/RMD/NPS por cliente desde CSV o JSON y refresca cache."""
    try:
        if request.files.get('file'):
            raw = _decode_csv_upload(request.files['file'].read())
            rows = _parse_servicio_csv(raw)
            fuente = str(request.form.get('fuente') or 'csv_upload')
        else:
            payload = request.get_json(force=True, silent=True)
            if isinstance(payload, dict) and isinstance(payload.get('clientes'), list):
                rows = payload['clientes']
                fuente = str(payload.get('fuente') or 'json')
            elif isinstance(payload, list):
                rows = payload
                fuente = 'json'
            else:
                return _err('Se esperaba CSV (file) o JSON lista de clientes')
        if not rows:
            return _err('No se encontraron clientes validos con OTIF/RMD/NPS')
        actualizados = svc.bulk_upsert_atributos(rows)
        payload = {'leidos': len(rows), 'actualizados': actualizados, 'fuente': fuente}
        try:
            payload['segmentacion_cache'] = svc.refresh_segmentacion_cache('upload_metricas_servicio')
        except Exception as cache_error:
            payload['segmentacion_cache_error'] = str(cache_error)
        return _ok(payload)
    except Exception as e:
        return _err(e, 500)


@bp.get('/autoelevador/resumen')
def autoelevador_resumen():
    try:
        return _ok(svc.get_autoelevador_resumen(
            sucursal=request.args.get('sucursal'),
        ))
    except Exception as e:
        return _err(e, 500)


@bp.get('/cluster-logistico')
def cluster_logistico():
    try:
        rows = svc.get_cliente_cluster_logistico(
            sucursal=request.args.get('sucursal'),
            cluster=request.args.get('cluster'),
            limit=int(request.args.get('limit', 500)),
        )
        return _ok(rows, total=len(rows))
    except Exception as e:
        return _err(e, 500)


@bp.get('/plan-servicio')
def plan_servicio():
    """
    Plan de servicio sugerido + alertas operativas.
    Query params: sucursal, cluster, solo_alertas (bool), limit, offset
    """
    try:
        rows = svc.get_plan_servicio(
            sucursal=request.args.get('sucursal'),
            cluster=request.args.get('cluster'),
            solo_alertas=request.args.get('solo_alertas', '').lower() in ('1', 'true'),
            limit=int(request.args.get('limit', 500)),
            offset=int(request.args.get('offset', 0)),
        )
        return _ok(rows, total=len(rows))
    except Exception as e:
        return _err(e, 500)


@bp.get('/cliente/<cliente>')
def cliente_detalle(cliente: str):
    """Detalle completo de un cliente específico."""
    try:
        row = svc.get_cliente_detalle(cliente)
        if not row:
            return _err('Cliente no encontrado', 404)
        return _ok(row)
    except Exception as e:
        return _err(e, 500)


@bp.get('/cliente/<cliente>/evolucion')
def cliente_evolucion(cliente: str):
    """Historial mensual de clusters para un cliente."""
    try:
        return _ok(svc.get_evolucion_cluster(cliente))
    except Exception as e:
        return _err(e, 500)


# ─────────────────────────────────────────────────────────────
# Resúmenes para dashboard
# ─────────────────────────────────────────────────────────────

@bp.get('/resumen/sucursal')
def resumen_sucursal():
    try:
        return _ok(svc.get_resumen_sucursal())
    except Exception as e:
        return _err(e, 500)


@bp.get('/resumen/localidad')
def resumen_localidad():
    try:
        return _ok(svc.get_resumen_localidad(
            sucursal=request.args.get('sucursal')
        ))
    except Exception as e:
        return _err(e, 500)


@bp.get('/resumen/activos-localidad')
def resumen_activos_localidad():
    try:
        return _ok(svc.get_resumen_activos_localidad(
            sucursal=request.args.get('sucursal')
        ))
    except Exception as e:
        return _err(e, 500)


@bp.get('/evolucion-mensual')
def evolucion_mensual():
    """
    Evolución mensual de clientes por cluster (desde historico).
    Query params: anio, sucursal
    """
    try:
        anio_str = request.args.get('anio')
        return _ok(svc.get_evolucion_mensual_clusters(
            anio=int(anio_str) if anio_str else None,
            sucursal=request.args.get('sucursal'),
        ))
    except Exception as e:
        return _err(e, 500)


# ─────────────────────────────────────────────────────────────
# Auditoría
# ─────────────────────────────────────────────────────────────

@bp.get('/auditoria')
def auditoria():
    try:
        return _ok(svc.get_auditoria(
            limit=int(request.args.get('limit', 50))
        ))
    except Exception as e:
        return _err(e, 500)


# ─────────────────────────────────────────────────────────────
# Recálculo
# ─────────────────────────────────────────────────────────────

@bp.post('/recalcular')
def recalcular():
    """
    Dispara el recálculo de clusters y guarda snapshot en el histórico.

    Body JSON (opcional):
        {
          "periodo_anio": 2026,      -- default: año corriente
          "periodo_mes": 5,          -- default: 0 = anual
          "ejecutado_por": "admin"   -- default: "api"
        }
    """
    try:
        body = request.get_json(force=True) or {}
        anio = int(body.get('periodo_anio', datetime.now().year))
        mes = int(body.get('periodo_mes', 0))
        user = str(body.get('ejecutado_por', 'api'))
        resultado = svc.recalcular_clusters(anio, mes, user, periodo_data=body)
        return _ok(resultado)
    except Exception as e:
        return _err(e, 500)
