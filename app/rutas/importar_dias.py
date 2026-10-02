"""CSV delivery-day import with signed previews and atomic, repeat-safe confirmation."""
import csv
import hashlib
import io
import json
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

from flask import current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature
from sqlalchemy import text
from .db import Session
from .models import Cliente, ClienteEntrega, CambioLog, ImportacionDias

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20000
ES = ('LUNES', 'MARTES', 'MIERCOLES', 'JUEVES', 'VIERNES', 'SABADO')
DIAS = ('LU', 'MA', 'MI', 'JU', 'VI', 'SA')


def normalizar(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value.strip().upper())
                   if not unicodedata.combining(c))


def leer_csv(content):
    if not content or len(content) > MAX_BYTES:
        raise ValueError('El CSV está vacío o supera los 5 MB.')
    try:
        decoded = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            decoded = content.decode('cp1252')
        except UnicodeDecodeError as exc:
            raise ValueError('Guardá el archivo como CSV UTF-8.') from exc
    if '\x00' in decoded:
        raise ValueError('El archivo no es un CSV de texto válido.')
    header = decoded.splitlines()[0]
    delimiter = max((';', ',', '\t'), key=header.count)
    reader = csv.DictReader(io.StringIO(decoded, newline=''), delimiter=delimiter, strict=True)
    try:
        fields = [normalizar(h) for h in (reader.fieldnames or [])]
        if len(set(fields)) != len(fields):
            raise ValueError('Hay columnas duplicadas en el encabezado.')
        reader.fieldnames = fields
        if 'CLIENTE' not in fields or not all(h in fields for h in ES):
            raise ValueError('Se requiere CLIENTE y las columnas LUNES a SABADO.')
        rows = []
        for row in reader:
            if len(rows) >= MAX_ROWS:
                raise ValueError('El archivo supera las 20.000 filas.')
            if not any(v for v in row.values()):
                continue
            item = {'fila': reader.line_num, 'cliente': str(row.get('CLIENTE') or '').strip(), 'dias': '', 'error': ''}
            try:
                if None in row or any(v is None for v in row.values()):
                    raise ValueError('Cantidad de columnas incorrecta')
                raw = item['cliente']
                if not raw.isdecimal() or not 0 < int(raw) <= 2147483647:
                    raise ValueError('Código de cliente inválido')
                item['id'] = int(raw)
                values = [normalizar(row[h]) for h in ES]
                if any(v not in {'1', '', '0'} for v in values):
                    raise ValueError('Marca de día inválida: usá 1, vacío o 0')
                item['dias'] = ''.join(d for d, v in zip(DIAS, values) if v == '1')
            except ValueError as exc:
                item['error'] = str(exc)
            rows.append(item)
    except csv.Error as exc:
        raise ValueError('CSV mal formado: revisá comillas y separadores.') from exc
    if not rows:
        raise ValueError('El archivo no contiene clientes.')
    counts = Counter(r.get('id') for r in rows if r.get('id'))
    for row in rows:
        if counts[row.get('id')] > 1:
            row['error'] = 'Cliente duplicado: se excluyen todas sus filas'
    return rows


def serializer():
    return URLSafeTimedSerializer(current_app.secret_key, salt='rutas-importar-dias-v1')


def estado(entrega):
    return None if entrega is None else [entrega.dias or '', entrega.actualizado.isoformat() if entrega.actualizado else None]


def preparar(content, archivo, usuario, modo='vacios', actor=None):
    if modo not in {'vacios', 'reemplazar'}:
        raise ValueError('Modo de importación inválido.')
    rows = leer_csv(content)
    clients = {c.id_cliente: c for c in Session().query(Cliente)}
    changes, summary = [], Counter()
    for row in rows:
        c = clients.get(row.get('id'))
        row.update(nombre=c.fantasia or c.razon_social or '' if c else '', actuales=c.entrega.dias or '' if c and c.entrega else '')
        if row['error']:
            status = 'error'
        elif c is None:
            status = 'no_encontrado'
            row['error'] = 'No está en Rutas. Actualizá desde maestro y revisá el código.'
        elif c.anulado:
            status = 'inactivo'
        elif row['actuales'] == row['dias']:
            status = 'sin_cambios'
        elif modo == 'vacios' and row['actuales']:
            status = 'conservar'
        else:
            status = 'reemplazar' if row['actuales'] else 'asignar'
            changes.append({'id': c.id_cliente, 'dias': row['dias'], 'antes': estado(c.entrega)})
        row['estado'] = status
        summary[status] += 1
    result = dict(summary, total=len(rows), cambios=len(changes))
    payload = {'id': str(uuid4()), 'archivo': archivo[:255], 'sha256': hashlib.sha256(content).hexdigest(),
               'usuario': usuario, 'actor': actor or usuario, 'modo': modo, 'changes': changes, 'resumen': result}
    return {'ok': True, 'resumen': result, 'rows': rows,
            'token': serializer().dumps(payload) if changes else None}


class VistaDesactualizada(ValueError):
    pass


def confirmar(token, usuario):
    if not isinstance(token, str) or len(token) > 2_000_000:
        raise ValueError('Vista previa inválida.')
    try:
        payload = serializer().loads(token, max_age=1800)
    except BadSignature as exc:
        raise ValueError('La vista previa venció o no es válida. Volvé a analizar el CSV.') from exc
    if payload['usuario'] != usuario:
        raise ValueError('La vista previa pertenece a otro usuario.')
    s = Session()
    try:
        if s.bind.dialect.name == 'postgresql':
            s.execute(text('SELECT pg_advisory_xact_lock(7319021)'))
        saved = s.get(ImportacionDias, payload['id'])
        if saved:
            return {'ok': True, 'ya_aplicada': True, 'resumen': json.loads(saved.resumen)}
        # Lock and re-read both client and delivery records before comparing the preview.
        ids = sorted(r['id'] for r in payload['changes'])
        clients = {c.id_cliente: c for c in s.query(Cliente).filter(Cliente.id_cliente.in_(ids))
                   .order_by(Cliente.id_cliente).with_for_update(of=Cliente).populate_existing()}
        deliveries = {e.id_cliente: e for e in s.query(ClienteEntrega).filter(ClienteEntrega.id_cliente.in_(ids))
                      .order_by(ClienteEntrega.id_cliente).with_for_update().populate_existing()}
        for change in payload['changes']:
            c, e = clients.get(change['id']), deliveries.get(change['id'])
            if c is None or c.anulado or estado(e) != change['antes']:
                raise VistaDesactualizada('Hay clientes modificados después de la vista previa. Volvé a analizar el CSV; no se guardó ningún cambio.')
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for change in payload['changes']:
            e = deliveries.get(change['id'])
            if e is None:
                e = ClienteEntrega(id_cliente=change['id'])
                s.add(e)
            s.add(CambioLog(id_cliente=change['id'], campo='dias', antes=e.dias or '',
                            despues=change['dias'], usuario=payload['actor'], fecha=now))
            e.dias = change['dias']
            e.en_planilla = True
            e.pendiente_bees = True
            e.actualizado, e.actualizado_por = now, payload['actor']
        s.add(ImportacionDias(id=payload['id'], archivo=payload['archivo'], sha256=payload['sha256'],
                             usuario=payload['actor'], fecha=now, resumen=json.dumps(payload['resumen'])))
        s.commit()
        return {'ok': True, 'ya_aplicada': False, 'resumen': payload['resumen']}
    except Exception:
        s.rollback()
        raise
