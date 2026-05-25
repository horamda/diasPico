"""
Google Sheets integration: fetch CSV exports and normalize rows.
"""

from __future__ import annotations
import csv
import io
import re
import requests
from flask import current_app

from app.services.pico_svc import SUCURSAL_LABELS
from app.utils.coerce import norm_fecha, to_dec


def _to_csv_url(url: str) -> str:
    """Convierte cualquier URL de Google Sheets a URL de exportación CSV."""
    # Ya es una URL de CSV
    if 'output=csv' in url or 'export?format=csv' in url:
        return url
    # pubhtml → pub?output=csv  (ej: .../d/e/LONG_ID/pubhtml)
    if '/pubhtml' in url:
        base = url.split('/pubhtml')[0]
        gid_m = re.search(r'[#&?]gid=(\d+)', url)
        gid = f'&gid={gid_m.group(1)}' if gid_m else ''
        return f'{base}/pub?output=csv{gid}'
    # URL con /d/e/LONG_ID (sheet publicada sin pubhtml)
    m = re.search(r'(/spreadsheets/d/e/[^/?#]+)', url)
    if m:
        return f'https://docs.google.com{m.group(1)}/pub?output=csv'
    # URL estándar con /d/ID (no /d/e/)
    m = re.search(r'/spreadsheets/d/([^/e][^/?#]*)', url)
    if m:
        sheet_id = m.group(1)
        gid_m = re.search(r'[#&?]gid=(\d+)', url)
        gid = f'&gid={gid_m.group(1)}' if gid_m else ''
        return f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv{gid}'
    # fallback
    sep = '&' if '?' in url else '?'
    return url + sep + 'output=csv'


def _fetch_rows(url: str) -> list[dict]:
    csv_url = _to_csv_url(url)
    timeout = current_app.config.get('SHEETS_TIMEOUT', 15)
    resp = requests.get(csv_url, timeout=(5, timeout))
    resp.encoding = 'utf-8'
    resp.raise_for_status()
    text = resp.text.strip()
    if text.startswith('<!') or text.lower().startswith('<html'):
        raise ValueError(
            'La hoja devolvió HTML en vez de CSV. '
            'Asegurate de que esté compartida como "cualquier persona con el enlace puede ver".'
        )
    # Normalizar headers: strip + lowercase para lookup case-insensitive
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        rows.append({k.strip().lower(): str(v).strip() for k, v in row.items() if k})
    return rows


def _split_sheet_urls(url: str) -> list[str]:
    return [u.strip() for u in re.split(r'[;\n]+', str(url or '')) if u.strip()]


def _sucursal_id_from_label(label: str) -> str:
    label_lower = label.strip().lower()
    for k, v in SUCURSAL_LABELS.items():
        if v.lower() == label_lower:
            return k
    return ''


def _infer_sucursal_from_url(url: str) -> str:
    source = str(url or '').lower()
    if 'gid=249846040' in source or 'gid=680588527' in source:
        return 'Dolores'
    if 'gid=0' in source or 'gid=1883083406' in source:
        return 'Casa Central'
    return ''


def _get(row: dict, *keys: str, default='') -> str:
    # Lookup case-insensitive (row keys ya están en lowercase desde _fetch_rows)
    for k in keys:
        if k.lower() in row:
            return row[k.lower()]
    return default


