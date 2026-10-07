import pytest
from flask import Flask, g
from sqlalchemy import create_engine, event
from app.rutas import init_rutas
from app.rutas.db import Session, create_all
from app.rutas.models import Cliente, ClienteEntrega, Localidad, Deposito, Vehiculo, CambioLog
from app.rutas.maestro import actualizar_desde_maestro, coordenadas
from app.services import portal_svc


@pytest.fixture
def app(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='rutas-tests-only', RUTAS_ENGINE=create_engine('sqlite:///:memory:'))
    @event.listens_for(app.config['RUTAS_ENGINE'], 'connect')
    def fk(conn, record):
        conn.execute('PRAGMA foreign_keys=ON')
    app.add_url_rule('/portal', 'portal.portal_home', lambda: 'Portal')
    app.add_url_rule('/login', 'portal.login', lambda: 'Login')
    @app.before_request
    def user():
        g.portal_user = app.config.get('TEST_USER', {'id': 1, 'username': 'operador'})
    monkeypatch.setattr(portal_svc, 'list_modules_for_user', lambda u: [{'codigo': 'rutas_entrega'}, {'codigo': 'importaciones_datos'}])
    init_rutas(app)
    return app


def source(**overrides):
    row = dict(cliente='123', descripcion='Cliente prueba', localidad='DOLORES', sucursal='2', anulado='NO',
               coord_x='-57.68', coord_y='-36.31', fuerza_venta_1_dias_visita='MAR,VIE')
    return ([dict(row, **overrides)], {'1': 'CASA CENTRAL', '2': 'DOLORES'})


def seed(app):
    with app.app_context():
        create_all()
        actualizar_desde_maestro('operador', source())


def test_lazy_start_and_pages(app):
    assert not app.extensions['rutas_db']['ready']
    c = app.test_client()
    assert c.get('/rutas/').status_code == 200
    assert c.get('/rutas/plan').status_code == 200
    assert not app.extensions['rutas_db']['ready']
    assert c.get('/rutas/api/datos').json['clientes'] == []


def test_auth_and_module_permission(app, monkeypatch):
    app.config['TEST_USER'] = None
    c = app.test_client()
    assert c.get('/rutas/').status_code == 302
    assert c.get('/rutas/api/datos').status_code == 401
    assert c.patch('/rutas/api/clientes/123', json={'dias':'LU'}).status_code in (404,405)
    app.config['TEST_USER'] = {'id':1}
    monkeypatch.setattr(portal_svc, 'list_modules_for_user', lambda u: [])
    assert c.get('/rutas/api/datos').status_code == 403
    assert not app.extensions['rutas_db']['ready']


def test_refresh_preserves_planning_and_uses_delivery_coords(app):
    seed(app)
    c = app.test_client()
    assert c.get('/rutas/api/datos').json['clientes'][0]['d'] == ''
    from app.rutas.services import actualizar_cliente
    with app.app_context():
        actualizar_cliente(123, {'dias':'LUJU', 'nota':'Portón', 'lat':-36.32, 'lng':-57.69}, usuario='operador')
    with app.app_context():
        actualizar_desde_maestro('refresh', source(descripcion='Nombre nuevo', coord_x_entrega='-58', coord_y_entrega='-36'))
        cli = Session().get(Cliente,123)
        assert cli.lat == -36
        assert cli.entrega.dias == 'LUJU'
        assert cli.entrega.nota == 'Portón'
        assert cli.entrega.lat == -36.32
    rows = c.get('/rutas/api/clientes/123/historial').json
    assert {r['campo'] for r in rows} == {'dias','nota','ubicacion'}
    assert all(r['usuario']=='operador' for r in rows)


@pytest.mark.parametrize('payload', [{'lat':-36}, {'dias':'XX'}, {'lat':'abc','lng':1}, {'nota':[]}, {'dias':None}])
def test_invalid_client_edit_does_not_write(app, payload):
    seed(app)
    c=app.test_client()
    assert c.patch('/rutas/api/clientes/123',json=payload).status_code in (404,405)
    assert c.get('/rutas/api/clientes/123/historial').json == []


