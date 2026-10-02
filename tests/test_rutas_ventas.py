from datetime import date, timedelta

import pytest

from tests.test_rutas_entrega import app, seed
from app.rutas import dias as D
from app.rutas.chess import ChessClient, ChessError
from app.rutas.db import Session, create_all
from app.rutas.importar_dias import leer_csv
from app.rutas.models import SyncLog, Venta, VentaArticulo
from app.rutas.ventas import comportamiento, guardar_filas, sincronizar

HASTA = date(2026, 9, 30)


def fila(nro, cliente=123, fecha=HASTA, doc='FCVTA', neto=1000.0, suc=2, **extra):
    return dict(idDocumento=doc, letra='A', serie=1, nrodoc=nro, idCliente=cliente, idSucursal=suc,
                fechaComprobate=fecha.isoformat() + 'T00:00:00', fechaEntrega=fecha.isoformat(),
                fechaPedido=(fecha - timedelta(days=1)).isoformat(), subtotalNeto=neto, subtotalFinal=neto * 1.21,
                origen='BEES', dsVendedor='VENDEDOR', anulado='NO', **extra)


def linea(nro, articulo, bultos, neto, **extra):
    return fila(nro, neto=neto, idArticulo=articulo, dsArticuloEstadistico=articulo,
                cantidadesTotal=bultos, unimedtotal=bultos / 10, **extra)


@pytest.fixture
def ctx(app):
    with app.app_context():
        create_all()
        yield app


def test_dias_conversiones():
    assert D.desde_chess('3,6') == 'MAVI'
    assert D.a_chess('MAVI') == '3,6'
    assert D.a_bees('MAVI') == ['NO', 'FREE', 'NO', 'NO', 'FREE', 'NO', 'NO']


def test_csv_bees_completo_toma_solo_cliente_y_dias():
    header = ('DDC_ID;ERP_POC_ID;Vendor_Account_ID;Settings_Type;Mon;Tue;Wed;Thu;Fri;Sat;Sun;'
              + ';'.join(f'Minimum_Order_Value_{d}' for d in D.BEES_COLS) + ';'
              + ';'.join(f'Additional_Fee_{d}' for d in D.BEES_COLS)
              + ';Delivery_Frequency;Reference_Date;Click_And_Collect;Audience_Name;CLIENTE;LUNES;MARTES;MIERCOLES;'
                'JUEVES;VIERNES ;SABADO;CONCATENAR;LOCALIDAD;LAT;LONG;SUCURSAL QUE ENTREGA;TIENE RUTA ASIGNADA;ANULADO;FDVV')
    ceros, vacios = ';'.join(['0'] * 14), ';' * 13
    rows = [
        f'1;;13692800000101;POC-level;NO;FREE;NO;NO;FREE;NO;NO;{ceros};WEEKLY;22/11/2025;NO;;101;;1;;;1;;11;PUEBLO;-57.8;-36.8;DOLORES;SI;NO;LUN',
        f'1;;13692800000102;POC-level;NO;NO;NO;NO;NO;NO;NO;{ceros};WEEKLY;;NO;;102;;;;;;;;PUEBLO;-57.8;-36.8;DOLORES;NO;SI;0',
        f'1;;13692800000103;Default;FREE;NO;NO;FREE;NO;NO;NO;{vacios};WEEKLY;3/2/2026;NO;;103;1;;;1;;;11;PUEBLO;-58.0;-35.5;CHASCOMUS;SI;NO;DOM',
    ]
    out = leer_csv(('\n'.join([header] + rows) + '\n').encode('utf-8'))
    assert [(r['id'], r['dias'], r['error']) for r in out] == [(101, 'MAVI', ''), (102, '', ''), (103, 'LUJU', '')]