def get_equipos(url: str, fecha_filtro: str | None = None, sucursal_filtro: str | None = None) -> list[dict]:
    rows = _fetch_rows(url)
    result = []
    for r in rows:
        fn = norm_fecha(_get(r, 'Fecha', 'fecha'))
        if not fn:
            continue
        if fecha_filtro and fn != fecha_filtro:
            continue
        suc = _get(r, 'Sucursal', 'sucursal')
        if sucursal_filtro and suc.lower() != sucursal_filtro.lower():
            continue
        result.append({
            'fecha':          fn,
            'sucursal':       suc,
            'camion':         _get(r, 'Camion', 'Camión'),
            'nro_camion':     _get(r, 'N° Camion', 'Nro Camion'),
            'chofer':         _get(r, 'Chofer', 'Chofer / Responsable billetera'),
            'ayudante1':      _get(r, 'Ayudante1', 'Ayudante 1'),
            'ayudante2':      _get(r, 'Ayudante2', 'Ayudante 2'),
            'up':             _get(r, 'UP'),
            'clientes':       _get(r, 'CLIENTES', 'Clientes'),
            'personas':       _get(r, 'PERSONAS', 'Personas'),
            'pallets':        _get(r, 'Pallets'),
            'kms':            _get(r, 'KMS', 'Km', 'Kms'),
            'horas':          _get(r, 'Horas', 'hs'),
            'cargado_tiempo': _get(r, 'Cargado a tiempo?', 'Cargado a tiempo'),
        })
    return result


def get_disponibles(url: str, fecha_filtro: str | None = None, sucursal_filtro: str | None = None) -> list[dict]:
    rows = _fetch_rows(url)
    result = []
    for r in rows:
        fn = norm_fecha(_get(r, 'Fecha', 'fecha'))
        if not fn:
            continue
        if fecha_filtro and fn != fecha_filtro:
            continue
        suc = _get(r, 'Sucursal', 'sucursal')
        if sucursal_filtro and suc.lower() != sucursal_filtro.lower():
            continue
        result.append({
            'fecha':                fn,
            'sucursal':             suc,
            'camiones_disponibles': _get(r, 'Camiones disponibles', 'Camiones Disponibles', 'camiones_disponibles'),
            'personas_disponibles': _get(r, 'Personas disponibles', 'Personas Disponibles', 'personas_disponibles'),
            'camiones_en_taller':   _get(r, 'En taller', 'Camiones en taller'),
            'observaciones':        _get(r, 'Observaciones', 'Obs'),
        })
    return result


def _infer_sucursal_entrega(row: dict, fuente_url: str = '') -> str:
    sucursal_id = _get(row, 'sucursal_id', 'Sucursal ID', 'Id Sucursal')
    if sucursal_id:
        return SUCURSAL_LABELS.get(str(sucursal_id).strip(), str(sucursal_id).strip())
    explicit = _get(row, 'Sucursal', 'sucursal', 'Planta', 'planta')
    if explicit:
        return explicit
    source_sucursal = _infer_sucursal_from_url(fuente_url)
    if source_sucursal:
        return source_sucursal
    text = ' '.join(str(v or '') for v in row.values()).lower()
    if 'dolores' in text:
        return 'Dolores'
    if 'casa central' in text or 'central' in text:
        return 'Casa Central'
    return ''


def _matches_sucursal(row_sucursal: str, sucursal_filtro: str | None) -> bool:
    if not sucursal_filtro or sucursal_filtro == 'TODAS':
        return True
    if not row_sucursal:
        return False
    wanted = str(sucursal_filtro).strip().lower()
    wanted_label = SUCURSAL_LABELS.get(str(sucursal_filtro), str(sucursal_filtro)).strip().lower()
    current = str(row_sucursal).strip().lower()
    return current in {wanted, wanted_label}


def _num(value) -> float:
    return float(to_dec(value) or 0)


def _row_has_business_data(row: dict) -> bool:
    keys = (
        'Camion', 'CamiÃ³n', 'Chofer / Responsable billetera', 'Chofer',
        'Ayudante1', 'Ayudante 1', 'Ayudante2', 'Ayudante 2',
    )
    return any(str(_get(row, key) or '').strip() for key in keys)


