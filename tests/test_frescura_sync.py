from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date

from flask import Flask

from app.services import frescura_svc


class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload, default=str)

    def json(self):
        return self._payload


class _FakeCursor:
    def __init__(self):
        self.calls: list[tuple[str, dict | None]] = []
        self._fetchone_queue = [(11,)]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        if self._fetchone_queue:
            return self._fetchone_queue.pop(0)
        return None


class _FakeConn:
    def __init__(self, cursor: _FakeCursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def commit(self):
        return None

    def rollback(self):
        return None


@contextmanager
def _fake_pg_conn(cursor: _FakeCursor):
    yield _FakeConn(cursor)


def test_sync_frescura_login_and_stock_map_depositos(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        FRESCURA_API_BASE_URL='https://delpalacio.chesserp.com/AR459/web/api/chess/v1',
        FRESCURA_API_USER='APIPUBLICA',
        FRESCURA_API_PASSWORD='secret',
        FRESCURA_API_DEPOSITOS='1,4',
        FRESCURA_API_DEPOSIT_MAP='1:1,4:2',
        FRESCURA_API_TIMEOUT=5,
    )

    cursor = _FakeCursor()
    captured = {'login': None, 'stock_calls': [], 'bulk_rows': None}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured['login'] = {'url': url, 'json': json, 'headers': headers, 'timeout': timeout}
        return _FakeResponse(200, {'sessionId': 'SESSION-123'})

    def fake_get(url, headers=None, params=None, timeout=None):
        captured['stock_calls'].append({'url': url, 'headers': headers, 'params': params, 'timeout': timeout})
        deposito = str((params or {}).get('idDeposito'))
        payload = {
            'dsStockFisicoApi': {
                'dsStock': [
                    {
                        'idDeposito': deposito,
                        'idAlmacen': f'ALM-{deposito}',
                        'idArticulo': f'SKU-{deposito}',
                        'dsArticulo': f'Articulo {deposito}',
                        'fecVtoLote': '01-01-2030',
                        'cantBultos': '2,5' if deposito == '1' else 3,
                        'cantUnidades': '9' if deposito == '4' else '12',
                    },
                    {
                        'idDeposito': deposito,
                        'idAlmacen': f'ALM-{deposito}',
                        'idArticulo': '935',
                        'dsArticulo': 'Articulo excluido',
                        'fecVtoLote': '01-01-2030',
                        'cantBultos': '99',
                        'cantUnidades': '99',
                    },
                ]
            }
        }
        return _FakeResponse(200, payload)

    def fake_execute_values(cur, sql, rows):
        captured['bulk_rows'] = list(rows)

    with app.app_context():
        monkeypatch.setattr(frescura_svc, '_ensure_tables', lambda: None)
        monkeypatch.setattr(frescura_svc, 'pg_conn', lambda: _fake_pg_conn(cursor))
        monkeypatch.setattr(frescura_svc, 'get_last_sync', lambda: {'estado': 'ok'})
        monkeypatch.setattr(frescura_svc.requests, 'post', fake_post)
        monkeypatch.setattr(frescura_svc.requests, 'get', fake_get)
        monkeypatch.setattr(frescura_svc.psycopg2.extras, 'execute_values', fake_execute_values)

        result = frescura_svc.sync_frescura_from_api()

    assert result['ok'] is True
    assert result['mode'] == 'erp'
    assert result['total_items'] == 4
    assert result['saved_rows'] == 2
    assert result['source_url'].endswith('/stock/')
    assert captured['login']['url'].endswith('/auth/login')
    assert captured['login']['json'] == {'usuario': 'APIPUBLICA', 'password': 'secret'}
    assert [call['params']['idDeposito'] for call in captured['stock_calls']] == ['1', '4']
    assert captured['stock_calls'][0]['headers']['Cookie'] == 'SESSION-123'

    assert captured['bulk_rows'] is not None
    assert all(row[1] != '935' for row in captured['bulk_rows'])
    assert captured['bulk_rows'][0][0] == '1'
    assert captured['bulk_rows'][1][0] == '2'
    assert captured['bulk_rows'][0][2] == 'Articulo 1'
    assert captured['bulk_rows'][1][2] == 'Articulo 4'
    assert captured['bulk_rows'][0][7] == 12.0
    assert captured['bulk_rows'][1][7] == 9.0
    assert captured['bulk_rows'][0][9].isoformat() == '2030-01-01'
    assert captured['bulk_rows'][1][9].isoformat() == '2030-01-01'

    delete_calls = [sql for sql, _ in cursor.calls if sql.lstrip().upper().startswith('DELETE FROM FRESCURA_ARTICULOS')]
    assert delete_calls
