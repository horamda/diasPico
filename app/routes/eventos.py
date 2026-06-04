import calendar as cal_mod
from datetime import date
from flask import Blueprint, request, jsonify
from app.database import pg_cursor, pg_conn
from app.services import cache_svc
from app.utils.coerce import to_date

bp = Blueprint('eventos', __name__, url_prefix='/api/eventos')


def _clear_dashboard_caches():
    cache_svc.clear('picos:')
    cache_svc.clear('portal:')


_DDL = """
    CREATE TABLE IF NOT EXISTS eventos_especiales (
        id          SERIAL PRIMARY KEY,
        fecha       DATE NOT NULL,
        sucursal    VARCHAR(50) NOT NULL DEFAULT 'TODAS',
        descripcion VARCHAR(255) NOT NULL,
        created_at  TIMESTAMP DEFAULT NOW(),
        UNIQUE (fecha, sucursal)
    )
"""

_EVENTOS_READY = False


def _ensure_table(cur) -> None:
    global _EVENTOS_READY
    if _EVENTOS_READY:
        return
    cur.execute(_DDL)
    _EVENTOS_READY = True


@bp.get('', strict_slashes=False)
def listar():
    mes      = request.args.get('mes')
    sucursal = request.args.get('sucursal', 'TODAS')
    with pg_cursor() as cur:
        _ensure_table(cur)
        if mes:
            try:
                y, m = int(mes.split('-')[0]), int(mes.split('-')[1])
                ini  = date(y, m, 1)
                fin  = date(y, m, cal_mod.monthrange(y, m)[1])
            except Exception:
                return jsonify({'error': 'mes inválido (YYYY-MM)'}), 400
            if sucursal == 'TODAS':
                cur.execute("""
                    SELECT id, fecha::text, sucursal, descripcion
                    FROM eventos_especiales
                    WHERE fecha BETWEEN %s AND %s
                    ORDER BY fecha, sucursal
                """, (ini, fin))
            else:
                cur.execute("""
                    SELECT id, fecha::text, sucursal, descripcion
                    FROM eventos_especiales
                    WHERE fecha BETWEEN %s AND %s
                      AND (sucursal = %s OR sucursal = 'TODAS')
                    ORDER BY fecha
                """, (ini, fin, sucursal))
        else:
            cur.execute("""
                SELECT id, fecha::text, sucursal, descripcion
                FROM eventos_especiales ORDER BY fecha DESC LIMIT 60
            """)
        return jsonify([dict(r) for r in cur.fetchall()])


@bp.post('', strict_slashes=False)
def agregar():
    data = request.json or {}
    fd   = to_date(data.get('fecha'))
    if not fd:
        return jsonify({'error': 'fecha inválida'}), 400
    sucursal = str(data.get('sucursal') or 'TODAS')[:50]
    desc     = str(data.get('descripcion') or '').strip()[:255]
    if not desc:
        return jsonify({'error': 'descripcion requerida'}), 400
    with pg_conn() as conn:
        with conn.cursor() as cur:
            _ensure_table(cur)
            cur.execute("""
                INSERT INTO eventos_especiales (fecha, sucursal, descripcion)
                VALUES (%s, %s, %s)
                ON CONFLICT (fecha, sucursal) DO UPDATE SET descripcion = EXCLUDED.descripcion
                RETURNING id
            """, (fd, sucursal, desc))
            row = cur.fetchone()
    _clear_dashboard_caches()
    return jsonify({'ok': True, 'id': row[0]})


@bp.delete('/<int:evento_id>')
def eliminar(evento_id: int):
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM eventos_especiales WHERE id = %s", (evento_id,))
    _clear_dashboard_caches()
    return jsonify({'ok': True})
