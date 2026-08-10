from datetime import date

from flask import Flask

import app.routes.rechazos as rechazos
from app.services import rechazos_svc


def _app():
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(rechazos.bp)
    return app.test_client()


def test_rechazos_diario_resumen_route(monkeypatch):
    def fake(desde, hasta, sucursal):
        assert desde == date(2026, 1, 1)
        assert hasta == date(2026, 1, 31)
        assert sucursal == '2'
        return {'datos': [{'fecha': '2026-01-02', 'pallets_rechazo': 0.5}]}

    monkeypatch.setattr(rechazos_svc, 'get_resumen_diario', fake)

    res = _app().get('/api/rechazos/diario/resumen?desde=2026-01-01&hasta=2026-01-31&sucursal=2')

    assert res.status_code == 200
    assert res.get_json()['datos'][0]['pallets_rechazo'] == 0.5


def test_rechazos_diario_detalle_route(monkeypatch):
    def fake(desde, hasta, sucursal):
        return {'datos': [{'fecha': desde.isoformat(), 'chofer': 'Juan', 'motivo': 'Cerrado'}]}

    monkeypatch.setattr(rechazos_svc, 'get_detalle_diario', fake)

    res = _app().get('/api/rechazos/diario/detalle?desde=2026-01-01&hasta=2026-01-31')

    assert res.status_code == 200
    assert res.get_json()['datos'][0]['chofer'] == 'Juan'


def test_rechazos_diario_integracion_route(monkeypatch):
    def fake(desde, hasta, sucursal):
        return {'resumen_diario': [], 'detalle_diario': [], 'sucursal': sucursal}

    monkeypatch.setattr(rechazos_svc, 'get_integracion_diaria', fake)

    res = _app().get('/api/rechazos/diario/integracion?desde=2026-01-01&hasta=2026-01-31&sucursal=TODAS')

    assert res.status_code == 200
    assert set(res.get_json()) == {'resumen_diario', 'detalle_diario', 'sucursal'}


def test_rechazos_diario_fecha_invalida_devuelve_400():
    res = _app().get('/api/rechazos/diario/resumen?desde=mal&hasta=2026-01-31')

    assert res.status_code == 400
