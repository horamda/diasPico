"""Validate planning edits before touching persisted objects."""
import math
import re
from .dias import DIAS, normalizar


def validar(endpoint, data):
    action = endpoint.rsplit('.', 1)[-1]
    if action == 'api_plan':
        if any(d not in DIAS for d in data):
            raise ValueError('Día de entrega inválido')
        for values in data.values():
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise ValueError('Cada día debe contener una lista de localidades')
            if len(set(values)) != len(values):
                raise ValueError('No repitas una localidad en el mismo día')
        return
    for field, limit in {'nombre': 80, 'patente': 20, 'direccion': 200, 'nota': 4000}.items():
        if field in data and data[field] is not None:
            if not isinstance(data[field], str) or len(data[field]) > limit:
                raise ValueError(f'{field}: texto inválido o demasiado largo')
            if field == 'nombre' and not data[field].strip():
                raise ValueError('Ingresá un nombre')
    if 'nombre' in data and 'vehiculo' in action and len(data['nombre'] or '') > 60:
        raise ValueError('El nombre del vehículo admite hasta 60 caracteres')
    if 'activo' in data and not isinstance(data['activo'], bool):
        raise ValueError('Estado inválido')
    for field in ('deposito_id', 'capacidad_clientes'):
        value = data.get(field)
        if value is not None and (type(value) is not int or value < (1 if field == 'deposito_id' else 0)):
            raise ValueError(f'{field}: ingresá un entero válido')
    if 'color' in data and (not isinstance(data['color'], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', data['color'])):
        raise ValueError('Color inválido')
    if 'lat' in data or 'lng' in data:
        lat, lng = data.get('lat'), data.get('lng')
        if (lat is None) != (lng is None):
            raise ValueError('Completá ambas coordenadas o borrá ambas')
        if lat is not None:
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in (lat, lng)):
                raise ValueError('Coordenadas inválidas')
            if not (-41.5 < lat < -33 and -63.5 < lng < -56):
                raise ValueError('Coordenadas fuera de la provincia de Buenos Aires')
    if 'dias' in data:
        value = data['dias']
        if not isinstance(value, str) or value != normalizar(value):
            raise ValueError('Días inválidos; usá LU, MA, MI, JU, VI, SA en orden')
