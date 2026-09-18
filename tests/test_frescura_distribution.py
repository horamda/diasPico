from contextlib import contextmanager
from datetime import date

import pytest
from app.services import control_stock_svc as svc


def distribution():
    return [
        {'referencia': 'Pallets 1 al 10', 'bultos': 1000, 'unidades': 0, 'fecha_vencimiento': '2026-10-01'},
        {'referencia': 'Pallets 11 al 16', 'bultos': 600, 'unidades': 0, 'fecha_vencimiento': '2026-11-01'},
        {'referencia': 'Pallets 17 y 18', 'bultos': 200, 'unidades': 0, 'fecha_vencimiento': '2026-12-01'},
    ]


def test_each_group_has_its_own_freshness():
    groups = svc._validate_frescura_distribution({'distribucion_fechas': distribution()}, date(2026, 9, 9))
    assert sum(g['bultos'] for g in groups) == 1800
    assert [g['estado_frescura'] for g in groups] == ['CRITICO', 'ALERTA', 'OK']


@pytest.mark.parametrize('field,value', [('bultos', -1), ('bultos', 1.5), ('bultos', 'NaN'), ('bultos', 'Infinity'), ('fecha_vencimiento', ''), ('fecha_vencimiento', '2026-02-30')])
def test_invalid_group_rejected(field, value):
    group = distribution()[0]
    group[field] = value
    with pytest.raises(ValueError):
        svc._validate_frescura_distribution({'distribucion_fechas': [group]}, date(2026, 9, 9))


@pytest.mark.parametrize('missing_bultos', [0, 100])
@pytest.mark.parametrize('control_day', ['2026-09-09', '2026-09-10', '2026-09-13'])
def test_save_compares_total_once_and_preserves_all_dates(monkeypatch, missing_bultos, control_day):
    class Cursor:
        def __init__(self): self.results = [None, {'id': 99}]
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, *args): pass
        def fetchone(self): return self.results.pop(0)
    cursor = Cursor()
    class Conn:
        def cursor(self, **kwargs): return cursor
    @contextmanager
    def connection(): yield Conn()
    captured = []
    monkeypatch.setattr(svc, 'ensure_control_stock_tables', lambda: None)
    monkeypatch.setattr(svc, 'pg_conn', connection)
    monkeypatch.setattr(svc.psycopg2.extras, 'execute_values', lambda cur, sql, rows: captured.extend(rows))
    groups = distribution()
    groups[-1]['bultos'] -= missing_bultos
    result = svc.guardar_control_frescura({'sucursal': '1', 'fecha': control_day, 'responsable': 'Tester', 'items': [{
        'codigo_articulo': '7634', 'lote': 'L1', 'stock_sistema_bultos': 1800, 'stock_sistema_unidades': 0,
        'stock_contado_bultos': 9999, 'fecha_vencimiento_sistema': '2026-10-01', 'distribucion_fechas': groups,
    }]})
    assert len(captured) == 1
    stored = captured[0]
    assert stored[9] == 1800
    assert stored[11] == 1800 - missing_bultos
    assert len(stored[-1].adapted) == 3
    assert result['lotes_con_diferencia_stock'] == (1 if missing_bultos else 0)
    assert result['lotes_con_diferencia_fecha'] == 1
    findings = [r for r in result['no_ok'] if r['tipo'] == 'FECHA']
    assert len(findings) == 2
    assert sum(r['bultos'] for r in findings) == 800 - missing_bultos
    assert all(r['referencia'] != 'Pallets 1 al 10' for r in findings)
