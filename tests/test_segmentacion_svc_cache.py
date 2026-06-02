import inspect

from app.services import segmentacion_svc as svc


class _Cursor:
    def __init__(self, row=None):
        self.row = row or {}
        self.sql = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self, *_, **__):
        return self._cursor


def test_get_cliente_detalle_prefiere_seg_cliente_dpo_cache(monkeypatch):
    cursor = _Cursor({"cliente": "10001", "cluster_dpo": "Ganador"})
    monkeypatch.setattr(svc, "ensure_tables", lambda: None)
    monkeypatch.setattr(svc, "_dpo_cache_has_rows", lambda: True)
    monkeypatch.setattr(svc, "pg_cursor", lambda: cursor)

    row = svc.get_cliente_detalle("10001")

    assert row["cliente"] == "10001"
    assert "seg_cliente_dpo_cache" in cursor.sql
    assert cursor.params == {"c": "10001"}


def test_recalcular_clusters_lee_snapshot_desde_cache_dpo():
    source = inspect.getsource(svc.recalcular_clusters)

    assert "FROM seg_cliente_dpo_cache" in source
    assert "FROM mv_cliente_plan_servicio" not in source
    assert "otif_valor" in source


def test_refresh_segmentacion_cache_usa_cache_rapida_y_recalcula_score():
    source = inspect.getsource(svc.refresh_segmentacion_cache)
    legacy_source = inspect.getsource(svc._refresh_segmentacion_cache_legacy)

    assert "_refresh_segmentacion_cache_legacy" in source
    assert "INSERT INTO seg_cliente_dpo_cache" in legacy_source
    assert "_update_dpo_cache_scores" in legacy_source
    assert "otif_valor" in svc._DPO_CACHE_COLUMNS


def test_update_dpo_cache_scores_actualiza_dimensiones():
    source = inspect.getsource(svc._update_dpo_cache_scores)

    assert "UPDATE seg_cliente_dpo_cache" in source
    assert "score_total = calc.score_total" in source
    assert "pts_rechazos = calc.pts_rechazos" in source


def test_bulk_upsert_atributos_incluye_otif_y_preserva_campos(monkeypatch):
    calls = []
    cursor = _Cursor()

    def fake_execute_values(cur, sql, values, page_size=100):
        calls.append((sql, list(values), page_size))

    monkeypatch.setattr(svc, "ensure_tables", lambda: None)
    monkeypatch.setattr(svc, "pg_conn", lambda: _Connection(cursor))
    monkeypatch.setattr(svc.psycopg2.extras, "execute_values", fake_execute_values)

    result = svc.bulk_upsert_atributos([
        {"cliente": "10001", "otif_valor": 96.5, "otif_fecha": "2026-05-31"},
    ])

    assert result == 1
    sql, values, _ = calls[0]
    assert "otif_valor" in sql
    assert "COALESCE(EXCLUDED.otif_valor" in sql
    assert values[0][8:10] == (96.5, "2026-05-31")


def test_bulk_upsert_promotores_actualiza_atributos_y_maestro(monkeypatch):
    calls = []
    cursor = _Cursor()

    def fake_execute_values(cur, sql, values, page_size=100):
        calls.append((sql, list(values), page_size))

    monkeypatch.setattr(svc, "ensure_tables", lambda: None)
    monkeypatch.setattr(svc, "pg_conn", lambda: _Connection(cursor))
    monkeypatch.setattr(svc.psycopg2.extras, "execute_values", fake_execute_values)

    result = svc.bulk_upsert_promotores([
        {"cliente": "10001", "promotor": "Juan Perez"},
        {"cliente": "10055", "promotor": "Mayoristas"},
    ])

    assert result == {"actualizados": 2, "activos": 1, "inactivos": 1}
    assert len(calls) == 2
    assert "seg_clientes_atributos" in calls[0][0]
    assert "UPDATE clientes AS c" in calls[1][0]
    assert calls[0][1][0][:3] == ("10001", "Juan Perez", True)
    assert calls[0][1][1][:3] == ("10055", "Mayoristas", False)