def test_guardar_resumen_idempotente_y_nc_negativa(ctx):
    filas = [fila(1), fila(2, fecha=HASTA - timedelta(days=7), neto=500), fila(3, doc='DVVTA', neto=-200, dsRechazo='CERRADO')]
    assert guardar_filas(filas)['nuevos'] == 3
    assert guardar_filas(filas) == {'comprobantes': 3, 'nuevos': 0, 'con_detalle': 0}
    s = Session()
    assert s.query(Venta).count() == 3
    nc = s.get(Venta, 'DVVTA-A-1-3')
    assert nc.es_nc and nc.neto == -200 and nc.rechazo == 'CERRADO'
    assert s.get(Venta, 'FCVTA-A-1-1').bultos is None


def test_guardar_detalle_suma_lineas_sin_duplicar_articulos(ctx):
    filas = [linea(9, 'QUILMES 1L', 10, 3000), linea(9, 'QUILMES 1L', 5, 1500), linea(9, 'AGUA', 2, 400)]
    guardar_filas(filas)
    guardar_filas(filas)
    s = Session()
    v = s.get(Venta, 'FCVTA-A-1-9')
    assert (v.neto, v.bultos, v.hl) == (4900, 17, 1.7)
    arts = {a.articulo: a.bultos for a in s.query(VentaArticulo)}
    assert arts == {'QUILMES 1L': 15, 'AGUA': 2}


def test_filtro_sucursal(ctx):
    guardar_filas([fila(1, suc=1), fila(2, suc='2')], sucursales=[2])
    assert [v.id for v in Session().query(Venta)] == ['FCVTA-A-1-2']


def _compras(cliente, dias_atras, neto, inicio):
    return [fila(inicio + i, cliente=cliente, fecha=HASTA - timedelta(days=d), neto=neto) for i, d in enumerate(dias_atras)]


def test_comportamiento_estados(ctx):
    guardar_filas(_compras(1, range(0, 60, 7), 1000, 100)            # compra cada semana
                  + _compras(2, [54, 47, 40, 33, 26], 100, 200)       # frec. 7, hace 26 días
                  + _compras(3, [58, 50], 100, 300)                   # hace 50 días
                  + [fila(400, cliente=4, doc='DVVTA', neto=-50)])    # solo nota de crédito
    c = comportamiento(60, HASTA)['clientes']
    assert {k: c[k]['estado'] for k in c} == {1: 'activo', 2: 'riesgo', 3: 'inactivo', 4: 'sin_compras'}
    assert c[1]['frec'] == 7 and c[1]['dias_sin'] == 0 and c[1]['bees'] == 1
    assert c[2]['dias_sin'] == 26
    assert c[4]['nc'] == 50 and c[4]['abc'] == '-'


def test_comportamiento_abc(ctx):
    netos = [50, 20, 10, 5, 5, 4, 3, 1, 1, 1]
    guardar_filas([fila(i, cliente=i + 1, neto=n) for i, n in enumerate(netos)])
    c = comportamiento(60, HASTA)['clientes']
    assert ''.join(c[i + 1]['abc'] for i in range(len(netos))) == 'AAABBBCCCC'


class FakeChess:
    def __init__(self, lotes):
        self.lotes, self.calls = lotes, []

    def login(self):
        return True

    def ventas_lote(self, d1, d2, lote, detalle):
        self.calls.append((d1, d2, lote, detalle))
        filas = self.lotes.get((d1.month, lote), [])
        total = len([k for k in self.lotes if k[0] == d1.month]) or 1
        return {'cantComprobantesVentas': f'Numero de lote obtenido: {lote}/{total}. Total de comprobantes: x',
                'dsReporteComprobantesApi': {'VentasResumen': filas}}


def test_sincronizar_detalle_partido_entre_lotes_y_por_mes(ctx):
    fake = FakeChess({
        (9, 1): [linea(1, 'A', 1, 100), linea(2, 'A', 1, 100)],
        (9, 2): [linea(2, 'B', 2, 300), linea(3, 'A', 1, 50)],
    })
    res = sincronizar(date(2026, 8, 25), HASTA, sucursales=[2], detalle=True, client=fake)
    assert [(c[0], c[1], c[2]) for c in fake.calls] == [
        (date(2026, 8, 25), date(2026, 8, 31), 1), (HASTA.replace(day=1), HASTA, 1), (HASTA.replace(day=1), HASTA, 2)]
    s = Session()
    assert s.get(Venta, 'FCVTA-A-1-2').neto == 400 and s.get(Venta, 'FCVTA-A-1-2').bultos == 3
    assert res['comprobantes'] == 3
    log = s.query(SyncLog).filter_by(origen='chess-ventas-detalle').one()
    assert log.leidos == 4 and log.nuevos == 3 and log.fin and not log.error


