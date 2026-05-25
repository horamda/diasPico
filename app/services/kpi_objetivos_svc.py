from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.database import pg_conn, pg_cursor

_KPI_OBJETIVOS_READY = False

SUCURSAL_LABELS = {
    '1': 'Casa Central',
    '2': 'Dolores',
}

INDICADORES = {
    'pct_rechazo_hl': {
        'nombre': '% rechazo HL',
        'unidad': '%',
        'direccion': 'max',
    },
    'pct_rechazo_bultos': {
        'nombre': '% rechazo bultos',
        'unidad': '%',
        'direccion': 'max',
    },
    'pct_rechazo_pedidos': {
        'nombre': '% rechazo PDV',
        'unidad': '%',
        'direccion': 'max',
    },
    'rmcyo_pct_rechazo_hl': {
        'nombre': '% RMCYO rechazo HL',
        'unidad': '%',
        'direccion': 'max',
    },
    'rmcyo_pct_rechazo_bultos': {
        'nombre': '% RMCYO rechazo bultos',
        'unidad': '%',
        'direccion': 'max',
    },
    'rmcyo_pct_rechazo_pedidos': {
        'nombre': '% RMCYO rechazo PDV',
        'unidad': '%',
        'direccion': 'max',
    },
}

DDL = """
CREATE TABLE IF NOT EXISTS kpi_objetivos (
    id BIGSERIAL PRIMARY KEY,
    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50),
    indicador VARCHAR(80) NOT NULL,
    nombre VARCHAR(120) NOT NULL,
    unidad VARCHAR(20) NOT NULL DEFAULT '',
    direccion VARCHAR(10) NOT NULL CHECK (direccion IN ('max', 'min')),
    objetivo NUMERIC(14,4) NOT NULL,
    alerta NUMERIC(14,4),
    fecha_desde DATE NOT NULL,
    fecha_hasta DATE,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""


def ensure_table() -> None:
    global _KPI_OBJETIVOS_READY
    if _KPI_OBJETIVOS_READY:
        return
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                {DDL};
                CREATE INDEX IF NOT EXISTS idx_kpi_obj_suc_ind_activo
                    ON kpi_objetivos(sucursal_id, indicador, activo);
                CREATE INDEX IF NOT EXISTS idx_kpi_obj_fechas
                    ON kpi_objetivos(fecha_desde, fecha_hasta);
            """)
    _KPI_OBJETIVOS_READY = True


