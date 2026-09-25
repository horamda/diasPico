import os
from contextlib import contextmanager
from datetime import date

import pytest
from flask import Flask

from app.routes import integracion_logistica as route
from app.services import integracion_pedidos_svc as svc


URL = '/api/v1/integracion/logistica/pedidos'


def linea(rechazo=0, total='NO', **kwargs):
    return dict(bultos=10, hl=1, up=1, bultos_rechazados=rechazo,
                hl_rechazados=0, up_rechazadas=0, rechazo_total=total, **kwargs)


@pytest.mark.parametrize('lineas,expected', [
    ([linea()], 'sin_rechazo_registrado'),
    ([linea(2)], 'parcial'),
    ([linea(2, 'Sí'), linea(4, 'SI')], 'total'),
    ([linea(2, 'SI'), linea()], 'parcial'),
    ([linea(2, '')], 'sin_determinar'),
    ([linea(0, 'SI')], 'sin_determinar'),
    ([linea(None)], 'sin_determinar'),
    ([linea(-2)], 'sin_determinar'),
    ([], 'sin_determinar'),
])
def test_clasificacion_no_infiere_entrega_completa(lineas, expected):
    assert svc._clasificar(lineas)[0] == expected


def test_route(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, INTEGRATION_API_KEY='test')
    app.register_blueprint(route.bp)
    client = app.test_client()
    captured = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return dict(total=2, datos=[{'numero_comprobante': '5'}], ultima_fecha_disponible='2026-09-17')

    monkeypatch.setattr(svc, 'get_pedidos', fake)
    headers = {'X-API-Key': 'test'}
    assert client.get(URL).status_code == 401
    for query in ('', '?fecha=mal', '?fecha=2026-09-17&limit=0',
                  '?fecha=2026-09-17&offset=-1', '?fecha=2026-09-17&empresa_id=',
                  '?desde=2026-01-01&hasta=2026-02-10'):
        assert client.get(URL + query, headers=headers).status_code == 400
    response = client.get(URL + '?fecha=2026-09-17&empresa_id=2&sucursal=2&limit=1', headers=headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body['paginacion']['hay_mas'] is True
    assert body['cobertura']['ultima_fecha_disponible'] == '2026-09-17'
    assert body['criterios']['fuente'] == 'ventas_detalle'
    assert captured['empresa_id'] == '2'
    assert captured['sucursal'] == '2'
    assert captured['desde'] == date(2026, 9, 17)
    assert body['contrato'] == 'comprobantes_ventas_v2'


@pytest.mark.skipif(os.environ.get('RUN_RECHAZOS_DB_TEST') != '1', reason='Requires PostgreSQL')
def test_postgres_comprobantes_actualizados_y_aislamiento(monkeypatch):
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from app.config import AppSettings
    from app.services.ventas_svc import VENTAS_DETALLE_DDL

    settings = AppSettings()
    conn = psycopg2.connect(settings.RAILWAY_URL or settings.DATABASE_URL, connect_timeout=8)
    try:
        with conn.cursor() as cur:
            cur.execute(VENTAS_DETALLE_DDL.replace('CREATE TABLE IF NOT EXISTS', 'CREATE TEMP TABLE'))
            cur.execute(svc.rec.DDL.replace('CREATE TABLE IF NOT EXISTS', 'CREATE TEMP TABLE'))
            cur.execute('CREATE TEMP TABLE articulos (id_articulo INTEGER PRIMARY KEY, tipo_producto TEXT)')
            cur.execute("INSERT INTO articulos VALUES (1, 'mercaderia'), (2, 'envase')")
            cur.execute("INSERT INTO rechazos (motivo_key,motivo_rechazo,tomar) VALUES ('roto','Roto',false)")
            rows = [
                ('1','1','0042','FCVTA','A','1','5',None,2,'NO','2026-09-17',1),
                ('1','1','0042','FCVTA','A','1','5',None,0,'NO','2026-09-17',1),
                ('1','1','0042','FCVTA','A','1','6',None,0,'NO','2026-09-17',1),
                ('1','1','0042','FCVTA','B','1','5',None,2,'SI','2026-09-17',1),
                ('1','2','0042','FCVTA','A','1','5',None,2,'SI','2026-09-17',1),
                ('2','1','0042','FCVTA','A','1','5',None,2,'SI','2026-09-17',1),
                ('1','1','0042','FCVTA','A','2','5',None,0,'NO','2026-09-17',1),
                ('1','1','0042',None,None,None,None,'DOC-FALLBACK',0,'NO','2026-09-17',1),
                ('1','1',None,None,None,None,None,None,0,'NO','2026-09-17',1),
                ('1','1',None,None,None,None,None,None,0,'NO','2026-09-17',1),
                # Later remitos and non-merchandise must not affect coverage.
                ('1','1','0042','REMIT','A','1','8',None,0,'NO','2026-09-18',1),
                ('1','1','0042','FCVTA','A','1','9',None,0,'NO','2026-09-18',2),
            ]
            cur.executemany('''INSERT INTO ventas_detalle
                (empresa,sucursal,cliente,documento,letra,serie,numero,detalle_documento,
                 bultos_rechazados,rechazo_total,fecha,id_articulo,bultos,
                 unidad_medida_rechazado,unidad_paquete_rechazado,motivo_rechazo,ruta)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,10,0,0,'Roto','R1')''', rows)

        @contextmanager
        def cursor():
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur

        monkeypatch.setattr(svc, 'pg_cursor', cursor)
        for name in ('ensure_table', 'ensure_ventas_detalle_table', 'ensure_articulos_table'):
            monkeypatch.setattr(svc.rec, name, lambda: None)
        args = dict(desde=date(2026,9,17), hasta=date(2026,9,18),
                    sucursal='TODAS', empresa_id='1', limit=100, offset=0)
        result = svc.get_pedidos(**args)
        assert result['total'] == 8
        assert result['ultima_fecha_disponible'] == '2026-09-17'
        assert len({r['id_integracion'] for r in result['datos']}) == 8
        partial = next(r for r in result['datos'] if r['estado_rechazo'] == 'parcial')
        assert partial['lineas_origen'] == 2
        assert partial['cliente_id'] == '0042'
        assert partial['numero_comprobante'] == '5'
        assert partial['numero_pedido'] is None
        assert partial['fecha_entrega'] is None
        assert partial['fecha_movimiento'] == '2026-09-17'
        for field in ('fecha_comprobante', 'fecha_entrega_planificada', 'fecha_entrega_real'):
            assert field in partial
            assert partial[field] is None
            assert partial['fuentes_fechas'][field] is None
        assert partial['fuentes_fechas']['fecha_movimiento'] == 'ventas_detalle.fecha'
        assert partial['vinculo_foxtrot']['rutas_venta'] == ['R1']
        assert partial['estado_entrega_inferido'] is True
        assert partial['tiene_rechazo_computable'] is False  # physical rejection still present
        assert partial['tiene_rechazo_registrado'] is True
        assert partial['cantidades']['bultos'] == 20
        assert partial['cantidades']['bultos_rechazados'] == 2
        assert partial['cantidades']['hl'] is None
        assert any(r['estado_rechazo'] == 'sin_rechazo_registrado' for r in result['datos'])
        assert all(r['estado_entrega'] != 'completa' for r in result['datos'])
        assert sum(r['tipo_identificador'] == 'fila' for r in result['datos']) == 2
        filtered = svc.get_pedidos(**{**args, 'sucursal': '2'})
        assert filtered['total'] == 1
        assert filtered['datos'][0]['estado_entrega'] == 'rechazada'
        other = svc.get_pedidos(**{**args, 'empresa_id': '2'})
        assert other['total'] == 1
        assert other['datos'][0]['id_integracion'] not in {r['id_integracion'] for r in result['datos']}
        page = svc.get_pedidos(**{**args, 'offset': 99})
        assert page['datos'] == [] and page['total'] == 8
        pages = [svc.get_pedidos(**{**args, 'limit': 3, 'offset': n}) for n in (0, 3, 6)]
        assert [r['id_integracion'] for p in pages for r in p['datos']] == [r['id_integracion'] for r in result['datos']]
        empty = svc.get_pedidos(**{**args, 'desde':date(2026,9,18)})
        assert empty['total'] == 0
        assert empty['ultima_fecha_disponible'] == '2026-09-17'
    finally:
        conn.rollback()
        conn.close()