class Resp:
    def __init__(self, status, payload):
        self.status_code, self._p, self.text = status, payload, str(payload)

    def json(self):
        return self._p


class FakeHttp:
    def __init__(self, gets):
        self.headers, self.gets, self.posts, self.params = {}, list(gets), 0, []

    def post(self, url, json, timeout):
        self.posts += 1
        assert url.endswith('/auth/login') and json == {'usuario': 'u', 'password': 'p'}
        return Resp(200, {'sessionId': f'JSESSIONID=s{self.posts}'})

    def get(self, url, params, timeout):
        self.params.append((url, params, self.headers.get('Cookie')))
        return self.gets.pop(0)


def test_chess_client_login_cookie_y_relogin():
    http = FakeHttp([Resp(401, {}), Resp(200, {'dsReporteComprobantesApi': {'VentasResumen': []}})])
    client = ChessClient('https://chess.test/v1', 'u', 'p', session=http)
    client.ventas_lote(date(2026, 9, 1), date(2026, 9, 30), 2, True)
    assert http.posts == 2
    url, params, cookie = http.params[-1]
    assert url == 'https://chess.test/v1/ventas/' and cookie == 'JSESSIONID=s2'
    assert params == {'fechaDesde': '01-09-2026', 'fechaHasta': '30-09-2026', 'detallado': 'true', 'nroLote': 2}


def test_chess_client_errores(monkeypatch):
    for var in ('CHESS_USER', 'CHESS_PASSWORD', 'FRESCURA_API_USER', 'FRESCURA_API_PASSWORD'):
        monkeypatch.delenv(var, raising=False)
    http = FakeHttp([Resp(200, {'error': [{'mensaje': 'El rango de fecha corresponde a uno mayor de mes calendario'}]})])
    with pytest.raises(ChessError, match='mes calendario'):
        ChessClient('https://chess.test/v1', 'u', 'p', session=http).ventas_lote(date(2026, 8, 1), date(2026, 9, 30))
    with pytest.raises(ChessError, match='CHESS_USER'):
        ChessClient('https://chess.test/v1', '', '', session=FakeHttp([])).login()


def test_endpoints_ventas(app):
    seed(app)
    with app.app_context():
        guardar_filas(_compras(123, [21, 14, 7, 0], 1000, 1))
    c = app.test_client()
    r = c.get('/rutas/api/ventas/comportamiento?dias=60').json
    assert r['clientes']['123']['estado'] == 'activo' and 'ent' not in r['clientes']['123']
    r = c.get('/rutas/api/clientes/123/ventas').json
    assert r['metricas']['compras'] == 4 and len(r['ultimos']) == 4 and r['sugerencia']['en_dia'] == 0
    assert c.get('/rutas/api/clientes/999/ventas').json['metricas'] is None
    assert c.get('/rutas/api/ventas/comportamiento?dias=3').status_code == 400


def test_sync_endpoint_por_token(app, monkeypatch):
    import app.rutas.ventas as V
    llamadas = []
    monkeypatch.setattr(V, 'sincronizar', lambda d, h, s, detalle: llamadas.append((d, h, s, detalle)) or {'nuevos': 1})
    app.config['TEST_USER'] = None
    c = app.test_client()
    assert c.post('/rutas/api/sync').status_code == 403
    app.config['RUTAS_SYNC_TOKEN'] = 'secreto'
    assert c.post('/rutas/api/sync', headers={'X-Sync-Token': 'otro'}).status_code == 403
    r = c.post('/rutas/api/sync?dias=3', headers={'X-Sync-Token': 'secreto'})
    assert r.status_code == 200 and r.json['nuevos'] == 1
    assert llamadas[0][1] - llamadas[0][0] == timedelta(days=2) and llamadas[0][3] is False