def _to_float(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _round(value, digits: int = 4) -> float:
    return round(_to_float(value), digits)


def _row_to_dict(row) -> dict:
    return {
        'id': row['id'],
        'empresa_id': row['empresa_id'],
        'sucursal_id': row['sucursal_id'],
        'sucursal': SUCURSAL_LABELS.get(row['sucursal_id'], row['sucursal_id'] or 'Todas'),
        'indicador': row['indicador'],
        'nombre': row['nombre'],
        'unidad': row['unidad'],
        'direccion': row['direccion'],
        'objetivo': _round(row['objetivo']),
        'alerta': _round(row['alerta']) if row['alerta'] is not None else None,
        'fecha_desde': row['fecha_desde'].isoformat(),
        'fecha_hasta': row['fecha_hasta'].isoformat() if row['fecha_hasta'] else None,
        'activo': bool(row['activo']),
    }


def list_indicadores() -> list[dict]:
    return [
        {'codigo': codigo, **meta}
        for codigo, meta in INDICADORES.items()
    ]


def list_objetivos(sucursal: str | None = None) -> list[dict]:
    ensure_table()
    params = {}
    where = ''
    if sucursal and sucursal != 'TODAS':
        where = 'WHERE sucursal_id IS NULL OR sucursal_id = %(s)s'
        params['s'] = sucursal
    with pg_cursor() as cur:
        cur.execute(f"""
            SELECT id, empresa_id, sucursal_id, indicador, nombre, unidad, direccion,
                   objetivo, alerta, fecha_desde, fecha_hasta, activo
            FROM kpi_objetivos
            {where}
            ORDER BY activo DESC, indicador, sucursal_id NULLS FIRST, fecha_desde DESC, id DESC
        """, params)
        rows = cur.fetchall()
    return [_row_to_dict(r) for r in rows]


def save_objetivo(data: dict) -> dict:
    ensure_table()
    indicador = str(data.get('indicador') or '').strip()
    if indicador not in INDICADORES:
        raise ValueError('Indicador invalido')

    meta = INDICADORES[indicador]
    objetivo = float(data.get('objetivo', 0))
    alerta_raw = data.get('alerta')
    alerta = float(alerta_raw) if alerta_raw not in (None, '') else None
    if objetivo < 0 or (alerta is not None and alerta < 0):
        raise ValueError('Los objetivos no pueden ser negativos')

    direccion = meta['direccion']
    if alerta is not None:
        if direccion == 'max' and alerta < objetivo:
            raise ValueError('Para objetivos maximos, alerta debe ser mayor o igual al objetivo')
        if direccion == 'min' and alerta > objetivo:
            raise ValueError('Para objetivos minimos, alerta debe ser menor o igual al objetivo')

    fecha_desde = date.fromisoformat(str(data.get('fecha_desde') or date.today().isoformat()))
    fecha_hasta_raw = data.get('fecha_hasta') or None
    fecha_hasta = date.fromisoformat(str(fecha_hasta_raw)) if fecha_hasta_raw else None
    if fecha_hasta and fecha_hasta < fecha_desde:
        raise ValueError('fecha_hasta debe ser mayor o igual a fecha_desde')

    sucursal = data.get('sucursal_id') or data.get('sucursal')
    sucursal_id = None if not sucursal or sucursal == 'TODAS' else str(sucursal)
    empresa_id = str(data.get('empresa_id') or '1')
    activo = bool(data.get('activo', True))
    objetivo_id = data.get('id')

    params = {
        'empresa_id': empresa_id,
        'sucursal_id': sucursal_id,
        'indicador': indicador,
        'nombre': meta['nombre'],
        'unidad': meta['unidad'],
        'direccion': direccion,
        'objetivo': objetivo,
        'alerta': alerta,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'activo': activo,
    }

    with pg_cursor() as cur:
        if objetivo_id:
            params['id'] = int(objetivo_id)
            cur.execute("""
                UPDATE kpi_objetivos
                SET empresa_id=%(empresa_id)s,
                    sucursal_id=%(sucursal_id)s,
                    indicador=%(indicador)s,
                    nombre=%(nombre)s,
                    unidad=%(unidad)s,
                    direccion=%(direccion)s,
                    objetivo=%(objetivo)s,
                    alerta=%(alerta)s,
                    fecha_desde=%(fecha_desde)s,
                    fecha_hasta=%(fecha_hasta)s,
                    activo=%(activo)s,
                    updated_at=NOW()
                WHERE id=%(id)s
                RETURNING id
            """, params)
            row = cur.fetchone()
            if not row:
                raise ValueError('Objetivo no encontrado')
            saved_id = row['id']
        else:
            cur.execute("""
                INSERT INTO kpi_objetivos (
                    empresa_id, sucursal_id, indicador, nombre, unidad, direccion,
                    objetivo, alerta, fecha_desde, fecha_hasta, activo
                )
                VALUES (
                    %(empresa_id)s, %(sucursal_id)s, %(indicador)s, %(nombre)s,
                    %(unidad)s, %(direccion)s, %(objetivo)s, %(alerta)s,
                    %(fecha_desde)s, %(fecha_hasta)s, %(activo)s
                )
                RETURNING id
            """, params)
            saved_id = cur.fetchone()['id']

    return {'ok': True, 'id': saved_id}


def delete_objetivo(objetivo_id: int | str) -> dict:
    ensure_table()
    try:
        objetivo_id = int(objetivo_id)
    except (TypeError, ValueError):
        raise ValueError('ID de objetivo invalido')

    with pg_cursor() as cur:
        cur.execute('DELETE FROM kpi_objetivos WHERE id = %s', (objetivo_id,))
        if cur.rowcount == 0:
            raise ValueError('Objetivo no encontrado')
    return {'ok': True, 'id': objetivo_id}


def _semaforo(valor: float, objetivo: dict) -> dict:
    obj = _to_float(objetivo['objetivo'])
    alerta = objetivo.get('alerta')
    alerta_f = _to_float(alerta) if alerta is not None else None
    direccion = objetivo['direccion']

    if direccion == 'max':
        if valor <= obj:
            estado, label = 'verde', 'Cumple'
        elif alerta_f is not None and valor <= alerta_f:
            estado, label = 'amarillo', 'Alerta'
        else:
            estado, label = 'rojo', 'Fuera'
    else:
        if valor >= obj:
            estado, label = 'verde', 'Cumple'
        elif alerta_f is not None and valor >= alerta_f:
            estado, label = 'amarillo', 'Alerta'
        else:
            estado, label = 'rojo', 'Fuera'

    return {
        'estado': estado,
        'label': label,
        'valor': round(valor, 4),
        'objetivo': objetivo,
    }


def evaluar(kpis: dict, sucursal: str, fecha_ref: date) -> dict:
    ensure_table()
    with pg_cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (indicador)
                   id, empresa_id, sucursal_id, indicador, nombre, unidad, direccion,
                   objetivo, alerta, fecha_desde, fecha_hasta, activo
            FROM kpi_objetivos
            WHERE activo = TRUE
              AND fecha_desde <= %(fecha)s
              AND (fecha_hasta IS NULL OR fecha_hasta >= %(fecha)s)
              AND (sucursal_id IS NULL OR sucursal_id = %(sucursal)s)
            ORDER BY indicador, (sucursal_id = %(sucursal)s) DESC, fecha_desde DESC, id DESC
        """, {'fecha': fecha_ref, 'sucursal': None if sucursal == 'TODAS' else sucursal})
        rows = cur.fetchall()

    objetivos = {}
    for r in rows:
        indicador = r['indicador']
        if indicador not in kpis:
            continue
        objetivos[indicador] = _semaforo(float(kpis.get(indicador) or 0), _row_to_dict(r))
    return objetivos