def test_rutas_rejects_all_mutation_endpoints(app):
    c=app.test_client()
    for method,path in [('post','/rutas/api/vehiculos'),('patch','/rutas/api/vehiculos/1'),('put','/rutas/api/vehiculos/1/plan'),('put','/rutas/api/localidades/1'),('post','/rutas/api/localidades'),('put','/rutas/api/depositos/1'),('post','/rutas/api/actualizar-maestro'),('post','/rutas/api/importar-dias/confirmar')]:
        assert getattr(c,method)(path,json={}).status_code in (404,405)
    assert c.get('/rutas/importar-dias').status_code==404


def test_ambiguous_locality_not_assigned_and_ids_not_merged(app):
    with app.app_context():
        create_all()
        row=source(localidad='LOCALIDAD COMPARTIDA')[0][0]
        rows=[row,dict(row,cliente='124',sucursal='1'),dict(row,cliente='abc'),dict(row,cliente='0125'),dict(row,cliente='125')]
        result=actualizar_desde_maestro('test',(rows,source()[1]))
        assert result['omitidos']==3
        assert Session().query(Localidad).filter_by(nombre='LOCALIDAD COMPARTIDA').one().deposito_id is None


def test_inactive_master_marks_client_without_losing_plan(app):
    seed(app)
    with app.app_context():
        actualizar_desde_maestro('test',source(activo_maestro=False))
        assert Session().get(Cliente,123).anulado


def test_empty_master_preserves_existing(app):
    seed(app)
    with app.app_context():
        with pytest.raises(ValueError):
            actualizar_desde_maestro('test',([],{}))
        assert Session().query(Cliente).count()==1


def test_refresh_endpoint_and_cross_origin(app, monkeypatch):
    from app.rutas import maestro
    monkeypatch.setattr(maestro, 'leer_maestro', source)
    c=app.test_client()
    assert c.post('/importaciones/rutas/api/actualizar-maestro',json={}).json['nuevos']==1
    assert c.post('/importaciones/rutas/api/actualizar-maestro',json={},headers={'Origin':'https://other.example'}).status_code==403
    assert c.post('/rutas/api/sync').status_code==403  # solo con X-Sync-Token
    assert c.get('/rutas/export/bees.csv').status_code==404


def test_coordinate_fallback():
    assert coordenadas({'coord_x_entrega':'NaN','coord_y_entrega':'-36','coord_x':'-57,68','coord_y':'-36,31'})==(-36.31,-57.68)


def test_import_permission_is_separate(app, monkeypatch):
    monkeypatch.setattr(portal_svc, 'list_modules_for_user', lambda u: [{'codigo':'rutas_entrega'}])
    c=app.test_client()
    assert c.get('/rutas/').status_code==200
    assert c.get('/importaciones/rutas/dias').status_code==403
    assert c.post('/importaciones/rutas/api/actualizar-maestro',json={}).status_code==403


@pytest.mark.parametrize('anulado,dias,active', [
    ('NO','LUN',True), (' no ',' mar,vie ',True), ('NO','DOM,LUN',True),
    ('NO','DOM',False), ('NO',' dom ',False), ('NO','',False),
    ('NO','   ',False), ('NO',None,False), ('SI','LUN',False),
    ('','LUN',False), (None,'LUN',False),
])
def test_delivery_active_rule(anulado, dias, active):
    from app.rutas.maestro import cliente_activo
    assert cliente_activo({'anulado':anulado,'fuerza_venta_1_dias_visita':dias}) is active


def test_visit_rule_excludes_csv_without_erasing_delivery_days(app):
    from app.rutas.services import actualizar_cliente
    from app.rutas.importar_dias import preparar
    seed(app)
    with app.app_context():
        actualizar_cliente(123, {'dias':'LUJU'}, usuario='test')
        actualizar_desde_maestro('test', source(fuerza_venta_1_dias_visita='DOM'))
        assert Session().get(Cliente,123).anulado is True
        assert Session().get(ClienteEntrega,123).dias=='LUJU'
        data=b'CLIENTE;LUNES;MARTES;MIERCOLES;JUEVES;VIERNES;SABADO\n123;;1;;;1;\n'
        assert preparar(data,'dias.csv','test','reemplazar')['resumen']['inactivo']==1
        actualizar_desde_maestro('test', source())
        assert Session().get(Cliente,123).anulado is False


