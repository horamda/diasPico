from contextlib import contextmanager

from app.services import segmentacion_svc as svc


THRESHOLDS = {
    'clientes_evaluados': 4, 'p50_ratio': 12, 'p75_ratio': 20,
    'p25_dropsize': 10, 'p75_pedidos': 50,
    'p75_rechazo': 5, 'p75_rechazo_hl': 2, 'p25_venta': 100,
}


def customer(code='1', **changes):
    row = dict(cliente=code, descripcion_cliente=code, sucursal='1',
               venta_ytd=1000, costo_logistico_total=100, costo_por_pedido=10,
               costo_entrega=60, costo_almacen=40, pedidos_ytd=10,
               ratio_costo_logistico_pct=10, dropsize_bultos_ytd=20,
               pct_rechazo_pedidos=0, pct_rechazo_hl=0)
    return {**row, **changes}


def test_large_customer_and_large_daily_order_do_not_add_review_signals():
    small = svc._cost_attention_assessment(customer(), THRESHOLDS)
    large = svc._cost_attention_assessment(customer(
        venta_ytd=1000000, costo_logistico_total=100000,
        costo_por_pedido=10000, dropsize_bultos_ytd=20000,
        autoelevador=False,
    ), THRESHOLDS)
    assert small == large
    assert large['indice_costo_servicio'] == 0


def test_three_signals_are_independent_and_rejection_is_not_double_counted():
    result = svc._cost_attention_assessment(customer(
        ratio_costo_logistico_pct=120, pct_rechazo_pedidos=20,
        pct_rechazo_hl=10, pedidos_ytd=50, dropsize_bultos_ytd=10,
    ), THRESHOLDS)
    assert result['indice_costo_servicio'] == 3
    assert len(result['motivos']) == 3
    assert result['motivo_principal'] == 'Costo estimado superior a la venta'


def test_missing_thresholds_and_missing_drop_do_not_fabricate_signals():
    assert svc._cost_attention_assessment(customer(), {})['indice_costo_servicio'] == 0
    result = svc._cost_attention_assessment(customer(pedidos_ytd=100, dropsize_bultos_ytd=None), THRESHOLDS)
    assert result['indice_costo_servicio'] == 0
    assert svc._cost_report_leaders([]) == {}


def test_rejection_threshold_respects_population_and_absolute_floor():
    result = svc._cost_attention_assessment(customer(pct_rechazo_pedidos=9, pct_rechazo_hl=2.9), THRESHOLDS)
    assert result['indice_costo_servicio'] == 0
    higher = {**THRESHOLDS, 'p75_rechazo': 30, 'p75_rechazo_hl': 8}
    assert svc._cost_attention_assessment(customer(pct_rechazo_pedidos=20, pct_rechazo_hl=5), higher)['indice_costo_servicio'] == 0


def report_from_rows(monkeypatch, rows, **kwargs):
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, params=None): self.sql = sql
        def fetchone(self):
            return THRESHOLDS if 'clientes_evaluados' in self.sql else {'clientes': 0}
        def fetchall(self):
            return rows if 'SELECT * FROM evaluado' in self.sql else []

    class Connection:
        def cursor(self, **_): return Cursor()

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr(svc, 'pg_conn', connection)
    monkeypatch.setattr(svc, 'ensure_tables', lambda: None)
    monkeypatch.setattr(svc, '_dpo_cache_has_rows', lambda: True)
    kwargs.setdefault('incluir_outliers', True)
    return svc.get_reporte_costos_atencion(**kwargs)


def test_leaders_use_full_population_before_ranking_limit(monkeypatch):
    rows = [customer('large', costo_logistico_total=10000),
            customer('daily', costo_por_pedido=500),
            customer('review', ratio_costo_logistico_pct=30, pct_rechazo_hl=4)]
    report = report_from_rows(monkeypatch, rows, limit=1)
    assert [r['cliente'] for r in report['items']] == ['review']
    assert report['destacados']['gasto_total']['cliente'] == 'large'
    assert report['destacados']['costo_dia']['cliente'] == 'daily'
    assert report['destacados']['costo_venta']['cliente'] == 'review'
    assert report['resumen']['clientes_elegibles'] == 3
    assert report['metodologia']['version'] == 'volumen_senales_v2'


def test_daily_average_is_weighted_and_ignores_unavailable_denominators(monkeypatch):
    report = report_from_rows(monkeypatch, [
        customer('a', costo_logistico_total=100, pedidos_ytd=1, costo_por_pedido=100),
        customer('b', costo_logistico_total=900, pedidos_ytd=90, costo_por_pedido=10),
        customer('c', costo_logistico_total=500, pedidos_ytd=0, costo_por_pedido=None),
    ])
    assert report['resumen']['costo_por_pdv_promedio_reportado'] == round(1000 / 91, 2)
    assert report['destacados']['costo_dia']['cliente'] == 'a'


def test_no_days_returns_unavailable_average(monkeypatch):
    report = report_from_rows(monkeypatch, [customer(pedidos_ytd=0, costo_por_pedido=None)])
    assert report['resumen']['costo_por_pdv_promedio_reportado'] is None
    assert 'costo_dia' not in report['destacados']


def test_low_sale_leader_is_preserved_outside_review_ranking(monkeypatch):
    report = report_from_rows(monkeypatch, [
        customer('small', venta_ytd=50, ratio_costo_logistico_pct=60),
        customer('regular'),
    ], incluir_outliers=False, min_venta=100)
    assert [r['cliente'] for r in report['items']] == ['regular']
    assert report['destacados']['costo_venta']['cliente'] == 'small'
    assert report['umbrales']['min_venta_efectiva'] == 100


def test_custom_minimum_and_include_outliers_are_respected(monkeypatch):
    rows = [customer('small', venta_ytd=50), customer('regular')]
    report = report_from_rows(monkeypatch, rows, incluir_outliers=False, min_venta=2000)
    assert report['items'] == []
    assert report['destacados']
    report = report_from_rows(monkeypatch, rows, incluir_outliers=True, min_venta=2000)
    assert len(report['items']) == 2