def _aggregate_dotacion_items(
    items: list[dict],
    skipped_sin_fecha: int,
    sin_sucursal_total: int,
) -> dict:
    by_day: dict[str, dict] = {}
    choferes_globales: set[str] = set()
    ayudantes_globales: set[str] = set()
    camiones_distintos: set[str] = set()

    for item in items:
        fecha = item['fecha']
        truck_key = str(item.get('nro_camion') or item.get('camion') or '').strip()
        day = by_day.setdefault(fecha, {
            'fecha': fecha,
            'camiones': set(),
            'choferes': set(),
            'ayudantes': set(),
        })
        if truck_key:
            day['camiones'].add(truck_key)
            camiones_distintos.add(truck_key)
        if item.get('chofer'):
            day['choferes'].add(item['chofer'])
            choferes_globales.add(item['chofer'])
        for key in ('ayudante1', 'ayudante2'):
            if item.get(key):
                day['ayudantes'].add(item[key])
                ayudantes_globales.add(item[key])

    dias = []
    for day in sorted(by_day.values(), key=lambda x: x['fecha']):
        dias.append({
            'fecha': day['fecha'],
            'camiones': len(day['camiones']),
            'choferes': len(day['choferes']),
            'ayudantes': len(day['ayudantes']),
        })

    return {
        'resumen': {
            'registros': len(items),
            'dias_con_datos': len(dias),
            'camiones_jornada': sum(d['camiones'] for d in dias),
            'camiones_distintos': len(camiones_distintos),
            'choferes_distintos': len(choferes_globales),
            'ayudantes_distintos': len(ayudantes_globales),
            'filas_sin_sucursal': sin_sucursal_total,
            'filas_sin_fecha': skipped_sin_fecha,
        },
        'dias': dias,
    }


def _parse_dotacion_items(
    rows: list[dict],
    fecha_filtro: str | None,
    sucursal_filtro: str | None,
    mes_filtro: str | None,
    tipo: str,
) -> tuple[list[dict], int, int]:
    items = []
    skipped_sin_fecha = 0
    sin_sucursal_total = 0

    for r in rows:
        fecha = norm_fecha(_get(r, 'Fecha', 'fecha'))
        if not fecha:
            if _row_has_business_data(r):
                skipped_sin_fecha += 1
            continue
        if fecha_filtro and fecha != fecha_filtro:
            continue
        if mes_filtro and not fecha.startswith(mes_filtro):
            continue

        fuente_url = r.get('_fuente_url', '')
        sucursal = _infer_sucursal_entrega(r, fuente_url)
        if not sucursal:
            sin_sucursal_total += 1
        if not _matches_sucursal(sucursal, sucursal_filtro):
            continue

        chofer = _get(r, 'Chofer / Responsable billetera', 'Chofer', 'Responsable billetera')
        ayudante1 = _get(r, 'Ayudante1', 'Ayudante 1')
        ayudante2 = _get(r, 'Ayudante2', 'Ayudante 2')
        sucursal_id = _get(r, 'sucursal_id', 'Sucursal ID', 'Id Sucursal')
        nro_camion = _get(r, 'NÂ° Camion', 'Nro Camion', 'Nro. Camion', 'Numero Camion')

        items.append({
            'tipo': tipo,
            'fecha': fecha,
            'sucursal': sucursal,
            'sucursal_id': sucursal_id,
            'camion': _get(r, 'Camion', 'CamiÃ³n'),
            'nro_camion': nro_camion,
            'chofer': chofer,
            'ayudante1': ayudante1,
            'ayudante2': ayudante2,
        })

    return items, skipped_sin_fecha, sin_sucursal_total


