"""Opt-in SQL integration, isolated in a schema rolled back at the end."""
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg2
from psycopg2 import sql
import psycopg2.extras
import pytest

from app.services import control_stock_svc as stock
from app.services import frescura_control_svc as sessions


@pytest.mark.skipif(os.environ.get('RUN_FRESCURA_DB_TEST') != '1', reason='Requires opt-in PostgreSQL access')
def test_session_pause_resume_finish_and_history_in_isolated_transaction(monkeypatch):
    from app.config import AppSettings
    settings = AppSettings()
    conn = psycopg2.connect(settings.RAILWAY_URL or settings.DATABASE_URL, connect_timeout=8)
    schema = 'codex_frescura_test_' + uuid4().hex
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            cur.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(schema)))
        @contextmanager
        def connection():
            yield conn  # The entire test is one transaction, never committed.
        @contextmanager
        def cursor():
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                yield cur
        for module in (stock, sessions):
            monkeypatch.setattr(module, 'pg_conn', connection)
            monkeypatch.setattr(module, 'pg_cursor', cursor)
        monkeypatch.setattr(stock, '_CONTROL_STOCK_READY', False)
        clock = [datetime(2026, 9, 9, 12, tzinfo=timezone.utc)]
        monkeypatch.setattr(sessions, 'now', lambda: clock[0])
        source = {'codigo_articulo': '7634', 'lote': 'L1', 'stock_sistema_bultos': 1800,
                  'stock_sistema_unidades': 0, 'fecha_vencimiento_sistema': '2026-10-01'}
        draft = {'rows': [source], 'observaciones': 'Prueba aislada'}
        first = sessions.start({'sucursal': '1', 'fecha': '2026-09-09', 'responsable': 'Tester', 'borrador': draft})
        clock[0] += timedelta(minutes=10)
        paused = sessions.update(first['id'], {'accion': 'pausar', 'borrador': draft})
        assert paused['segundos_activos'] == 600
        clock[0] += timedelta(minutes=15)
        recovered = sessions.start({'sucursal': '1', 'fecha': '2026-09-09', 'responsable': 'Tester', 'borrador': draft})
        assert recovered['id'] == first['id']
        assert recovered['estado'] == 'pausado'
        sessions.update(first['id'], {'accion': 'reanudar'})
        clock[0] += timedelta(minutes=5)
        groups = [
            {'referencia': 'Pallets 1 al 16', 'bultos': 1600, 'unidades': 0,
             'fecha_vencimiento': '2026-10-01', 'revision': 'OK'},
            {'referencia': 'Pallets 17 y 18', 'bultos': 200, 'unidades': 0,
             'fecha_vencimiento': '2026-11-01', 'revision': 'NO_OK'},
        ]
        saved = stock.guardar_control_frescura({'sesion_id': first['id'], 'sucursal': '1',
            'fecha': '2026-09-09', 'responsable': 'Tester', 'items': [{**source, 'distribucion_fechas': groups}]})
        assert saved['segundos_activos'] == 900
        assert saved['segundos_transcurridos'] == 1800
        assert len(saved['no_ok']) == 1
        assert saved['no_ok'][0]['bultos'] == 200
        history = sessions.history('2026-09-01', '2026-09-30', '1', 'Tester')
        assert history['resumen'][0]['segundos_activos'] == 900
        assert history['rows'][0]['lotes_no_ok'] == 1
        assert sessions.history('2026-09-01', '2026-09-30', '2')['rows'] == []
        detail = stock.get_control_frescura_diferencias('1', '2026-09-09', '2026-09-09', conteo_id=saved['id'])
        assert len(detail['rows']) == 1
        assert len(detail['rows'][0]['distribucion_fechas']) == 2
        with pytest.raises(ValueError, match='finalizada'):
            sessions.update(first['id'], {'accion': 'reanudar'})
    finally:
        conn.rollback()  # Removes all test tables/schema and data.
        conn.close()
