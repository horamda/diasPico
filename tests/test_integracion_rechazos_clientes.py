import os
from contextlib import contextmanager
from datetime import date

import pytest
from flask import Flask

from app.routes import integracion_logistica as route
from app.services import integracion_rechazos_svc as svc


URL = '/api/v1/integracion/logistica/rechazos/clientes-diario'


def client(key='test'):
    app = Flask(__name__)
    app.config.update(TESTING=True, INTEGRATION_API_KEY=key)
    app.register_blueprint(route.bp)
    return app.test_client()


def test_auth_validation_and_contract(monkeypatch):
    captured = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return {'total': 3, 'datos': [{'fecha': '2026-09-01', 'cliente_id': '42'}]}

    monkeypatch.setattr(svc, 'get_clientes_diario', fake)
    api = client()
    headers = {'Authorization': 'Bearer test'}
    assert api.get(URL + '?fecha=2026-09-01').status_code == 401
    assert client(None).get(URL).status_code == 503
    for query in ('', '?fecha=mal', '?desde=2026-01-01&hasta=2026-02-28',
                  '?fecha=2026-09-01&offset=-1', '?fecha=2026-09-01&limit=1001',
                  '?fecha=2026-09-01&empresa_id='):
        assert api.get(URL + query, headers=headers).status_code == 400
    response = api.get(URL + '?fecha=2026-09-01&limit=1&offset=1', headers=headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body['paginacion'] == dict(limit=1, offset=1, devueltos=1, total=3, hay_mas=True)
    assert body['criterios']['otif_calculable'] is False
    assert captured['desde'] == date(2026, 9, 1)
    assert captured['empresa_id'] == '1'
    assert response.headers['X-Total-Count'] == '3'


@pytest.mark.skipif(os.environ.get('RUN_RECHAZOS_DB_TEST') != '1', reason='Requires PostgreSQL')
def test_sql_deduplicacion_filtros_y_paginacion(monkeypatch):
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from app.config import AppSettings
    from app.services.ventas_svc import VENTAS_DETALLE_DDL

    settings = AppSettings()
    conn = psycopg2.connect(settings.RAILWAY_URL or settings.DATABASE_URL, connect_timeout=8)
    try:
        # Temporary tables shadow production names only in this connection.
        with conn.cursor() as cur:
            cur.execute(VENTAS_DETALLE_DDL.replace('CREATE TABLE IF NOT EXISTS', 'CREATE TEMP TABLE'))
            cur.execute(svc.rec.DDL.replace('CREATE TABLE IF NOT EXISTS', 'CREATE TEMP TABLE'))
            cur.execute('CREATE TEMP TABLE articulos (id_articulo INTEGER, tipo_producto TEXT)')
            cur.execute("INSERT INTO articulos VALUES (1, 'mercaderia'), (2, 'envase')")
            cur.execute("INSERT INTO rechazos (motivo_key, motivo_rechazo, tomar) VALUES ('roto', 'Roto', true), ('cerrado', 'Cerrado', false)")
            rows = [
                ('1', '1', '42', 'FCVTA', '1', 1, 10, 2, 'Roto'),
                ('1', '1', '42', 'FCVTA', '1', 1, 5, 1, 'Cerrado'),
                ('1', '2', '42', 'FCVTA', '2', 1, 3, 1, 'Nuevo'),
                ('1', '1', '43', 'FCVTA', '3', 1, 7, 0, None),
                ('1', '1', None, 'FCVTA', '4', 1, 1, 1, None),
                ('2', '1', '42', 'FCVTA', '5', 1, 100, 100, 'Roto'),
                ('1', '1', '42', 'REMIT', '6', 1, 100, 100, 'Roto'),
                ('1', '1', '42', 'FCVTA', '7', 2, 100, 100, 'Roto'),
            ]
            cur.executemany("""INSERT INTO ventas_detalle
                (empresa, sucursal, cliente, documento, numero, id_articulo,
                 bultos, bultos_rechazados, motivo_rechazo, fecha, letra, serie)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'2026-09-01','A','1')""", rows)

        @contextmanager
        def cursor():
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur

        monkeypatch.setattr(svc, 'pg_cursor', cursor)
        for name in ('ensure_table', 'ensure_ventas_detalle_table', 'ensure_articulos_table'):
            monkeypatch.setattr(svc.rec, name, lambda: None)
        args = dict(empresa_id='1', sucursal='TODAS', desde=date(2026, 9, 1),
                    hasta=date(2026, 9, 1), limit=100, offset=0)
        result = svc.get_clientes_diario(**args)
        assert result['total'] == 3
        by_client = {r['cliente_id']: r for r in result['datos']}
        row = by_client['42']
        assert row['bultos_registrados'] == 18
        assert row['bultos_rechazados'] == 4
        assert row['bultos_rechazados_computables'] == 2
        assert len(row['documentos']) == 2
        assert len(row['motivos']) == 3
        assert row['tiene_rechazo_computable'] is True
        assert row['calidad']['lineas_rechazo_sin_clasificar'] == 1
        assert row['calidad']['multiples_sucursales'] is True
        assert by_client['43']['tiene_rechazo'] is False
        assert by_client['']['calidad']['cliente_identificado'] is False
        page = svc.get_clientes_diario(**{**args, 'offset': 99})
        assert page == {'total': 3, 'datos': []}
        filtered = svc.get_clientes_diario(**{**args, 'sucursal': '1'})
        assert next(r for r in filtered['datos'] if r['cliente_id'] == '42')['bultos_rechazados'] == 3
        empty = svc.get_clientes_diario(**{**args, 'empresa_id': '99'})
        assert empty == {'total': 0, 'datos': []}
    finally:
        conn.rollback()
        conn.close()