def test_same_active_filter_for_every_branch_and_view(app):
    rows=[]
    for branch in ('1','2'):
        for offset, values in enumerate([{'anulado':'NO','fuerza_venta_1_dias_visita':'LUN'},
                                         {'anulado':'SI','fuerza_venta_1_dias_visita':'LUN'},
                                         {'anulado':'NO','fuerza_venta_1_dias_visita':''},
                                         {'anulado':'NO','fuerza_venta_1_dias_visita':'DOM'}]):
            rows.append(source(cliente=str(int(branch)*100+offset),sucursal=branch,**values)[0][0])
    with app.app_context():
        create_all()
        actualizar_desde_maestro('test',(rows,source()[1]))
    c=app.test_client()
    data=c.get('/rutas/api/datos').json
    assert {row['id'] for row in data['clientes']}=={100,200}
    assert data['resumen']['activos']==2
    assert data['resumen']['sin_dias']==2
    assert c.get('/rutas/api/resumen').json==data['resumen']


@pytest.mark.parametrize('activos,dias,expected', [
    ('si','si',{101}), ('si','no',{102}), ('no','si',{103}), ('no','no',{104}),
    ('todos','si',{101,103}), ('todos','no',{102,104}),
    ('si','todos',{101,102}), ('no','todos',{103,104}), ('todos','todos',{101,102,103,104}),
])
def test_activity_and_assigned_days_filters(app, activos, dias, expected):
    from app.rutas.services import actualizar_cliente
    rows=[source(cliente=str(cid),anulado='NO' if cid<103 else 'SI')[0][0] for cid in range(101,105)]
    with app.app_context():
        create_all()
        actualizar_desde_maestro('test',(rows,source()[1]))
        for cid in (101,103):
            actualizar_cliente(cid,{'dias':'LU'},usuario='test')
    c=app.test_client()
    query=f'?activos={activos}&dias_asignados={dias}'
    data=c.get('/rutas/api/datos'+query).json
    assert {r['id'] for r in data['clientes']}==expected
    assert data['resumen']['clientes']==len(expected)
    assert sum(r['clientes'] for r in data['resumen']['por_localidad'])==len(expected)
    assert c.get('/rutas/api/resumen'+query).json==data['resumen']


def test_unknown_filter_rejected(app):
    assert app.test_client().get('/rutas/api/datos?activos=invalid').status_code==400


@pytest.mark.parametrize('localidad,expected', [
    ('GENERAL   LAVALLE','CASA CENTRAL'),('CASTELLI','CHASCOMUS'),
    ('General   Belgrano','CHASCOMUS'),('Chascomús','CHASCOMUS'),
    ('ESQUINA DE   CROTTO','DOLORES'),('MAIPÚ','DOLORES'),
])
def test_locality_delivery_branch_overrides_master_branch(app, localidad, expected):
    with app.app_context():
        create_all()
        actualizar_desde_maestro('test',source(localidad=localidad,sucursal='1'))
    data=app.test_client().get('/rutas/api/datos').json
    customer=data['clientes'][0]
    assert customer['suc']==expected
    assert data['resumen']['por_localidad'][0]['suc']==expected
    assert next(l for l in data['plan']['localidades'] if l['nombre']==customer['loc'])['deposito']==expected
    assert 'CHASCOMUS' in {d['nombre'] for d in data['plan']['depositos']}


def test_mapping_applies_to_previously_loaded_clients_without_refresh(app):
    with app.app_context():
        create_all()
        dep=Deposito(nombre='DOLORES');Session().add(dep);Session().flush()
        Session().add(Localidad(nombre='CASTELLI',deposito_id=dep.id))
        Session().add(Cliente(id_cliente=9,localidad_erp='CASTELLI',anulado=False))
        Session().commit()
    data=app.test_client().get('/rutas/api/datos').json
    assert data['clientes'][0]['suc']=='CHASCOMUS'
    assert next(l for l in data['plan']['localidades'] if l['nombre']=='CASTELLI')['deposito']=='CHASCOMUS'


def test_dias_de_visita_del_maestro():
    from app.rutas import dias as D
    assert [D.desde_visita(v) for v in ('MAR,VIE', 'JUE', 'DOM', 'MIE,SAB', '', None)] == ['MAVI', 'JU', 'DO', 'MISA', '', '']