def get_camiones_diarios(
    url: str | None = None,
    recargas_url: str | None = None,
    mes_filtro: str | None = None,
    sucursal_filtro: str | None = None,
) -> list[dict]:
    """Devuelve estadística diaria de dotación desde Google Sheets.

    Retorna por (sucursal_id, fecha):
    - camiones / choferes / ayudantes  → backward-compat (reparto + recarga deduplicados)
    - camiones_reparto, personas_reparto → solo reparto
    - recargas_count, camiones_recarga, personas_recargas → solo recargas
    - _camiones_usados  → set de códigos de camiones usados (para cruce con flota)
    """
    from flask import current_app
    url = url or current_app.config.get('DOTACION_ENTREGA_URL')
    recargas_url = recargas_url or current_app.config.get('DOTACION_RECARGAS_URL')
    if not url:
        raise ValueError('DOTACION_ENTREGA_URL no configurada.')

    rows: list[dict] = []
    for sheet_url in _split_sheet_urls(url):
        fetched = _fetch_rows(sheet_url)
        for row in fetched:
            row['_fuente_url'] = sheet_url
        rows.extend(fetched)

    recarga_rows: list[dict] = []
    for sheet_url in _split_sheet_urls(recargas_url or ''):
        fetched = _fetch_rows(sheet_url)
        for row in fetched:
            row['_fuente_url'] = sheet_url
        recarga_rows.extend(fetched)

    items, _, _ = _parse_dotacion_items(rows, None, sucursal_filtro, mes_filtro, 'REPARTO')
    rec_items, _, _ = _parse_dotacion_items(recarga_rows, None, sucursal_filtro, mes_filtro, 'RECARGA')

    by_suc_day: dict[tuple[str, str], dict] = {}

    def _suc_key(item: dict) -> str:
        suc_id = str(item.get('sucursal_id') or '').strip()
        return suc_id or _sucursal_id_from_label(str(item.get('sucursal') or '')) or 'DESCONOCIDA'

    def _truck_code(item: dict) -> str:
        return str(item.get('nro_camion') or item.get('camion') or '').strip()

    def _init_day(fecha: str, suc_id: str) -> dict:
        return {
            'fecha': fecha,
            'sucursal_id': suc_id,
            # reparto
            '_rep_camiones': set(),
            '_rep_choferes': set(),
            '_rep_ayudantes': set(),
            # recargas
            '_rec_camiones': set(),
            '_rec_choferes': set(),
            '_rec_ayudantes': set(),
            '_rec_rows': 0,
        }

    for item in items:
        suc_id = _suc_key(item)
        key = (suc_id, item['fecha'])
        day = by_suc_day.setdefault(key, _init_day(item['fecha'], suc_id))
        code = _truck_code(item)
        if code:
            day['_rep_camiones'].add(code)
        if item.get('chofer'):
            day['_rep_choferes'].add(item['chofer'])
        for ak in ('ayudante1', 'ayudante2'):
            if item.get(ak):
                day['_rep_ayudantes'].add(item[ak])

    for item in rec_items:
        suc_id = _suc_key(item)
        key = (suc_id, item['fecha'])
        day = by_suc_day.setdefault(key, _init_day(item['fecha'], suc_id))
        code = _truck_code(item)
        if code:
            day['_rec_camiones'].add(code)
        if item.get('chofer'):
            day['_rec_choferes'].add(item['chofer'])
        for ak in ('ayudante1', 'ayudante2'):
            if item.get(ak):
                day['_rec_ayudantes'].add(item[ak])
        day['_rec_rows'] += 1

    result = []
    for day in by_suc_day.values():
        all_camiones = day['_rep_camiones'] | day['_rec_camiones']
        all_choferes = day['_rep_choferes'] | day['_rec_choferes']
        personas_rep = len(day['_rep_choferes']) + len(day['_rep_ayudantes'])
        personas_rec = len(day['_rec_choferes']) + len(day['_rec_ayudantes'])
        result.append({
            'fecha': day['fecha'],
            'sucursal_id': day['sucursal_id'],
            # backward-compat
            'camiones': len(all_camiones),
            'choferes': len(all_choferes),
            'ayudantes': len(day['_rep_ayudantes'] | day['_rec_ayudantes']),
            # reparto
            'camiones_reparto': len(day['_rep_camiones']),
            'personas_reparto': personas_rep,
            # recargas
            'recargas_count': day['_rec_rows'],
            'camiones_recarga': len(day['_rec_camiones']),
            'personas_recargas': personas_rec,
            # set de codigos para cruce con flota (interno)
            '_camiones_usados': all_camiones,
        })

    return sorted(result, key=lambda x: (x['sucursal_id'], x['fecha']))


