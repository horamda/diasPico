import os
from contextlib import contextmanager
from datetime import date

import pytest
from flask import Flask

from app.routes import integracion_logistica as route
from app.services import integracion_pedidos_svc as svc


URL = '/api/v1/integracion/logistica/pedidos'


@pytest.mark.parametrize('estados,expected', [
    (['ENTREGADO'], 'completa'), (['RECHAZADO'], 'rechazada'),
    (['ENTREGADO', 'RECHAZADO'], 'parcial'), (['PARCIAL'], 'parcial'),
    (['ENTREGADO', 'EN TRÁNSITO'], 'en_transito'),
    (['ENTREGADO', None], 'sin_determinar'), ([], 'sin_determinar'),
    (['PENDIENTE'], 'sin_determinar'), ([' entregado '], 'completa'),
])
def test_estado(estados, expected):
    assert svc._estado(estados) == expected


def test_route(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, INTEGRATION_API_KEY='test')
    app.register_blueprint(route.bp)
    client = app.test_client()
    captured = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return dict(total=2, datos=[{'numero_pedido': '5'}], ultima_fecha_disponible='2026-05-19')

    monkeypatch.setattr(svc, 'get_pedidos', fake)
    headers = {'X-API-Key': 'test'}
    assert client.get(URL).status_code == 401
    for query in ('', '?fecha=mal', '?fecha=2026-05-01&limit=0',
                  '?fecha=2026-05-01&offset=-1', '?fecha=2026-05-01&empresa_id=2',
                  '?desde=2026-01-01&hasta=2026-02-10'):
        assert client.get(URL + query, headers=headers).status_code == 400
    response = client.get(URL + '?fecha=2026-05-01&sucursal=2&limit=1', headers=headers)
    assert response.status_code == 200
    assert response.get_json()['paginacion']['hay_mas'] is True
    assert response.get_json()['cobertura']['ultima_fecha_disponible'] == '2026-05-19'
    assert captured['sucursal'] == '2'
    assert captured['desde'] == date(2026, 5, 1)


@pytest.mark.skipif(os.environ.get('RUN_RECHAZOS_DB_TEST') != '1', reason='Requires PostgreSQL')
def test_postgres_pedidos_sin_duplicar_y_sin_mezclar_intentos(monkeypatch):
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from app.config import AppSettings

    settings = AppSettings()
    conn = psycopg2.connect(settings.RAILWAY_URL or settings.DATABASE_URL, connect_timeout=8)
    try:
        with conn.cursor() as cur:
            cur.execute('''CREATE TEMP TABLE repartos_detalle (
                id SERIAL, sucursal TEXT, comprobante TEXT, id_cliente INTEGER,
                nombre_cliente TEXT, nro_pedido INTEGER, estado TEXT,
                fecha_entrega_planilla DATE, nro_planilla INTEGER,
                ruta_venta TEXT, ruta_distribucion TEXT, id_articulo INTEGER,
                bultos NUMERIC, cantidad_um NUMERIC, unidad_medida TEXT,
                cantidad_up NUMERIC, motivo_rechazo TEXT, hora_entrega TIME)''')
            rows = [
                ('1', 'FACTURA-A-1-1', 42, 5, 'ENTREGADO', '2026-05-01', 100),
                ('1', 'FACTURA-A-1-1', 42, 5, 'RECHAZADO', '2026-05-01', 100),
                ('1', 'FACTURA-A-1-2', 42, 6, 'ENTREGADO', '2026-05-01', 101),
                ('1', 'FACTURA-A-1-1', 42, 5, 'ENTREGADO', '2026-05-02', 102),
                ('2', 'FACTURA-A-1-1', 42, 5, 'RECHAZADO', '2026-05-01', 103),
                ('1', 'FACTURA-A-1-3', 42, None, 'EN TRANSITO', '2026-05-01', 104),
                ('1', None, None, None, None, '2026-05-01', None),
                ('1', None, None, None, None, '2026-05-01', None),
            ]
            cur.executemany('''INSERT INTO repartos_detalle
                (sucursal, comprobante, id_cliente, nro_pedido, estado,
                 fecha_entrega_planilla, nro_planilla, ruta_distribucion)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'R1')''', rows)

        @contextmanager
        def cursor():
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur

        monkeypatch.setattr(svc, 'pg_cursor', cursor)
        args = dict(desde=date(2026, 5, 1), hasta=date(2026, 5, 2),
                    sucursal='TODAS', limit=100, offset=0)
        result = svc.get_pedidos(**args)
        assert result['total'] == 7
        assert result['ultima_fecha_disponible'] == '2026-05-02'
        assert len({r['id_integracion'] for r in result['datos']}) == 7
        partial = next(r for r in result['datos'] if r['estado_entrega'] == 'parcial')
        assert partial['lineas_origen'] == 2
        assert partial['numero_pedido'] == '5'
        assert partial['vinculo_foxtrot']['planillas'] == ['100']
        assert partial['vinculo_foxtrot']['rutas_distribucion'] == ['R1']
        assert len(partial['comprobantes']) == 1
        assert len(partial['detalle']) == 2
        unknown = [r for r in result['datos'] if r['tipo_identificador'] == 'fila']
        assert len(unknown) == 2
        assert all(not r['calidad']['pedido_o_comprobante_identificado'] for r in unknown)
        filtered = svc.get_pedidos(**{**args, 'sucursal': '2'})
        assert filtered['total'] == 1
        assert filtered['datos'][0]['estado_entrega'] == 'rechazada'
        page = svc.get_pedidos(**{**args, 'offset': 99})
        assert page['datos'] == [] and page['total'] == 7
        empty = svc.get_pedidos(**{**args, 'desde': date(2026, 9, 1), 'hasta': date(2026, 9, 2)})
        assert empty['total'] == 0
        assert empty['ultima_fecha_disponible'] == '2026-05-02'
    finally:
        conn.rollback()
        conn.close()
