from datetime import timedelta

import pytest
from sqlalchemy import text

from tests.test_rutas_ventas_app import ctx, app, cargar, linea, HASTA
from app.rutas import ventas_app as V
from app.rutas.db import Session
from app.rutas.prioridades import diagnostico


def cliente(i, suc='A', loc='Centro', **extra):
    return dict(id=i, n=f'Cliente {i}', suc=suc, loc=loc, d='LUJU', an=False, lat=-36, lng=-57, far=False, **extra)


def camion(i, suc='A'):
    return {'id': i, 'nombre': f'Camión {i}', 'deposito': suc, 'capacidad_clientes': 1, 'plan': {'LU': ['Centro']}}


@pytest.mark.parametrize('dias', [7, 15, 30, 45, 60, 90, 120])
def test_actividad_independiente_de_ventana_y_creditos(ctx, dias):
    cargar([linea(1, 1, 1), linea(2, 50, 2), linea(2, 0, 3, tipo='DVVTA', bultos=-3, neto=-300),
            linea(3, 26, 4), linea(3, 33, 5), linea(3, 40, 6), linea(4, 0, 7, tipo='DVVTA')])
    data = V.comportamiento(dias, HASTA)['clientes']
    assert data[1]['estado'] == 'activo'
    assert data[2]['estado'] == 'inactivo' and data[2]['dias_sin'] == 50
    assert data[3]['estado'] == 'riesgo' and data[3]['frec_hist'] == 7
    assert data[4]['estado'] == 'sin_compras' and data[4]['compras'] == 0
    assert data[4]['ultima'] is None


@pytest.mark.parametrize('dias', [7, 15, 30, 45, 60, 90, 120])
def test_comparacion_igual_duracion_y_limites(ctx, dias):
    cargar([linea(1, 0, 1), linea(1, dias - 1, 2), linea(1, dias, 3, bultos=20),
            linea(1, 2*dias - 1, 4, bultos=30), linea(1, 2*dias, 5, bultos=900)])
    result = diagnostico([cliente(1)], {'vehiculos': []}, dias, hoy=HASTA)
    assert result['volumen']['bultos'] == 20
    assert result['anterior']['bultos'] == 50
    assert result['localidades'][0]['variacion']['bultos'] == -.6
    assert result['anterior_hasta'] == (HASTA - timedelta(days=dias)).isoformat()
    assert result['anterior_desde'] == (HASTA - timedelta(days=2*dias - 1)).isoformat()
    assert result['dias_desactualizacion'] == 0


def test_rutas_compartidas_no_atribuyen_ocupacion_y_dia_no_duplica(ctx):
    cargar([linea(1, 0, 1, bultos=10), linea(2, 0, 2, bultos=20)])
    result = diagnostico([cliente(1), cliente(2)], {'vehiculos': [camion(1), camion(2)]}, 7, hoy=HASTA)
    assert len(result['rutas']) == 2
    assert all(r['compartida'] and r['ocupacion_clientes'] is None for r in result['rutas'])
    assert result['dias_carga'][0]['bultos'] == 30
    assert not any(a['tipo'] == 'capacidad' for a in result['alertas'])
    assert all(r['alta']['bultos'] is None for r in result['rutas'])
    result = diagnostico([cliente(1), cliente(2)], {'vehiculos': [camion(1)]}, 7, hoy=HASTA)
    assert result['rutas'][0]['ocupacion_clientes'] == 2
    assert any(a['tipo'] == 'capacidad' for a in result['alertas'])


