"""Cliente de la API de ChessERP para comprobantes de venta.

El login es el mismo que usa frescura (app/services/frescura_svc.py): POST auth/login
con usuario y contraseña devuelve un sessionId, que viaja como Cookie en cada consulta.
La ruta de ventas y el formato de fecha son configurables porque todavía no se
validaron contra la API real (CHESS_VENTAS_PATH, CHESS_FECHA_FMT).
"""
import os
from urllib.parse import urljoin

import requests

from app.services.frescura_svc import _extract_api_errors, _extract_nested_value

DEFAULT_BASE = 'https://delpalacio.chesserp.com/AR459/web/api/chess/v1'


class ChessError(RuntimeError):
    pass


def _cfg(name, default=None):
    try:
        from flask import current_app
        value = current_app.config.get(name)
    except RuntimeError:  # fuera de contexto de aplicación (scripts)
        value = None
    return value if value not in (None, '') else os.environ.get(name, default)


class ChessClient:
    def __init__(self, base_url=None, user=None, password=None, timeout=None, session=None):
        self.base = (base_url or _cfg('CHESS_BASE_URL') or _cfg('FRESCURA_API_BASE_URL') or DEFAULT_BASE).rstrip('/') + '/'
        self.user = user or _cfg('CHESS_USER') or _cfg('FRESCURA_API_USER') or ''
        self.password = password or _cfg('CHESS_PASSWORD') or _cfg('FRESCURA_API_PASSWORD') or ''
        self.timeout = int(timeout or _cfg('CHESS_TIMEOUT') or 180)
        self.ventas_path = str(_cfg('CHESS_VENTAS_PATH') or 'ventas/').lstrip('/')
        self.fecha_fmt = _cfg('CHESS_FECHA_FMT') or '%d-%m-%Y'
        self.s = session or requests.Session()
        self.s.headers.update({'Accept': 'application/json'})
        self.session_id = None

    def login(self):
        if not self.user or not self.password:
            raise ChessError('Configurá CHESS_USER y CHESS_PASSWORD (o FRESCURA_API_USER y FRESCURA_API_PASSWORD).')
        try:
            r = self.s.post(urljoin(self.base, 'auth/login'), json={'usuario': self.user, 'password': self.password},
                            timeout=self.timeout)
        except requests.RequestException as exc:
            raise ChessError(f'No se pudo conectar con ChessERP: {exc}') from exc
        if r.status_code >= 400:
            raise ChessError(f'ChessERP rechazó el login ({r.status_code}).')
        try:
            payload = r.json()
        except ValueError as exc:
            raise ChessError('ChessERP no devolvió JSON válido al autenticar.') from exc
        sid = _extract_nested_value(payload, ('sessionId', 'session_id', 'token', 'session'))
        if not sid:
            raise ChessError('ChessERP no devolvió sessionId.')
        self.session_id = sid
        self.s.headers['Cookie'] = sid
        return True

    def _get(self, path, params):
        if not self.session_id:
            self.login()
        url = urljoin(self.base, path)
        try:
            r = self.s.get(url, params=params, timeout=self.timeout)
            if r.status_code == 401:  # sesión vencida
                self.login()
                r = self.s.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise ChessError(f'No se pudo consultar ChessERP: {exc}') from exc
        if r.status_code >= 400:
            raise ChessError(f'ChessERP respondió {r.status_code}: {r.text[:300]}')
        try:
            payload = r.json()
        except ValueError as exc:
            raise ChessError('ChessERP no devolvió JSON válido.') from exc
        errors = _extract_api_errors(payload)
        if errors:
            raise ChessError('; '.join(errors))
        return payload

    def ventas_lote(self, desde, hasta, lote=1, detalle=False):
        """Un lote (hasta 1000 comprobantes) de un rango que no supere el mes calendario."""
        return self._get(self.ventas_path, {
            'fechaDesde': desde.strftime(self.fecha_fmt),
            'fechaHasta': hasta.strftime(self.fecha_fmt),
            'detallado': 'true' if detalle else 'false',
            'nroLote': lote,
        })
