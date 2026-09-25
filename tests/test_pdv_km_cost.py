from unittest.mock import Mock

import pytest
from flask import Flask
from app.services import pdv_km_cost_svc as svc
from app.routes.segmentacion import bp


def client(code='1', branch='1', **kwargs):
    return dict(cliente=code, sucursal=branch, descripcion_cliente='Almacén',
                cluster_dpo='Ganador', venta_ytd=100000, bultos_ytd=10, **kwargs)


def visit(code='1', branch='1', rid='r1', km=8):
    return dict(cliente=code, sucursal=branch, rid=rid, km_asignados=km,
                km_tramo=6, km_regreso=2, fecha='2026-09-01')


def test_all_inclusive_2500_rate_no_extra_costs():
    row, = svc.aggregate([client()], [visit()], 2500, 'https://reparto.example')
    assert row['costo'] == 20000
    assert row['costo_por_atencion'] == 20000
    assert row['costo_por_bulto'] == 2000
    assert row['costo_sobre_venta'] == 20
    assert row['visitas'][0]['detalle_url'].endswith('?rid=r1')


def test_same_customer_different_branch_is_not_merged():
    rows = svc.aggregate([client(), client(branch='2')], [visit(), visit(branch='2', km=2)], 2500, 'https://reparto.example')
    assert [(r['sucursal'], r['costo']) for r in rows] == [('1', 20000), ('2', 5000)]


def test_partial_and_missing_costs_never_become_zero_or_full_ratios():
    rows = svc.aggregate([client(), client('2'), client('3')], [visit(), visit(rid='r2', km=None), visit('2', km=None)], 2500, 'https://reparto.example')
    by_id = {r['cliente']: r for r in rows}
    assert by_id['1']['estado'] == 'Parcial'
    assert by_id['1']['costo'] == 20000
    assert by_id['1']['costo_sobre_venta'] is None
    assert by_id['1']['costo_por_bulto'] is None
    assert by_id['2']['estado'] == 'Sin distancias'
    assert by_id['2']['costo'] is None
    assert by_id['3']['estado'] == 'Sin visitas registradas'
    assert by_id['3']['costo'] is None


def test_failed_visit_still_costs_and_missing_master_remains_visible():
    failed = {**visit('99'), 'estado_entrega': 'failed'}
    rows = svc.aggregate([], [failed], 2500, 'https://reparto.example')
    assert rows[0]['costo'] == 20000
    assert rows[0]['sin_maestro']
    assert rows[0]['costo_sobre_venta'] is None


def test_filter_and_normalization():
    rows = svc.aggregate([client('001'), client('2', branch='2')], [visit('1')], 2500,
                         'https://reparto.example', '1', 'Ganador')
    assert len(rows) == 1 and rows[0]['costo'] == 20000


def test_reject_duplicate_visits_and_invalid_rates():
    with pytest.raises(ValueError):
        svc.aggregate([], [visit(), visit()], 2500, 'https://reparto.example')
    for rate in ('NaN', 'inf', -1, 0, '', None):
        with pytest.raises(ValueError):
            svc.rate_value(rate)


def test_auth_and_missing_configuration(monkeypatch):
    app = Flask(__name__)
    app.secret_key = 'test'
    app.register_blueprint(bp)
    browser = app.test_client()
    assert browser.get('/api/segmentacion/reporte/costos-km').status_code == 401
    with browser.session_transaction() as session:
        session['portal_user_id'] = 1
    result = browser.get('/api/segmentacion/reporte/costos-km').json['data']
    assert result['configurado'] is False
    assert result['tarifa'] == 2500
    assert browser.get('/api/segmentacion/reporte/costos-km?tarifa=NaN').status_code == 400


def test_fetch_rejects_wrong_period_and_never_follows_redirects(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = dict(ok=True, version=1, desde='2025-01-01', hasta='2025-01-31', items=[])
    fetch = Mock(return_value=response)
    monkeypatch.setattr(svc.requests, 'get', fetch)
    with pytest.raises(RuntimeError):
        svc.fetch_distances('https://reparto.example', 'test', '2026-01-01', '2026-01-31')
    assert fetch.call_args.kwargs['allow_redirects'] is False


def test_report_uses_active_period_and_rate(monkeypatch):
    app = Flask(__name__)
    app.config.update(REPARTO_COST_API_URL='https://reparto.example', REPARTO_COST_API_KEY='test')
    monkeypatch.setattr(svc.segmentation, 'get_parametros', lambda: {
        'periodo': {'fecha_desde': '2026-09-01', 'fecha_hasta': '2026-09-30'}})
    fetch = Mock(return_value={'items': [visit()], 'rutas': 1, 'rutas_sin_distancias': 0})
    monkeypatch.setattr(svc, 'fetch_distances', fetch)
    monkeypatch.setattr(svc, 'load_clients', lambda *_: [client()])
    with app.app_context():
        result = svc.report(2500)
    assert result['items'][0]['costo'] == 20000
    assert fetch.call_args.args[-2:] == ('2026-09-01', '2026-09-30')


def test_template_has_editable_rate_and_loads_calculator():
    from pathlib import Path
    from flask import render_template
    root = Path(__file__).resolve().parents[1] / 'app'
    app = Flask(__name__, template_folder=str(root / 'templates'), static_folder=str(root / 'static'))
    with app.test_request_context('/'):
        html = render_template('segmentacion_clientes.html')
    assert 'id="pdvKmRate"' in html
    assert 'value="2500" required' in html
    assert '/static/pdv-km-cost.js' in html
    assert 'window.renderPdvKmCosts?.({' in html


def test_sales_query_uses_same_dates_as_kilometers(monkeypatch):
    from contextlib import contextmanager
    cursor = Mock()
    cursor.fetchall.return_value = []
    @contextmanager
    def pg():
        yield cursor
    monkeypatch.setattr(svc, 'pg_cursor', pg)
    monkeypatch.setattr(svc.segmentation, 'ensure_tables', lambda: None)
    monkeypatch.setattr(svc.segmentation, '_dpo_cache_has_rows', lambda: True)
    assert svc.load_clients('2026-09-01', '2026-09-30', '1') == []
    sql, params = cursor.execute.call_args.args
    assert params == {'desde': '2026-09-01', 'hasta': '2026-09-30', 'empresa': '1'}
    assert 'ventas_detalle' in sql
    assert 's.venta AS venta_ytd' in sql
    assert 'LIMIT' not in sql
