from contextlib import contextmanager
from datetime import date
import pytest
from app.services import control_stock_svc as svc

class Cursor:
    def __init__(self, control=None, rows=None):
        self.control = control
        self.rows = rows or []
        self.calls = []
    def execute(self, sql, args):
        self.calls.append((sql, args))
    def fetchone(self):
        return self.control
    def fetchall(self):
        return self.rows

@pytest.fixture
def db(monkeypatch):
    cursor = Cursor()
    @contextmanager
    def connection():
        yield cursor
    monkeypatch.setattr(svc, 'ensure_control_stock_tables', lambda: None)
    monkeypatch.setattr(svc, 'pg_cursor', connection)
    return cursor

def test_history_filters_external_branch_dates_and_external_name(db):
    db.rows = [{'id': 7, 'responsable': 'Auditor externo'}]
    result = svc.get_controles_externos('2026-09-01', '2026-09-30', '2', 'Auditor')
    sql, args = db.calls[0]
    assert "c.tipo_conteo = 'externo'" in sql
    assert args == ('2', date(2026,9,1), date(2026,9,30), 'Auditor', '%Auditor%')
    assert result['rows'] == db.rows

def test_detail_rejects_missing_or_other_branch_control(db):
    with pytest.raises(ValueError, match='no encontrado'):
        svc.get_controles_externos(sucursal='2', conteo_id=7)
    assert db.calls[0][1] == (7, '2')
    assert len(db.calls) == 1

def test_legacy_detail_keeps_missing_reference(db):
    db.control = {'id': 7}
    db.rows = [{'id_articulo': 1, 'stock_referencia_bultos': None, 'diferencia_bultos': None}]
    result = svc.get_controles_externos(conteo_id=7)
    assert result['items'][0]['stock_referencia_bultos'] is None

@pytest.mark.parametrize('start,end', [('invalid','2026-09-30'), ('2026-10-01','2026-09-30')])
def test_invalid_dates(db, start, end):
    with pytest.raises(ValueError):
        svc.get_controles_externos(start,end)
    assert not db.calls

def test_dispersion_uses_same_reference_without_refetch(monkeypatch):
    def unexpected(*args):
        raise AssertionError('Reference must not be queried twice')
    monkeypatch.setattr(svc, '_stock_frescura_por_articulo', unexpected)
    row = (1,'Articulo','A','externo','Externo',0,0,0,0,0,0,0,20,False,'')
    rows, alerts = svc._marcar_dispersion_frescura([row], '1', {1: 10})
    assert rows[0][13] is True
    assert len(alerts) == 1
