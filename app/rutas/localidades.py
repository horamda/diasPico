"""Relación operativa de localidades y sucursales indicada por logística."""
import unicodedata


def normalizar_nombre(value):
    value = ' '.join(str(value or '').upper().split())
    return ''.join(c for c in unicodedata.normalize('NFD', value)
                   if not unicodedata.combining(c))


SUCURSAL_POR_LOCALIDAD = {
    'GENERAL LAVALLE': 'CASA CENTRAL',
    'CASTELLI': 'CHASCOMUS', 'CHASCOMUS': 'CHASCOMUS',
    'GENERAL BELGRANO': 'CHASCOMUS', 'LEZAMA': 'CHASCOMUS',
    'PILA': 'CHASCOMUS', 'RANCHOS': 'CHASCOMUS',
    'SEVIGNE': 'CHASCOMUS', 'VILLANUEVA': 'CHASCOMUS',
    'DOLORES': 'DOLORES', 'ESQUINA DE CROTTO': 'DOLORES',
    'GENERAL CONESA': 'DOLORES', 'GENERAL GUIDO': 'DOLORES',
    'LAS ARMAS': 'DOLORES', 'MAIPU': 'DOLORES', 'SANTO DOMINGO': 'DOLORES',
}


def sucursal_entrega(localidad, fallback=None):
    return SUCURSAL_POR_LOCALIDAD.get(normalizar_nombre(localidad),
                                      normalizar_nombre(fallback) or 'SIN ASIGNAR')
