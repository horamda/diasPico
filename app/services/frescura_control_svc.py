"""Timed freshness sessions. All timestamps and durations are server-owned."""
from datetime import date, datetime, timezone

import psycopg2.extras

from app.database import pg_conn, pg_cursor


SCHEMA = """
CREATE TABLE IF NOT EXISTS control_frescura_sesiones (
    id BIGSERIAL PRIMARY KEY,
    sucursal VARCHAR(20) NOT NULL,
    fecha DATE NOT NULL,
    responsable VARCHAR(120) NOT NULL,
    iniciado_at TIMESTAMPTZ NOT NULL,
    activo_desde TIMESTAMPTZ,
    finalizado_at TIMESTAMPTZ,
    segundos_activos NUMERIC NOT NULL DEFAULT 0,
    estado VARCHAR(20) NOT NULL DEFAULT 'activo',
    borrador JSONB NOT NULL DEFAULT '{}'::jsonb,
    conteo_id BIGINT REFERENCES control_frescura_conteos(id),
    UNIQUE(sucursal, fecha, responsable)
);
ALTER TABLE control_frescura_conteos ADD COLUMN IF NOT EXISTS iniciado_at TIMESTAMPTZ;
ALTER TABLE control_frescura_conteos ADD COLUMN IF NOT EXISTS finalizado_at TIMESTAMPTZ;
ALTER TABLE control_frescura_conteos ADD COLUMN IF NOT EXISTS segundos_activos NUMERIC;
ALTER TABLE control_frescura_conteos ADD COLUMN IF NOT EXISTS segundos_transcurridos NUMERIC;
"""


def now():
    return datetime.now(timezone.utc)


def timing(row, instant):
    active = float(row.get('segundos_activos') or 0)
    if row.get('estado') == 'activo' and row.get('activo_desde'):
        active += max(0, (instant - row['activo_desde']).total_seconds())
    end = row.get('finalizado_at') or instant
    return {'segundos_activos': round(active, 2),
            'segundos_transcurridos': round(max(0, (end - row['iniciado_at']).total_seconds()), 2)}


def public_session(row):
    return {**row, **timing(row, now()),
            'fecha': row['fecha'].isoformat(),
            'iniciado_at': row['iniciado_at'].isoformat(),
            'activo_desde': row['activo_desde'].isoformat() if row.get('activo_desde') else None,
            'finalizado_at': row['finalizado_at'].isoformat() if row.get('finalizado_at') else None}


def draft_keys(draft):
    if not isinstance(draft, dict) or not isinstance(draft.get('rows'), list) or not 0 < len(draft['rows']) <= 10000:
        raise ValueError('Carga una planilla valida antes de iniciar')
    keys = []
    for row in draft['rows']:
        if not isinstance(row, dict) or not row.get('codigo_articulo') or not row.get('lote'):
            raise ValueError('Cada lote debe tener articulo e identificacion')
        keys.append((str(row['codigo_articulo']), str(row['lote'])))
    if len(set(keys)) != len(keys):
        raise ValueError('La planilla contiene lotes duplicados')
    return set(keys)


def start(payload):
    from app.services.control_stock_svc import ensure_control_stock_tables, _sucursal_id
    ensure_control_stock_tables()
    control_date = date.fromisoformat(str(payload.get('fecha') or ''))
    name = str(payload.get('responsable') or '').strip()
    if not name or len(name) > 120:
        raise ValueError('Selecciona un operario valido')
    branch = _sucursal_id(payload.get('sucursal'))
    draft = payload.get('borrador') or {}
    draft_keys(draft)
    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute('SELECT id FROM control_frescura_conteos WHERE sucursal=%s AND fecha=%s AND responsable=%s',
                        (branch, control_date, name))
            if cur.fetchone():
                raise ValueError('Este operario ya tiene un control finalizado para esta fecha y sucursal. Consulta el historial.')
            cur.execute("""INSERT INTO control_frescura_sesiones
                (sucursal, fecha, responsable, iniciado_at, activo_desde, borrador)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (sucursal, fecha, responsable) DO NOTHING""",
                (branch, control_date, name, now(), now(), psycopg2.extras.Json(draft)))
            cur.execute('SELECT * FROM control_frescura_sesiones WHERE sucursal=%s AND fecha=%s AND responsable=%s',
                        (branch, control_date, name))
            row = dict(cur.fetchone())
    if row['estado'] == 'finalizado':
        raise ValueError('Este operario ya finalizo el control de esta fecha y sucursal')
    return public_session(row)


def update(session_id, payload):
    from app.services.control_stock_svc import ensure_control_stock_tables
    ensure_control_stock_tables()
    action = payload.get('accion', 'borrador')
    if action not in {'borrador', 'pausar', 'reanudar'}:
        raise ValueError('Accion de sesion invalida')
    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute('SELECT * FROM control_frescura_sesiones WHERE id=%s FOR UPDATE', (session_id,))
            row = cur.fetchone()
            if not row or row['estado'] == 'finalizado':
                raise ValueError('Sesion inexistente o finalizada')
            instant = now()
            active = timing(row, instant)['segundos_activos']
            state = 'pausado' if action == 'pausar' else 'activo' if action == 'reanudar' else row['estado']
            draft = payload.get('borrador', row['borrador'])
            # A session keeps its initial scope, even when saving a partial draft.
            initial_keys = draft_keys(row['borrador'])
            if draft_keys(draft) != initial_keys:
                raise ValueError('El borrador debe conservar todos los lotes de la sesion')
            preserve_reference(row['borrador']['rows'], draft['rows'])
            cur.execute('''UPDATE control_frescura_sesiones SET estado=%s, segundos_activos=%s,
                activo_desde=%s, borrador=%s WHERE id=%s RETURNING *''',
                (state, active, instant if state == 'activo' else None, psycopg2.extras.Json(draft), session_id))
            result = dict(cur.fetchone())
    return public_session(result)


