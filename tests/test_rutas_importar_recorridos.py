import io
import pytest
from tests.test_rutas_entrega import app
from app.rutas.db import Session, create_all
from app.rutas.models import Vehiculo, PlanRuta, CambioLog, ImportacionRutas, ClienteEntrega
from app.rutas.importar_rutas import preparar, confirmar, leer_csv
from app.rutas.importar_dias import VistaDesactualizada

HEADER='SUCURSAL;VEHICULO;DIA;LOCALIDAD;ORDEN\n'
def content(rows='CHASCOMUS;CAMION 1;LUNES;LEZAMA;2\nCHASCOMUS;CAMION 1;LUNES;CASTELLI;1\n'):
    return (HEADER+rows).encode('utf-8-sig')

@pytest.fixture
def ready(app):
    with app.app_context():
        create_all()
    return app


def test_preview_no_writes_then_creates_and_orders_route(ready):
    with ready.app_context():
        preview=preparar(content(),'rutas.csv','1',actor='operador')
        assert preview['resumen']['crear']==1
        assert Session().query(Vehiculo).count()==0
        assert [p['localidad'] for p in preview['rows'][0]['paradas']]==['CASTELLI','LEZAMA']
        result=confirmar(preview['token'],'1')
        assert result['ok']
        assert Session().query(Vehiculo).one().to_dict()['plan']=={'LU':['CASTELLI','LEZAMA']}
        assert Session().query(CambioLog).one().usuario=='operador'
        assert Session().query(ClienteEntrega).count()==0
        assert confirmar(preview['token'],'1')['ya_aplicada']
        assert Session().query(ImportacionRutas).count()==1
        assert Session().query(PlanRuta).count()==2


def test_same_vehicle_multiple_days_and_replace_preserves_other_days(ready):
    with ready.app_context():
        data=content('DOLORES;CAMION 1;LU;DOLORES;1\nDOLORES;CAMION 1;MA;MAIPU;1\n')
        confirmar(preparar(data,'a.csv','1')['token'],'1')
        changed=content('DOLORES;CAMION 1;LU;LAS ARMAS;1\n')
        assert preparar(changed,'b.csv','1')['resumen']['conservar']==1
        preview=preparar(changed,'b.csv','1','reemplazar')
        confirmar(preview['token'],'1')
        assert Session().query(Vehiculo).one().to_dict()['plan']=={'LU':['LAS ARMAS'],'MA':['MAIPU']}


@pytest.mark.parametrize('bad',[
    'DOLORES;CAMION 1;LU;CASTELLI;1\n',
    'DOLORES;CAMION 1;DOMINGO;DOLORES;1\n',
    'DOLORES;CAMION 1;LU;DOLORES;0\n',
    'DOLORES;CAMION 1;LU;NO EXISTE;1\n',
    'DOLORES;CAMION 1;LU;DOLORES;1\nDOLORES;CAMION 1;LU;MAIPU;1\n',
    'DOLORES;CAMION 1;LU;DOLORES;1\nDOLORES;CAMION 1;LU;DOLORES;2\n',
])
def test_any_invalid_route_blocks_whole_confirmation(ready,bad):
    with ready.app_context():
        preview=preparar(content(bad+'CHASCOMUS;CAMION 2;LU;CASTELLI;1\n'),'bad.csv','1')
        assert preview['token'] is None
        assert preview['resumen'].get('error',0)+preview['resumen']['errores_fila']>0
        assert Session().query(PlanRuta).count()==0


def test_stale_preview_rejected_atomically(ready):
    with ready.app_context():
        confirmar(preparar(content(),'a.csv','1')['token'],'1')
        changed=content('CHASCOMUS;CAMION 1;LU;PILA;1\n')
        preview=preparar(changed,'b.csv','1','reemplazar')
        Session().query(PlanRuta).first().orden=9;Session().commit()
        with pytest.raises(VistaDesactualizada):
            confirmar(preview['token'],'1')
        assert Session().query(ImportacionRutas).count()==1


def test_inactive_vehicle_and_wrong_identity_are_rejected(ready):
    with ready.app_context():
        preview=preparar(content(),'a.csv','1')
        with pytest.raises(ValueError):confirmar(preview['token'],'2')
        with pytest.raises(ValueError):confirmar('bad'+preview['token'],'1')
        confirmar(preview['token'],'1')
        Session().query(Vehiculo).one().activo=False;Session().commit()
        assert preparar(content(),'b.csv','1')['token'] is None


def test_http_preview_confirmation_template_and_read_only_map(ready):
    c=ready.test_client()
    assert c.get('/importaciones/rutas/recorridos').status_code==200
    template=c.get('/importaciones/rutas/recorridos/plantilla.csv')
    assert template.status_code==200 and len(leer_csv(template.data))==3
    p=c.post('/importaciones/rutas/api/importar-rutas/preview',data={'archivo':(io.BytesIO(content()),'rutas.csv')})
    assert p.status_code==200
    assert c.post('/importaciones/rutas/api/importar-rutas/confirmar',json={'token':p.json['token']}).status_code==200
    assert c.get('/rutas/api/datos').json['plan']['vehiculos'][0]['plan']['LU']==['CASTELLI','LEZAMA']
    assert c.post('/rutas/api/vehiculos',json={}).status_code==404


def test_import_permission_required(ready,monkeypatch):
    from app.services import portal_svc
    monkeypatch.setattr(portal_svc,'list_modules_for_user',lambda u:[{'codigo':'rutas_entrega'}])
    c=ready.test_client()
    assert c.get('/importaciones/rutas/recorridos').status_code==403
    assert c.post('/importaciones/rutas/api/importar-rutas/preview').status_code==403
    assert c.post('/importaciones/rutas/api/importar-rutas/confirmar',json={}).status_code==403
