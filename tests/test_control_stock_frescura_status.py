from datetime import date, datetime

import pytest

from app.services import control_stock_svc as svc


def sync_row(stock_date='2026-09-09', estado='ok'):
    return {'id': 1, 'estado': estado, 'finished_at': datetime(2026, 9, 10),
            'payload_json': {'fecha_stock': stock_date}}


@pytest.mark.parametrize('stock_date,estado,expected', [
    ('2026-09-09', 'ok', 'ok'),
    ('2026-09-08', 'ok', 'desactualizado'),
    ('2026-09-10', 'ok', 'desactualizado'),
    ('2026-09-09', 'error', 'desactualizado'),
    ('2026-09-09', 'running', 'desactualizado'),
])
def test_exact_successful_date_required(stock_date, estado, expected):
    status = svc._format_frescura_status(sync_row(stock_date, estado), date(2026, 9, 9))
    assert status['estado_alerta'] == expected


@pytest.mark.parametrize('force,expected_calls', [(False, 0), (True, 1)])
def test_force_refresh_even_when_current(monkeypatch, force, expected_calls):
    calls = []
    monkeypatch.setattr(svc, 'ensure_control_stock_tables', lambda: None)
    monkeypatch.setattr(svc, '_latest_frescura_sync_row', sync_row)
    monkeypatch.setattr(svc.frescura_svc, 'sync_frescura_from_api',
                        lambda **kw: calls.append(kw) or {'saved_rows': 2})
    status = svc.get_frescura_status('2026-09-09', force_sync=force)
    assert len(calls) == expected_calls
    assert status['estado_alerta'] == 'ok'
    if force:
        assert calls[0]['fecha_stock'] == date(2026, 9, 9)


def test_failed_sync_keeps_previous_success_date(monkeypatch):
    monkeypatch.setattr(svc, 'ensure_control_stock_tables', lambda: None)
    monkeypatch.setattr(svc, '_latest_frescura_sync_row', lambda: sync_row('2026-09-07'))
    def fail(**kwargs):
        raise RuntimeError('ERP no disponible')
    monkeypatch.setattr(svc.frescura_svc, 'sync_frescura_from_api', fail)
    status = svc.get_frescura_status('2026-09-09')
    assert status['fecha_stock'] == '2026-09-07'
    assert status['estado_alerta'] == 'desactualizado'
    assert status['auto_sync']['ok'] is False
    assert status['auto_sync']['error'] == 'ERP no disponible'
