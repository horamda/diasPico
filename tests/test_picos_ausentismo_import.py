import io

from flask import Flask

import app.routes.picos as picos
from app.services import pico_svc


class _Cursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


class _Conn:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def test_importar_ausentismo_historico_formato_ancho(monkeypatch):
    cursor = _Cursor()
    monkeypatch.setattr(pico_svc, "_ensure_ausentismo_mensual_table", lambda: None)
    monkeypatch.setattr(pico_svc, "pg_cursor", lambda: _Conn(cursor))

    result = pico_svc.importar_ausentismo_historico({
        "texto": "Sucursal;Año;Ene;Feb;2026-05;Jun-26\nTODAS;2025;2,7;3.4;6,1%;7\n"
    })

    assert result["registros"] == 4
    assert result["anios"] == [2025, 2026]
    assert result["sucursales"] == ["TODAS"]
    assert [call[1]["m"] for call in cursor.calls] == [1, 2, 5, 6]
    assert [call[1]["p"] for call in cursor.calls] == [2.7, 3.4, 6.1, 7.0]


def test_post_import_ausentismo_mensual_csv(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(picos.bp)
    captured = {}
    cleared = []

    def fake_import(data):
        captured.update(data)
        return {"registros": 12, "omitidas": 0, "anios": [2025], "sucursales": ["TODAS"]}

    monkeypatch.setattr(picos.pico_svc, "importar_ausentismo_historico", fake_import)
    monkeypatch.setattr(picos.cache_svc, "clear", cleared.append)

    client = app.test_client()
    res = client.post(
        "/api/picos/ausentismo-mensual/import",
        data={"file": (io.BytesIO(b"Sucursal;Anio;Ene\nTODAS;2025;2.5\n"), "aus.csv")},
        content_type="multipart/form-data",
    )

    assert res.status_code == 200
    payload = res.get_json()
    assert payload["ok"] is True
    assert payload["registros"] == 12
    assert captured["sucursal_id"] == "TODAS"
    assert "TODAS;2025;2.5" in captured["texto"]
    assert cleared == ["picos:", "portal:"]