def get_dotacion_entrega(
    url: str | None = None,
    recargas_url: str | None = None,
    fecha_filtro: str | None = None,
    sucursal_filtro: str | None = None,
    mes_filtro: str | None = None,
) -> dict:
    url = url or current_app.config.get('DOTACION_ENTREGA_URL')
    recargas_url = recargas_url or current_app.config.get('DOTACION_RECARGAS_URL')
    if not url:
        raise ValueError('DOTACION_ENTREGA_URL no configurada.')

    rows = []
    for sheet_url in _split_sheet_urls(url):
        fetched = _fetch_rows(sheet_url)
        for row in fetched:
            row['_fuente_url'] = sheet_url
        rows.extend(fetched)

    recarga_rows = []
    for sheet_url in _split_sheet_urls(recargas_url):
        fetched = _fetch_rows(sheet_url)
        for row in fetched:
            row['_fuente_url'] = sheet_url
        recarga_rows.extend(fetched)

    items, skipped_sin_fecha, sin_sucursal_total = _parse_dotacion_items(
        rows, fecha_filtro, sucursal_filtro, mes_filtro, 'REPARTO'
    )
    recargas, skipped_sin_fecha_rec, sin_sucursal_rec = _parse_dotacion_items(
        recarga_rows, fecha_filtro, sucursal_filtro, mes_filtro, 'RECARGA'
    )

    reparto_agg = _aggregate_dotacion_items(items, skipped_sin_fecha, sin_sucursal_total)
    recarga_agg = _aggregate_dotacion_items(recargas, skipped_sin_fecha_rec, sin_sucursal_rec)

    resumen = reparto_agg['resumen']
    dias = reparto_agg['dias']
    resumen_recargas = recarga_agg['resumen']
    dias_recargas = recarga_agg['dias']
    resumen['recargas'] = resumen_recargas

    advertencias = []
    if sin_sucursal_total or sin_sucursal_rec:
        advertencias.append(
            'La hoja no trae sucursal explicita en todas las filas; para filtrar Casa Central/Dolores se recomienda agregar columna Sucursal.'
        )
    return {
        'resumen': resumen,
        'dias': dias,
        'items': items,
        'recargas': {
            'resumen': resumen_recargas,
            'dias': dias_recargas,
            'items': recargas,
        },
        'advertencias': advertencias,
        'fuente': 'google_sheet_dotacion_entrega',
        'fuentes_csv': len(_split_sheet_urls(url)),
        'fuentes_recargas_csv': len(_split_sheet_urls(recargas_url or '')),
    }


def sync_feriados(url: str) -> dict:
    """Import holidays from a Google Sheet into the feriados table."""
    from app.database import pg_conn
    from app.utils.coerce import to_date

    rows = _fetch_rows(url)
    if not rows:
        raise ValueError('El sheet no devolvió filas. Verificá que la URL sea correcta y la hoja tenga datos.')

    inserted = skipped = errors = 0

    with pg_conn() as conn:
        with conn.cursor() as cur:
            for r in rows:
                raw = _get(r, 'Fecha', 'fecha')
                if not raw:
                    skipped += 1
                    continue
                fd = to_date(raw)
                if not fd:
                    skipped += 1
                    continue
                try:
                    cur.execute('SAVEPOINT sp_fer')
                    cur.execute("""
                        INSERT INTO feriados (fecha, descripcion, tipo)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (fecha) DO UPDATE SET
                            descripcion = EXCLUDED.descripcion,
                            tipo        = EXCLUDED.tipo
                    """, (
                        fd,
                        _get(r, 'Descripcion', 'descripcion', 'Evento')[:200],
                        _get(r, 'Tipo', 'tipo', default='nacional')[:50],
                    ))
                    cur.execute('RELEASE SAVEPOINT sp_fer')
                    inserted += 1
                except Exception:
                    cur.execute('ROLLBACK TO SAVEPOINT sp_fer')
                    errors += 1

    return {'imported': inserted, 'skipped': skipped, 'errors': errors}
