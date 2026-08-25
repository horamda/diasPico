from datetime import date
from decimal import Decimal

from flask import Flask

import app.routes.integracion_logistica as route
from app.services import integracion_logistica_svc as svc


def _client(api_key="secreto"):
    app = Flask(__name__)
    app.config.update(TESTING=True, INTEGRATION_API_KEY=api_key)
    app.register_blueprint(route.bp)
    return app.test_client()


def test_logistica_diaria_devuelve_contrato_versionado(monkeypatch):
    captured = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return {
            "total": 1,
            "fecha_min": "2026-08-13",
            "fecha_max": "2026-08-13",
            "datos": [{"fecha": "2026-08-13", "camion_codigo": "1100"}],
        }

    monkeypatch.setattr(route.svc, "get_logistica_diaria", fake)
    response = _client().get(
        "/api/v1/integracion/logistica/diaria"
        "?fecha=2026-08-13&sucursal=1&incluir_clientes=1&limit=50",
        headers={"X-API-Key": "secreto"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["api_version"] == "v1"
    assert payload["filtros"]["desde"] == "2026-08-13"
    assert payload["filtros"]["hasta"] == "2026-08-13"
    assert payload["paginacion"]["total"] == 1
    assert payload["datos"][0]["camion_codigo"] == "1100"
    assert response.headers["X-Total-Count"] == "1"
    assert captured == {
        "empresa_id": "1",
        "sucursal": "1",
        "desde": date(2026, 8, 13),
        "hasta": date(2026, 8, 13),
        "incluir_clientes": True,
        "limit": 50,
        "offset": 0,
    }


def test_logistica_diaria_valida_periodo_y_limite():
    client = _client()
    headers = {"X-API-Key": "secreto"}

    missing = client.get("/api/v1/integracion/logistica/diaria", headers=headers)
    too_long = client.get(
        "/api/v1/integracion/logistica/diaria"
        "?desde=2026-01-01&hasta=2026-02-01",
        headers=headers,
    )
    bad_limit = client.get(
        "/api/v1/integracion/logistica/diaria"
        "?fecha=2026-08-13&incluir_clientes=1&limit=201",
        headers=headers,
    )

    assert missing.status_code == 400
    assert missing.get_json()["codigo"] == "invalid_request"
    assert too_long.status_code == 400
    assert "31 días" in too_long.get_json()["error"]
    assert bad_limit.status_code == 400
    assert "entre 1 y 200" in bad_limit.get_json()["error"]


def test_logistica_diaria_exige_api_key_si_esta_configurada(monkeypatch):
    monkeypatch.setattr(route.svc, "get_logistica_diaria", lambda **_: {
        "total": 0,
        "fecha_min": None,
        "fecha_max": None,
        "datos": [],
    })
    client = _client("secreto")

    unauthorized = client.get(
        "/api/v1/integracion/logistica/diaria?fecha=2026-08-13"
    )
    authorized = client.get(
        "/api/v1/integracion/logistica/diaria?fecha=2026-08-13",
        headers={"X-API-Key": "secreto"},
    )

    assert unauthorized.status_code == 401
    assert unauthorized.get_json()["codigo"] == "unauthorized"
    assert authorized.status_code == 200


def test_logistica_diaria_no_se_habilita_sin_api_key():
    response = _client(None).get(
        "/api/v1/integracion/logistica/diaria?fecha=2026-08-13"
    )

    assert response.status_code == 503
    assert response.get_json()["codigo"] == "integration_not_configured"


class _Cursor:
    def __init__(self):
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.executions.append((sql, params))

    def fetchone(self):
        return {
            "total": 1,
            "fecha_min": date(2026, 8, 13),
            "fecha_max": date(2026, 8, 13),
        }

    def fetchall(self):
        return [{
            "fecha": date(2026, 8, 13),
            "empresa_id": "1",
            "sucursal_id": "1",
            "camion_codigo": "1100",
            "camion_descripcion": "Transporte ventas",
            "camion_descripcion_final": "IVECO TECTOR",
            "patente": "KTO613",
            "marca": "IVECO",
            "modelo": "2018",
            "carga_maxima_kg": Decimal("18000.00"),
            "capacidad_up": Decimal("700.00"),
            "camion_en_maestro_flota": True,
            "chofer_codigo": "15",
            "chofer_nombre": "Juan Pérez",
            "clientes": 2,
            "documentos": 3,
            "bultos": Decimal("520.50"),
            "hl": Decimal("48.76543"),
            "pallets_estimados": Decimal("6.34567"),
            "up": Decimal("680.00"),
            "lineas_origen": 10,
            "articulos_sin_configuracion_pallet": 1,
            "bultos_sin_conversion_pallet": Decimal("12.5"),
            "clientes_detalle": [
                {"id": "2", "nombre": "Zeta"},
                {"id": "1", "nombre": "Alfa"},
            ],
        }]


def test_servicio_normaliza_numeros_calidad_y_clientes(monkeypatch):
    cursor = _Cursor()
    monkeypatch.setattr(svc, "ensure_ventas_detalle_table", lambda: None)
    monkeypatch.setattr(svc, "ensure_articulos_table", lambda: None)
    monkeypatch.setattr(svc, "ensure_transportes_table", lambda: None)
    monkeypatch.setattr(svc, "ensure_flota_tables", lambda: None)
    monkeypatch.setattr(svc, "pg_cursor", lambda: cursor)
    monkeypatch.setattr(svc, "_sucursal_labels", lambda _: {"1": "Casa Central"})

    result = svc.get_logistica_diaria(
        empresa_id="1",
        sucursal="1",
        desde=date(2026, 8, 13),
        hasta=date(2026, 8, 13),
        incluir_clientes=True,
        limit=100,
        offset=0,
    )

    item = result["datos"][0]
    assert result["total"] == 1
    assert item["camion_descripcion"] == "IVECO TECTOR"
    assert item["bultos"] == 520.5
    assert item["hl"] == 48.7654
    assert item["pallets_estimados"] == 6.3457
    assert item["calidad"]["pallets_completos"] is False
    assert item["clientes_detalle"] == [
        {"id": "1", "nombre": "Alfa"},
        {"id": "2", "nombre": "Zeta"},
    ]
    assert len(cursor.executions) == 2
    assert "LOWER(TRIM(COALESCE(a.tipo_producto" in cursor.executions[0][0]
    assert "LEFT JOIN flota_vehiculos" in cursor.executions[1][0]