def lock_for_finish(cur, session_id, branch, control_date, name, items):
    cur.execute('SELECT * FROM control_frescura_sesiones WHERE id=%s FOR UPDATE', (session_id,))
    row = cur.fetchone()
    if not row or row['estado'] != 'activo':
        raise ValueError('Inicia o reanuda el control antes de finalizar')
    if (row['sucursal'], row['fecha'], row['responsable']) != (branch, control_date, name):
        raise ValueError('La sucursal, fecha y operario deben coincidir con el control iniciado')
    expected = {(r['codigo_articulo'], r['lote']) for r in row['borrador']['rows']}
    received = {(r.get('codigo_articulo'), r.get('lote')) for r in items}
    if received != expected or len(items) != len(expected):
        raise ValueError('Revisa todos los lotes antes de finalizar')
    for item in items:
        groups = item.get('distribucion_fechas') or []
        if groups:
            if any(g.get('revision') not in {'OK', 'NO_OK'} for g in groups):
                raise ValueError('Quedan pallets pendientes de revision')
        elif item.get('revision') not in {'OK', 'NO_OK'}:
            raise ValueError('Quedan lotes pendientes de revision')
        elif (item['revision'] == 'OK') != (item.get('fecha_vencimiento') == item.get('fecha_vencimiento_sistema')):
            raise ValueError('La revision del lote debe coincidir con la fecha real informada')
    preserve_reference(row['borrador']['rows'], items)
    return dict(row)


def preserve_reference(original, current):
    reference = {(r['codigo_articulo'], r['lote']): r for r in original}
    for item in current:
        old = reference[(item['codigo_articulo'], item['lote'])]
        for field in ('stock_sistema_bultos', 'stock_sistema_unidades', 'fecha_vencimiento_sistema'):
            if item.get(field) != old.get(field):
                raise ValueError('El stock y vencimiento esperados no pueden modificarse durante el control')


def finish(cur, row, count_id):
    instant = now()
    times = timing(row, instant)
    cur.execute('''UPDATE control_frescura_sesiones SET estado='finalizado', finalizado_at=%s,
        activo_desde=NULL, segundos_activos=%s, conteo_id=%s WHERE id=%s''',
        (instant, times['segundos_activos'], count_id, row['id']))
    cur.execute('''UPDATE control_frescura_conteos SET iniciado_at=%s, finalizado_at=%s,
        segundos_activos=%s, segundos_transcurridos=%s WHERE id=%s''',
        (row['iniciado_at'], instant, times['segundos_activos'], times['segundos_transcurridos'], count_id))
    return {**times, 'iniciado_at': row['iniciado_at'].isoformat(), 'finalizado_at': instant.isoformat()}


def history(desde, hasta, sucursal='', responsable=''):
    from app.services.control_stock_svc import ensure_control_stock_tables
    ensure_control_stock_tables()
    start_date, end_date = date.fromisoformat(desde), date.fromisoformat(hasta)
    if end_date < start_date:
        raise ValueError('El fin del periodo debe ser posterior al inicio')
    with pg_cursor() as cur:
        cur.execute('''SELECT c.id, c.sucursal, c.fecha, c.responsable, c.iniciado_at, c.finalizado_at,
            c.segundos_activos, c.segundos_transcurridos, COUNT(i.codigo_articulo) AS lotes,
            COUNT(i.codigo_articulo) FILTER (WHERE i.diferencia OR i.diferencia_fecha) AS lotes_no_ok
            FROM control_frescura_conteos c LEFT JOIN control_frescura_conteo_items i ON i.conteo_id=c.id
            WHERE c.fecha BETWEEN %s AND %s AND (%s='' OR c.sucursal=%s)
            AND (%s='' OR c.responsable=%s)
            GROUP BY c.id ORDER BY c.fecha DESC, c.id DESC''',
            (start_date, end_date, sucursal, sucursal, responsable, responsable))
        rows = [dict(r) for r in cur.fetchall()]
    totals = {}
    for row in rows:
        key = (row['sucursal'], row['responsable'])
        total = totals.setdefault(key, {'sucursal': key[0], 'responsable': key[1], 'controles': 0,
                                       'segundos_activos': 0, 'controles_con_tiempo': 0, 'lotes_no_ok': 0})
        total['controles'] += 1
        total['lotes_no_ok'] += row['lotes_no_ok']
        if row['segundos_activos'] is not None:
            total['controles_con_tiempo'] += 1
            total['segundos_activos'] += float(row['segundos_activos'])
        for field in ('fecha', 'iniciado_at', 'finalizado_at'):
            row[field] = row[field].isoformat() if row[field] else None
    return {'rows': rows, 'resumen': list(totals.values())}