def test_rechazos_con_varios_motivos_y_calidad(ctx):
    cargar([linea(1, 0, 1, art=1, rech=2, motivo='CERRADO'),
            linea(1, 0, 1, art=2, rech=3, motivo='SIN DINERO'),
            linea(1, 1, 2, rech=1, motivo='CERRADO'), linea(99, 0, 3)])
    Session().execute(text('UPDATE ventas_detalle SET id_articulo=999 WHERE cliente=\'99\''))
    Session().execute(text('UPDATE ventas_detalle SET unidad_medida=NULL WHERE id_articulo=2'))
    Session().commit()
    r = diagnostico([cliente(1)], {'vehiculos': []}, 30, hoy=HASTA + timedelta(days=8))
    assert sum(x['bultos'] for x in r['rechazos']) == 6
    assert {x['motivo'] for x in r['rechazos']} == {'CERRADO', 'SIN DINERO'}
    assert any(a['tipo'] == 'rechazos' for a in r['alertas'])
    assert r['calidad_origen'] == {'filas_sin_articulo': 1, 'filas_sin_hl': 1, 'filas_sin_cliente': 1}
    assert r['dias_desactualizacion'] == 8
    assert not r['historial_suficiente']
    assert all(v is None for v in r['localidades'][0]['variacion'].values())


def test_sucursal_y_clientes_inactivos_no_contaminan_carga(ctx):
    cargar([linea(1, 0, 1), linea(2, 0, 2, bultos=900), linea(3, 0, 3, bultos=800)])
    inactivo = cliente(3); inactivo['an'] = True
    r = diagnostico([cliente(1), cliente(2, suc='B'), inactivo], {'vehiculos': [camion(1), camion(2, 'B')]}, 7, 'A', HASTA)
    assert r['clientes'] == 1 and r['volumen']['bultos'] == 10
    assert len(r['localidades']) == len(r['rutas']) == 1


def test_frecuencia_y_caida_con_base_suficiente(ctx):
    cargar([linea(1, d, i, bultos=2) for i, d in enumerate([0, 10, 20])]
           + [linea(1, d, 20+i, bultos=10) for i,d in enumerate([30, 40, 59])]
           + [linea(cid, 0, 100+cid, bultos=30) for cid in range(2, 6)])
    r = diagnostico([cliente(i) for i in range(1, 6)], {'vehiculos': []}, 30, hoy=HASTA)
    tipos = {a['tipo'] for a in r['alertas'] if a['id'] == 1}
    assert {'frecuencia', 'caida'} <= tipos
    # El mismo cliente con varios días sin camión se cuenta una vez en el resumen.
    resumen = next(x for x in r['resumen'] if x['tipo'] == 'sin_camion')
    assert resumen['alertas'] == 10 and resumen['clientes'] == 5
    assert resumen['bultos'] == 126


def test_api_prioridades_sin_datos_y_parametros(ctx):
    c = ctx.test_client()
    assert c.get('/rutas/api/ventas/prioridades?dias=7').json['disponible'] is False
    assert c.get('/rutas/api/ventas/prioridades?dias=1').status_code == 400
    cargar([linea(1, 0, 1)])
    V._cache.clear()
    r = c.get('/rutas/api/ventas/prioridades?dias=120')
    assert r.status_code == 200 and r.json['disponible'] is True


def test_escenario_alto_exige_cinco_fechas_y_suma_p90(ctx):
    cargar([linea(1, i, i, bultos=b) for i,b in enumerate([10,10,10,10,50])])
    r = diagnostico([cliente(1)], {'vehiculos': [camion(1)]}, 7, hoy=HASTA)
    assert r['rutas'][0]['bultos'] == 18
    assert r['rutas'][0]['alta']['bultos'] == 50


def test_prioridades_respeta_autenticacion(ctx):
    ctx.config['TEST_USER'] = None
    assert ctx.test_client().get('/rutas/api/ventas/prioridades').status_code == 401


def test_alejamiento_solo_con_coordenadas_confiables_y_bajo_volumen(ctx):
    cargar([linea(i, d, i*100+d, bultos=2 if i==1 else 30) for i in range(1,6) for d in [0,10,20]])
    clientes = [cliente(i) for i in range(1,6)]
    clientes[0]['lat'] = -36.1
    r = diagnostico(clientes, {'vehiculos': []}, 30, hoy=HASTA)
    assert any(a['tipo']=='distancia' and a['id']==1 for a in r['alertas'])
    clientes[0]['far'] = True
    r = diagnostico(clientes, {'vehiculos': []}, 30, hoy=HASTA)
    assert not any(a['tipo']=='distancia' and a['id']==1 for a in r['alertas'])
