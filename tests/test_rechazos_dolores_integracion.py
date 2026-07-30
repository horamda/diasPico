import io
from datetime import date

from flask import Flask

import app.routes.picos as picos
from app.services import pico_svc


def _fake_calendario(sucursal, mes, *args, **kwargs):
    assert sucursal == '2'
    assert args == (None, None)
    dias = {
        '2026-01': [
            {
                'fecha': '2026-01-02',
                'pedidos': 10,
                'clientes_unicos': 9,
                'rechazo_pedidos': 2,
                'pct_rechazo_pedidos': 20,
                'bultos': 100,
                'rechazo_bultos': 5,
                'rechazo_bultos_parcial': 2,
                'rechazo_bultos_total': 3,
                'pct_rechazo_bultos': 5,
                'hectolitros': 12,
                'rechazo_hl': 1.2,
                'rechazo_hl_parcial': 0.5,
                'rechazo_hl_total': 0.7,
                'pct_rechazo_hl': 10,
                'nds': 80,
                'camiones_salidos': 3,
                'es_pico': True,
                'feriado_desc': '',
                'evento_desc': 'Evento prueba',
            }
        ],
        '2026-02': [
            {
                'fecha': '2026-02-01',
                'pedidos': 4,
                'clientes_unicos': 4,
                'rechazo_pedidos': 0,
                'bultos': 40,
                'hectolitros': 4,
                'camiones_salidos': 1,
            }
        ],
    }
    return {'dias': dias.get(mes, [])}


def test_get_rechazos_dolores_diario_usa_rango_y_campos(monkeypatch):
    monkeypatch.setattr(pico_svc, 'get_calendario', _fake_calendario)

    data = pico_svc.get_rechazos_dolores_diario(date(2026, 1, 1), date(2026, 1, 31))

    assert data['sucursal_id'] == '2'
    assert data['sucursal'] == 'Dolores'
    assert data['desde'] == '2026-01-01'
    assert data['hasta'] == '2026-01-31'
    assert data['total_dias'] == 1
    assert data['campos'] == pico_svc.RECHAZOS_DOLORES_HEADERS
    assert data['datos'][0]['fecha'] == '2026-01-02'
    assert data['datos'][0]['rechazo_hl'] == 1.2
    assert data['datos'][0]['evento'] == 'Evento prueba'


def test_rechazos_dolores_diario_route_json_y_csv(monkeypatch):
    monkeypatch.setattr(pico_svc, 'get_calendario', _fake_calendario)

    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(picos.bp)
    client = app.test_client()

    res_json = client.get('/api/picos/rechazos-dolores/diario?desde=2026-01-01&hasta=2026-01-31')
    assert res_json.status_code == 200
    assert res_json.get_json()['datos'][0]['sucursal'] == 'Dolores'

    res_csv = client.get('/api/picos/rechazos-dolores/diario?desde=2026-01-01&hasta=2026-01-31&formato=csv')
    assert res_csv.status_code == 200
    assert res_csv.mimetype == 'text/csv'
    text = res_csv.data.decode('utf-8')
    assert text.startswith('fecha,sucursal_id,sucursal')
    assert '2026-01-02,2,Dolores' in text
