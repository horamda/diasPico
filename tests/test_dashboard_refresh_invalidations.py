from flask import Flask

import app.routes.flota as flota
import app.routes.parametros as parametros
import app.routes.picos as picos
import app.routes.planificacion_picos as planificacion
import app.routes.sync_sheets as sync_sheets
import app.services.pico_svc as pico_svc


def _client_for(bp):
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(bp)
    return app.test_client()


def test_parametros_invalida_picos_y_portal(monkeypatch):
    cleared = []
    monkeypatch.setattr(parametros.pico_svc, "save_params", lambda *_: None)
    monkeypatch.setattr(parametros.cache_svc, "clear", cleared.append)

    res = _client_for(parametros.bp).post(
        "/api/parametros",
        json={"sucursal": "1", "umbral_pct": 1.25, "metrica": "hectolitros"},
    )

    assert res.status_code == 200
    assert cleared == ["picos:", "portal:"]


def test_periodos_criticos_invalidan_picos_y_portal(monkeypatch):
    cleared = []
    monkeypatch.setattr(picos.pico_svc, "guardar_periodo_critico", lambda data: {"id": 7, **data})
    monkeypatch.setattr(picos.pico_svc, "eliminar_periodo_critico", lambda periodo_id: None)
    monkeypatch.setattr(picos.cache_svc, "clear", cleared.append)

    client = _client_for(picos.bp)
    post_res = client.post(
        "/api/picos/periodos-criticos",
        json={"nombre": "Pico test", "fecha_inicio": "2026-05-01", "fecha_fin": "2026-05-02"},
    )
    delete_res = client.delete("/api/picos/periodos-criticos/7")

    assert post_res.status_code == 201
    assert delete_res.status_code == 200
    assert cleared == ["picos:", "portal:", "picos:", "portal:"]


def test_planificacion_configuracion_invalida_resumen_cache(monkeypatch):
    cleared = []
    monkeypatch.setattr(
        planificacion.svc.repo,
        "guardar_configuracion",
        lambda data: {"ok": True, **data},
    )
    monkeypatch.setattr(planificacion.cache_svc, "clear", cleared.append)

    res = _client_for(planificacion.bp).post(
        "/api/planificacion_picos/configuracion",
        json={"empresa_id": "1", "sucursal_id": "1", "umbral_pico_hl_pct": 25},
    )

    assert res.status_code == 200
    assert cleared == ["planificacion_picos:"]


def test_flota_disponibilidad_invalida_planificacion(monkeypatch):
    cleared = []
    monkeypatch.setattr(flota.svc, "guardar_disponibilidad", lambda data: {"ok": True, **data})
    monkeypatch.setattr(flota.cache_svc, "clear", cleared.append)

    res = _client_for(flota.bp).post(
        "/api/flota/disponibilidad",
        json={"vehiculo_id": 3, "anio": 2026, "mes": 5, "activo": False},
    )

    assert res.status_code == 200
    assert cleared == ["planificacion_picos:"]


def test_sync_operativo_invalida_tableros_dependientes(monkeypatch):
    cleared = []
    monkeypatch.setattr(sync_sheets.svc, "sync_operacion_camiones", lambda empresa_id: {"insertados": 10})
    monkeypatch.setattr(sync_sheets.cache_svc, "clear", cleared.append)

    res = _client_for(sync_sheets.bp).post("/api/sync/sheets-operativo", json={"empresa_id": "1"})

    assert res.status_code == 200
    assert cleared == ["picos:", "portal:", "planificacion_picos:"]


class _Cursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params or {}))

    def fetchall(self):
        return []


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def test_comparativo_anual_usa_metrica_y_umbral_configurados(monkeypatch):
    cursor = _Cursor()
    monkeypatch.setattr(pico_svc, "ensure_ventas_detalle_table", lambda: None)
    monkeypatch.setattr(pico_svc, "ensure_articulos_table", lambda: None)
    monkeypatch.setattr(pico_svc, "ensure_rechazos_table", lambda: None)
    monkeypatch.setattr(pico_svc, "get_params", lambda sucursal: {"umbral_pct": 1.35, "metrica": "clientes"})
    monkeypatch.setattr(pico_svc, "pg_cursor", lambda: _CursorContext(cursor))
    monkeypatch.setattr(
        pico_svc,
        "get_dotacion_mensual",
        lambda *_: {"meses": [{"mes": m, 2026: {}, 2025: {}} for m in range(1, 13)]},
    )
    monkeypatch.setattr(
        pico_svc,
        "get_ausentismo_mensual",
        lambda *_: [{"mes": m, "pct_ausentismo": None} for m in range(1, 13)],
    )

    pico_svc.get_comparativo_anual("1", 2026, 2025)

    picos_sql, picos_params = cursor.calls[1]
    assert "COUNT(DISTINCT" in picos_sql
    assert "metrica_dia >= m.avg_metrica * %(umbral)s" in picos_sql
    assert "avg_b * 1.20" not in picos_sql
    assert picos_params["umbral"] == 1.35
