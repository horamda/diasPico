from datetime import date, datetime, timedelta, timezone

import pytest

from app.services import frescura_control_svc as svc


def session():
    instant = datetime(2026, 9, 9, 23, 50, tzinfo=timezone.utc)
    return {'id': 1, 'sucursal': '1', 'fecha': date(2026, 9, 9), 'responsable': 'Operario A',
            'iniciado_at': instant, 'activo_desde': instant, 'estado': 'activo',
            'segundos_activos': 0, 'borrador': {'rows': [
                {'codigo_articulo': '7634', 'lote': 'L1', 'stock_sistema_bultos': 1800,
                 'stock_sistema_unidades': 0, 'fecha_vencimiento_sistema': '2026-10-01'}]}}


def test_active_time_crosses_midnight():
    row = session()
    result = svc.timing(row, row['iniciado_at'] + timedelta(minutes=30))
    assert result == {'segundos_activos': 1800, 'segundos_transcurridos': 1800}


def test_pause_is_excluded_from_active_time():
    row = session()
    row.update(estado='pausado', activo_desde=None, segundos_activos=600)
    result = svc.timing(row, row['iniciado_at'] + timedelta(minutes=30))
    assert result == {'segundos_activos': 600, 'segundos_transcurridos': 1800}


def test_resume_counts_only_new_active_interval():
    row = session()
    row.update(activo_desde=row['iniciado_at']+timedelta(minutes=25), segundos_activos=600)
    result = svc.timing(row, row['iniciado_at']+timedelta(minutes=30))
    assert result == {'segundos_activos': 900, 'segundos_transcurridos': 1800}


def test_finished_time_remains_fixed():
    row = session()
    row.update(estado='finalizado', activo_desde=None, segundos_activos=900,
               finalizado_at=row['iniciado_at']+timedelta(minutes=30))
    result = svc.timing(row, row['iniciado_at']+timedelta(days=7))
    assert result == {'segundos_activos': 900, 'segundos_transcurridos': 1800}


class Cursor:
    def __init__(self, row): self.row = row
    def execute(self, *args): pass
    def fetchone(self): return self.row


def finish_item():
    return {**session()['borrador']['rows'][0], 'revision': 'OK', 'fecha_vencimiento': '2026-10-01'}


def test_finish_accepts_reviewed_control():
    row = session()
    assert svc.lock_for_finish(Cursor(row), 1, '1', row['fecha'], 'Operario A', [finish_item()]) == row


@pytest.mark.parametrize('change', ['pending', 'missing', 'wrong_worker', 'wrong_branch', 'paused', 'source_changed', 'pending_pallet'])
def test_finish_rejects_incomplete_or_misattributed_control(change):
    row, item, worker, branch = session(), finish_item(), 'Operario A', '1'
    items = [item]
    if change == 'pending': item['revision'] = 'PENDIENTE'
    if change == 'missing': items = []
    if change == 'wrong_worker': worker = 'Operario B'
    if change == 'wrong_branch': branch = '2'
    if change == 'paused': row['estado'] = 'pausado'
    if change == 'source_changed': item['stock_sistema_bultos'] = 1700
    if change == 'pending_pallet': item['distribucion_fechas'] = [{'revision': 'PENDIENTE'}]
    with pytest.raises(ValueError):
        svc.lock_for_finish(Cursor(row), 1, branch, row['fecha'], worker, items)


def test_invalid_duplicate_draft_rejected():
    item = session()['borrador']['rows'][0]
    with pytest.raises(ValueError, match='duplicados'):
        svc.draft_keys({'rows': [item, item]})
