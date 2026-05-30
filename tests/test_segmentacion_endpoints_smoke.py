import io

from flask import Flask, Response
import pytest

import app.routes.segmentacion as segmentacion


@pytest.fixture()
def client():
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(segmentacion.bp)
    return app.test_client()


def test_get_clientes_activos_smoke(client, monkeypatch):
    sample = [
        {
            "cliente_id": "10001",
            "cliente_nombre": "Cliente Demo",
            "sucursal": "1",
            "localidad": "La Plata",
            "activo": True,
        }
    ]
    monkeypatch.setattr(segmentacion.svc, "get_clientes_activos_dpo", lambda **_: sample)

    res = client.get("/api/segmentacion/clientes-activos?limit=10")
    assert res.status_code == 200

    payload = res.get_json()
    assert payload["ok"] is True
    assert isinstance(payload["data"], list)
    assert payload["total"] == len(payload["data"])


def test_get_mapa_clientes_smoke(client, monkeypatch):
    sample = [
        {
            "cliente_id": "10001",
            "cliente_nombre": "Cliente Demo",
            "latitud": -34.9214,
            "longitud": -57.9544,
            "hl": 125.4,
            "cluster_dpo": "Ganador",
        }
    ]
    monkeypatch.setattr(segmentacion.svc, "get_clientes_mapa", lambda **_: sample)

    res = client.get("/api/segmentacion/mapa/clientes?peso=hl&limit=50")
    assert res.status_code == 200

    payload = res.get_json()
    assert payload["ok"] is True
    assert isinstance(payload["data"], list)
    assert payload["total"] == len(payload["data"])


def test_get_autoelevador_resumen_smoke(client, monkeypatch):
    sample = {
        "clientes_totales": 10,
        "clientes_autoelevador": 4,
        "pct_clientes_autoelevador": 40.0,
        "hl_autoelevador": 350.5,
        "costo_autoelevador": 120000.0,
    }
    monkeypatch.setattr(segmentacion.svc, "get_autoelevador_resumen", lambda **_: sample)

    res = client.get("/api/segmentacion/autoelevador/resumen")
    assert res.status_code == 200

    payload = res.get_json()
    assert payload["ok"] is True
    assert isinstance(payload["data"], dict)
    assert "clientes_totales" in payload["data"]


def test_get_resumen_activos_localidad_smoke(client, monkeypatch):
    sample = [
        {
            "sucursal": "1",
            "sucursal_nombre": "Casa Central",
            "localidad": "La Plata",
            "clientes_activos_localidad": 12,
            "clientes_activos_sucursal": 30,
            "pct_localidad_sucursal": 40.0,
        }
    ]
    monkeypatch.setattr(segmentacion.svc, "get_resumen_activos_localidad", lambda **_: sample)

    res = client.get("/api/segmentacion/resumen/activos-localidad?sucursal=1")
    assert res.status_code == 200

    payload = res.get_json()
    assert payload["ok"] is True
    assert isinstance(payload["data"], list)
    assert payload["data"][0]["clientes_activos_localidad"] == 12


def test_post_autoelevador_import_smoke(client, monkeypatch):
    monkeypatch.setattr(segmentacion.svc, "bulk_upsert_autoelevador", lambda registros, fuente="api": len(registros))

    body = {"clientes": [{"is_cliente": "10001"}, {"is_cliente": "10055"}], "fuente": "test"}
    res = client.post("/api/segmentacion/autoelevador/import", json=body)
    assert res.status_code == 200

    payload = res.get_json()
    assert payload["ok"] is True
    assert isinstance(payload["data"], dict)
    assert "actualizados" in payload["data"]


def test_post_autoelevador_import_csv_acepta_cliente_y_fuente(client, monkeypatch):
    captured = {}

    def fake_bulk(registros, fuente="api"):
        captured["registros"] = registros
        captured["fuente"] = fuente
        return len(registros)

    monkeypatch.setattr(segmentacion.svc, "bulk_upsert_autoelevador", fake_bulk)

    data = {
        "file": (io.BytesIO(b"cliente;autoelevador\n10001;SI\n10055;NO\n"), "autoelevador.csv"),
        "fuente": "test_csv",
    }
    res = client.post("/api/segmentacion/autoelevador/import", data=data, content_type="multipart/form-data")
    assert res.status_code == 200

    payload = res.get_json()
    assert payload["ok"] is True
    assert payload["data"]["actualizados"] == 2
    assert payload["data"]["leidos"] == 2
    assert captured["fuente"] == "test_csv"
    assert captured["registros"] == [
        {"is_cliente": "10001", "autoelevador": "SI"},
        {"is_cliente": "10055", "autoelevador": "NO"},
    ]


def test_post_geografia_bulk_smoke(client, monkeypatch):
    monkeypatch.setattr(segmentacion.svc, "bulk_upsert_cliente_geografia", lambda rows: len(rows))

    body = [
        {
            "cliente_id": "10001",
            "latitud": -34.9214,
            "longitud": -57.9544,
            "localidad": "La Plata",
            "sucursal": "1",
        }
    ]
    res = client.post("/api/segmentacion/geografia/bulk", json=body)
    assert res.status_code == 200

    payload = res.get_json()
    assert payload["ok"] is True
    assert isinstance(payload["data"], dict)
    assert "actualizados" in payload["data"]


def test_get_sop_pdf_smoke(client, monkeypatch):
    monkeypatch.setattr(segmentacion.Path, "exists", lambda _: True)

    def _fake_send_file(*_, **__):
        return Response(b"%PDF-1.4\n%Smoke\n", mimetype="application/pdf")

    monkeypatch.setattr(segmentacion, "send_file", _fake_send_file)

    res = client.get("/api/segmentacion/sop/pdf")
    assert res.status_code == 200
    assert res.mimetype == "application/pdf"
    assert res.data.startswith(b"%PDF")
