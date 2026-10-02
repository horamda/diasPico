import io
import pytest
from tests.test_rutas_entrega import app, seed
from app.rutas.importar_dias import leer_csv, preparar, confirmar, VistaDesactualizada
from app.rutas.db import Session
from app.rutas.models import Cliente, ClienteEntrega, CambioLog, ImportacionDias

HEADER = 'CLIENTE;LUNES;MARTES;MIERCOLES;JUEVES;VIERNES ;SABADO\n'


def content(lines='123;1;;;1;;\n'):
    return (HEADER + lines).encode('utf-8-sig')


def test_csv_spaces_accents_both_day_groups():
    data='CLIENTE;LUNES;MARTES;MIÉRCOLES;JUEVES;VIERNES ;SABADO;Mon;Tue;Wed;Thu;Fri;Sat;Sun\n123;;1;;;1;;NO;FREE;NO;NO;FREE;NO;NO\n'
    rows=leer_csv(data.encode('cp1252'))
    assert rows[0]['dias']=='MAVI'
    assert not rows[0]['error']
    assert leer_csv(data.replace('NO;FREE;NO;NO;FREE', 'FREE;FREE;NO;NO;FREE').encode())[0]['dias']=='MAVI'
    assert not leer_csv(data.replace('NO;FREE;NO;NO;FREE', 'FREE;FREE;NO;NO;FREE').encode())[0]['error']


@pytest.mark.parametrize('data', [b'', b'wrong;headers\n1;2', b'\x00', content()*100000], ids=['empty','headers','binary','oversize'])
def test_invalid_files_rejected(data):
    with pytest.raises(ValueError):
        leer_csv(data)


def test_duplicate_and_invalid_rows_excluded():
    rows=leer_csv(content('123;1;;;1;;\n0123;;1;;;1;\nABC;;;;;;\n124;maybe;;;;;\n'))
    assert all(r['error'] for r in rows)


def test_preview_does_not_write_then_confirmation_is_idempotent(app):
    seed(app)
    with app.app_context():
        result=preparar(content(),'entregas.csv','1',actor='operador')
        assert result['resumen']['asignar']==1
        assert Session().get(ClienteEntrega,123).dias==''
        assert Session().query(CambioLog).count()==0
        assert confirmar(result['token'],'1')['ya_aplicada'] is False
        assert confirmar(result['token'],'1')['ya_aplicada'] is True
        assert Session().get(ClienteEntrega,123).dias=='LUJU'
        assert Session().query(CambioLog).one().usuario=='operador'
        assert Session().query(ImportacionDias).count()==1


def test_fill_preserves_existing_days_replace_can_clear(app):
    seed(app)
    from app.rutas.services import actualizar_cliente
    with app.app_context():
        actualizar_cliente(123,{'dias':'MAVI','nota':'Conservar','lat':-36.3,'lng':-57.7},usuario='test')
    with app.app_context():
        assert preparar(content(),'a.csv','1')['resumen']['conservar']==1
        result=preparar(content('123;;;;;;\n'),'a.csv','1','reemplazar')
        assert result['resumen']['reemplazar']==1
        confirmar(result['token'],'1')
        e=Session().get(ClienteEntrega,123)
        assert e.dias=='' and e.nota=='Conservar' and e.lat==-36.3


def test_stale_preview_applies_nothing(app):
    seed(app)
    with app.app_context():
        result=preparar(content(),'a.csv','1')
    from app.rutas.services import actualizar_cliente
    with app.app_context():
        actualizar_cliente(123,{'dias':'MI'},usuario='test')
    with app.app_context():
        with pytest.raises(VistaDesactualizada):
            confirmar(result['token'],'1')
        assert Session().get(ClienteEntrega,123).dias=='MI'
        assert Session().query(ImportacionDias).count()==0


def test_preview_omits_inactive_and_unknown(app):
    seed(app)
    with app.app_context():
        Session().get(Cliente,123).anulado=True
        Session().commit()
        result=preparar(content('123;1;;;;;\n456;1;;;;;\n'),'a.csv','1')
        assert result['resumen']['inactivo']==1
        assert result['resumen']['no_encontrado']==1
        assert result['token'] is None


def test_tampered_and_other_user_preview_rejected(app):
    seed(app)
    with app.app_context():
        result=preparar(content(),'a.csv','1')
        with pytest.raises(ValueError):
            confirmar('tampered'+result['token'],'1')
        with pytest.raises(ValueError):
            confirmar(result['token'],'2')
        assert Session().query(ImportacionDias).count()==0


def test_upload_confirm_endpoints_and_audit(app):
    seed(app)
    c=app.test_client()
    assert c.get('/importaciones/rutas/dias').status_code==200
    response=c.post('/importaciones/rutas/api/importar-dias/preview',data={'archivo':(io.BytesIO(content()),'rutas.csv'),'modo':'vacios'})
    assert response.status_code==200
    result=c.post('/importaciones/rutas/api/importar-dias/confirmar',json={'token':response.json['token']})
    assert result.status_code==200
    assert c.get('/rutas/api/clientes/123/historial').json[0]['usuario']=='operador'
    assert c.get('/rutas/api/datos').json['clientes'][0]['d']=='LUJU'


def test_upload_requires_permission_and_csv(app):
    seed(app)
    c=app.test_client()
    assert c.post('/importaciones/rutas/api/importar-dias/preview').status_code==400
    app.config['TEST_USER']=None
    assert c.post('/importaciones/rutas/api/importar-dias/preview').status_code==401


@pytest.mark.parametrize('index,expected',enumerate(['LU','MA','MI','JU','VI','SA']))
def test_one_marks_exact_weekday(index,expected):
    cells=['']*6;cells[index]='1'
    row=leer_csv(content('123;'+';'.join(cells)+'\n'))[0]
    assert row['dias']==expected and not row['error']
