from datetime import date, timedelta

import pytest
from sqlalchemy import text

from tests.test_rutas_entrega import app, source
from app.rutas import ventas_app
from app.rutas.db import Session, create_all
from app.rutas.maestro import actualizar_desde_maestro

HASTA = date(2026, 9, 30)
COLS = ('cliente, fecha, documento, detalle_documento, origen, id_articulo, descripcion_articulo, bultos, '
        'unidad_medida, importe_neto, bultos_rechazados, motivo_rechazo')


def linea(cliente, dias_atras, doc, art=1, bultos=10, hl=1.0, neto=1000, rech=0, motivo=None, tipo='FCVTA', origen='BEES'):
    return dict(cliente=str(cliente), fecha=(HASTA - timedelta(days=dias_atras)).isoformat(), documento=tipo,
                detalle_documento=f'{tipo}-A-0001-{doc:08d}', origen=origen, id_articulo=art,
                descripcion_articulo={1: 'QUILMES 1L', 2: 'BRAHMA LATA', 9: 'ENVASE 1L'}[art], bultos=bultos,
                unidad_medida=hl, importe_neto=neto, bultos_rechazados=rech, motivo_rechazo=motivo)


def cargar(lineas):
    s = Session()
    s.execute(text('CREATE TABLE IF NOT EXISTS articulos (id_articulo INTEGER PRIMARY KEY, tipo_producto VARCHAR(30))'))
    s.execute(text('CREATE TABLE IF NOT EXISTS ventas_detalle (id INTEGER PRIMARY KEY, sucursal VARCHAR(5), empresa VARCHAR(5), '
                   'letra VARCHAR(5), serie VARCHAR(10), numero VARCHAR(20), cliente VARCHAR(20), fecha DATE, documento VARCHAR(20), '
                   'detalle_documento VARCHAR(60), origen VARCHAR(30), id_articulo INTEGER, descripcion_articulo VARCHAR(100), '
                   'bultos NUMERIC, unidad_medida NUMERIC, importe_neto NUMERIC, bultos_rechazados NUMERIC, motivo_rechazo VARCHAR(80))'))
    s.execute(text("INSERT OR IGNORE INTO articulos VALUES (1, 'mercaderia'), (2, 'Mercaderia '), (9, 'envase')"))
    s.execute(text(f'INSERT INTO ventas_detalle ({COLS}) VALUES ({", ".join(":" + c.strip() for c in COLS.split(","))})'), lineas)
    s.commit()


@pytest.fixture
def ctx(app):
    ventas_app._cache.clear()
    with app.app_context():
        create_all()
        yield app
    ventas_app._cache.clear()


def test_reglas_de_volumen_y_pedidos(ctx):
    cargar([
        linea(123, 0, 1, art=1, bultos=10, hl=1, neto=1000),
        linea(123, 0, 1, art=9, bultos=50, hl=5, neto=200),            # envase: suma $ pero no volumen
        linea(123, 0, 2, art=2, bultos=4, hl=.4, neto=400, tipo='PRVTA', origen='PREVENTA'),
        linea(123, 7, 3, art=1, bultos=6, hl=.6, neto=0, tipo='RMCYO'),  # pedido y volumen, sin venta en $
        linea(123, 7, 4, art=1, bultos=99, hl=9, neto=0, tipo='REMIT'),  # remito: se excluye
        linea(123, 14, 5, art=1, bultos=20, hl=2, neto=2000, rech=5, motivo='CERRADO'),
    ])
    c = ventas_app.comportamiento(60, HASTA)['clientes'][123]
    assert (c['compras'], c['comprobantes']) == (3, 4)
    assert (c['bultos'], c['hl'], c['neto']) == (40, 4, 3600)
    assert c['ticket'] == 3600 / 2 and c['drop'] == round(40 / 3, 1)   # 2 días con factura o preventa
    assert c['rech'] == 5 and c['rech_pct'] == round(5 / 40, 3) and c['motivos'] == {'CERRADO': 1}
    assert c['frec'] == 7 and c['dias_sin'] == 0 and c['estado'] == 'activo' and c['bees'] == 1
    assert c['bultos_sem'] == round(40 / (60 / 7), 1)


def test_estado_y_cliente_sin_compras(ctx):
    cargar([linea(1, d, i) for i, d in enumerate([54, 47, 40, 33, 26])] + [linea(2, 50, 90), linea(2, 58, 91)])
    c = ventas_app.comportamiento(60, HASTA)['clientes']
    assert c[1]['estado'] == 'riesgo' and c[2]['estado'] == 'inactivo'
    assert 3 not in c


def test_sin_tablas_devuelve_vacio(ctx):
    assert ventas_app.comportamiento(60)['clientes'] == {}
    assert ventas_app.detalle_cliente(123)['ultimos'] == []


def test_endpoints_ficha_y_mapa(ctx):
    rows, branches = source()
    rows = rows + [dict(rows[0], cliente='124', descripcion='Vecino')]
    actualizar_desde_maestro('operador', (rows, branches))
    cargar([linea(123, d, i, bultos=10) for i, d in enumerate([0, 7, 14, 21])]
           + [linea(124, d, 50 + i, bultos=30) for i, d in enumerate([1, 8])]
           + [linea(123, 0, 99, art=9, bultos=500)])
    c = ctx.test_client()
    r = c.get('/rutas/api/ventas/comportamiento?dias=60').json
    assert r['fuente'] == 'ventas_detalle' and r['hasta'] == HASTA.isoformat()
    assert r['clientes']['123']['compras'] == 4 and r['clientes']['123']['comprobantes'] == 5 and r['clientes']['123']['bultos'] == 40 and 'ent' not in r['clientes']['123']
    r = c.get('/rutas/api/clientes/123/ventas?dias=30').json
    assert r['dias'] == 30 and r['metricas']['compras'] == 4 and r['metricas']['drop'] == 10
    ref = r['referencia']
    assert (ref['localidad'], ref['clientes'], ref['drop'], ref['frec']) == ('DOLORES', 2, 20, 7)
    assert ref['bultos_sem'] == pytest.approx((40 + 60) / (30 / 7) / 2, abs=.1)
    assert [a['articulo'] for a in r['articulos']] == ['QUILMES 1L']
    assert len(r['ultimos']) == 4 and r['ultimos'][0]['fecha'] == HASTA.isoformat() and r['ultimos'][0]['comprobantes'] == 2
    assert sum(s['bultos'] for s in r['semanas']) == 40 and sum(s['compras'] for s in r['semanas']) == 4
    assert c.get('/rutas/api/clientes/999/ventas').json['metricas'] is None


def test_varios_comprobantes_el_mismo_dia_son_una_compra(ctx):
    cargar([linea(7, 0, 1, bultos=10, neto=1000), linea(7, 0, 2, bultos=5, neto=500),
            linea(7, 0, 3, bultos=1, neto=0, tipo='RMCYO'), linea(7, 7, 4, bultos=6, neto=600)])
    c = ventas_app.comportamiento(60, HASTA)['clientes'][7]
    assert (c['compras'], c['comprobantes']) == (2, 4)
    assert c['drop'] == 11 and c['ticket'] == 1050 and c['frec'] == 7
    d = ventas_app.detalle_cliente(7, 60, HASTA)
    assert [(u['fecha'], u['comprobantes'], u['bultos'], u['tipo']) for u in d['ultimos']] == [
        (HASTA.isoformat(), 3, 16, 'FCVTA+RMCYO'), ((HASTA - timedelta(days=7)).isoformat(), 1, 6, 'FCVTA')]
    assert sum(s['compras'] for s in d['semanas']) == 2
