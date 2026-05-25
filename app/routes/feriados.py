from datetime import date
from flask import Blueprint, request, jsonify
from app.database import pg_cursor, pg_conn
from app.services import cache_svc, sheets_svc
from app.utils.coerce import to_date

bp = Blueprint('feriados', __name__, url_prefix='/api/feriados')


@bp.get('', strict_slashes=False)
def listar():
    anio = request.args.get('anio', date.today().year, type=int)
    with pg_cursor() as cur:
        cur.execute("""
            SELECT fecha::text, descripcion, tipo FROM feriados
            WHERE EXTRACT(YEAR FROM fecha) = %s
            ORDER BY fecha
        """, (anio,))
        return jsonify([dict(r) for r in cur.fetchall()])


@bp.post('/sync')
def sync():
    data = request.json or {}
    url  = data.get('sheets_url', '').strip()
    if not url:
        return jsonify({'error': 'sheets_url requerida'}), 400
    try:
        result = sheets_svc.sync_feriados(url)
        cache_svc.clear('picos:')
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 503


@bp.post('', strict_slashes=False)
def agregar():
    data = request.json or {}
    if data.get('sheets_url'):
        return sync()

    fd   = to_date(data.get('fecha'))
    if not fd:
        return jsonify({'error': 'fecha invalida'}), 400
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO feriados (fecha, descripcion, tipo)
                VALUES (%s, %s, %s)
                ON CONFLICT (fecha) DO UPDATE SET
                    descripcion = EXCLUDED.descripcion,
                    tipo        = EXCLUDED.tipo
            """, (fd, data.get('descripcion', '')[:200], data.get('tipo', 'nacional')[:50]))
    cache_svc.clear('picos:')
    return jsonify({'ok': True})


@bp.delete('/mes/<int:anio>/<int:mes>')
def limpiar_mes(anio: int, mes: int):
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM feriados
                WHERE EXTRACT(YEAR FROM fecha) = %s
                  AND EXTRACT(MONTH FROM fecha) = %s
            """, (anio, mes))
            deleted = cur.rowcount
    cache_svc.clear('picos:')
    return jsonify({'deleted': deleted})


@bp.delete('/anio/<int:anio>')
def limpiar_anio(anio: int):
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM feriados WHERE EXTRACT(YEAR FROM fecha) = %s", (anio,))
            deleted = cur.rowcount
    cache_svc.clear('picos:')
    return jsonify({'deleted': deleted})


@bp.delete('/<fecha_str>')
def eliminar(fecha_str: str):
    fd = to_date(fecha_str)
    if not fd:
        return jsonify({'error': 'fecha invalida'}), 400
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM feriados WHERE fecha = %s", (fd,))
    cache_svc.clear('picos:')
    return jsonify({'ok': True})
