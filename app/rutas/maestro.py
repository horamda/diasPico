"""Read the portal master; preserve decisions made by delivery planners."""
import math
from collections import defaultdict
from datetime import datetime
from app.database import pg_cursor
from .db import Session
from .models import Cliente, ClienteEntrega, Deposito, Localidad, SyncLog
from .localidades import normalizar_nombre, SUCURSAL_POR_LOCALIDAD


def leer_maestro():
    with pg_cursor() as cur:
        cur.execute("SELECT to_regclass('public.clientes') AS tabla")
        if not cur.fetchone()['tabla']:
            raise ValueError('Primero cargá el maestro en Importaciones de datos.')
        cur.execute('SELECT to_jsonb(c) AS datos FROM clientes c')
        rows = [r['datos'] for r in cur.fetchall()]
        cur.execute("SELECT to_regclass('public.sucursales') AS tabla")
        branches = {'1': 'CASA CENTRAL', '2': 'DOLORES'}
        if cur.fetchone()['tabla']:
            cur.execute('SELECT id, nombre FROM sucursales')
            branches.update({str(r['id']): r['nombre'].strip().upper() for r in cur.fetchall()})
    return rows, branches


def coordenadas(row):
    for x, y in [('coord_x_entrega', 'coord_y_entrega'), ('coord_x', 'coord_y')]:
        try:
            lng, lat = (float(str(row[k]).replace(',', '.')) for k in (x, y))
            if math.isfinite(lat) and math.isfinite(lng) and -41.5 < lat < -33 and -63.5 < lng < -56:
                return lat, lng
        except (KeyError, TypeError, ValueError):
            pass
    return None, None


def cliente_activo(row):
    """Delivery eligibility uses the master visit-day rule, not delivery-day assignments."""
    anulado = str(row.get('anulado') or '').strip().upper()
    dias_visita = str(row.get('fuerza_venta_1_dias_visita') or '').strip().upper()
    return (row.get('activo_maestro') is not False and anulado == 'NO'
            and bool(dias_visita) and dias_visita != 'DOM')


def actualizar_desde_maestro(usuario, source=None):
    rows, branches = source if source is not None else leer_maestro()
    if not rows:
        raise ValueError('El maestro está vacío. Cargalo en Importaciones de datos.')
    ids = defaultdict(list)
    for r in rows:
        raw = str(r.get('cliente') or '').strip()
        if raw.isdecimal() and 0 < int(raw) <= 2147483647:
            ids[int(raw)].append(r)
    valid = {k: v[0] for k, v in ids.items() if len(v) == 1}
    if not valid:
        raise ValueError('No hay códigos numéricos únicos compatibles con Rutas.')
    s = Session()
    try:
        if s.bind.dialect.name == 'postgresql':
            from sqlalchemy import text
            s.execute(text('SELECT pg_advisory_xact_lock(7319021)'))
        now = datetime.utcnow()
        deps = {d.nombre: d for d in s.query(Deposito)}
        for name in set(branches.values()) | set(SUCURSAL_POR_LOCALIDAD.values()):
            if name not in deps:
                deps[name] = Deposito(nombre=name)
                s.add(deps[name])
        s.flush()
        loc_branches = defaultdict(set)
        for r in valid.values():
            loc = normalizar_nombre(r.get('localidad'))[:80]
            branch = branches.get(str(r.get('sucursal') or '').strip())
            if loc:
                loc_branches[loc].add(branch)
        locs = {normalizar_nombre(l.nombre): l for l in s.query(Localidad)}
        for name, branch in SUCURSAL_POR_LOCALIDAD.items():
            if name in locs:
                locs[name].deposito_id = deps[branch].id
            else:
                locs[name] = Localidad(nombre=name, deposito_id=deps[branch].id)
                s.add(locs[name])
        for name, options in loc_branches.items():
            if name not in locs:
                branch = next(iter(options)) if len(options) == 1 else None
                s.add(Localidad(nombre=name, deposito_id=deps[branch].id if branch else None))
        existing = {c.id_cliente: c for c in s.query(Cliente)}
        new = 0
        for cid, r in valid.items():
            c = existing.get(cid)
            if c is None:
                c = Cliente(id_cliente=cid)
                c.entrega = ClienteEntrega(id_cliente=cid, dias='', en_planilla=False,
                                           actualizado=now, actualizado_por=usuario)
                s.add(c)
                new += 1
            suc = str(r.get('sucursal') or '').strip()
            c.id_sucursal_erp = int(suc) if suc.isdecimal() else None
            c.razon_social = str(r.get('razon_social') or r.get('descripcion') or '')[:200]
            c.fantasia = str(r.get('nombre_fantasia') or r.get('descripcion') or '')[:200]
            c.domicilio = str(r.get('domicilio') or '')[:200]
            c.localidad_erp = normalizar_nombre(r.get('localidad'))[:80]
            c.lat, c.lng = coordenadas(r)
            c.horario = str(r.get('horario_entrega') or '')[:120]
            # This flag drives inactive-client filtering throughout Rutas and CSV import.
            c.anulado = not cliente_activo(r)
            c.sincronizado = now
            # The master contains visit days, not delivery days. Do not equate them.
        s.add(SyncLog(origen='maestro', inicio=now, fin=now, leidos=len(valid), nuevos=new,
                      actualizados=len(valid)-new))
        s.commit()
        return {'leidos': len(valid), 'nuevos': new, 'actualizados': len(valid)-new,
                'omitidos': len(rows)-len(valid)}
    except Exception:
        s.rollback()
        raise
