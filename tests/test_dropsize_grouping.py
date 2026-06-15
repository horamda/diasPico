from datetime import date

from app.services import dropsize_svc as svc


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return self.rows


def test_ranking_por_segmento_usa_nombre_descriptivo(monkeypatch):
    cursor = _Cursor(
        [
            {
                "grupo_id": "KIOSCOS",
                "clientes_entregados": 3,
                "total_bultos": 30,
                "total_hl": 12,
                "total_pallets": 1,
            }
        ]
    )

    monkeypatch.setattr(svc, "ensure_dropsize_tables", lambda ensure_source=True: None)
    monkeypatch.setattr(svc, "pg_cursor", lambda: cursor)

    result = svc.get_ranking_sucursales(
        fecha_desde="2026-01-01",
        fecha_hasta="2026-01-31",
        unidad="bultos",
        agrupacion="segmento",
    )

    assert result["agrupacion"] == "segmento"
    assert result["agrupacion_label"] == "Segmento"
    assert result["ranking"][0]["grupo_id"] == "KIOSCOS"
    assert result["ranking"][0]["entregas_consolidadas"] == 3
    assert "canal_raw AS" in cursor.sql
    assert "canal_descripcion" in cursor.sql
    assert "LEFT JOIN clientes cli" in cursor.sql
    assert "LEFT JOIN canales ch" in cursor.sql
    assert "COUNT(DISTINCT" in cursor.sql


def test_ranking_por_localidad_usa_localidad(monkeypatch):
    cursor = _Cursor(
        [
            {
                "grupo_id": "Mar del Plata",
                "clientes_entregados": 5,
                "total_bultos": 80,
                "total_hl": 25,
                "total_pallets": 4,
            }
        ]
    )

    monkeypatch.setattr(svc, "ensure_dropsize_tables", lambda ensure_source=True: None)
    monkeypatch.setattr(svc, "pg_cursor", lambda: cursor)

    result = svc.get_ranking_sucursales(
        fecha_desde="2026-01-01",
        fecha_hasta="2026-01-31",
        unidad="hl",
        agrupacion="localidad",
    )

    assert result["agrupacion"] == "localidad"
    assert result["agrupacion_label"] == "Localidad"
    assert result["ranking"][0]["grupo_id"] == "Mar del Plata"
    assert "cli.localidad" in cursor.sql
    assert "LEFT JOIN clientes cli" in cursor.sql


def test_comparativo_usa_mismo_rango_de_dias(monkeypatch):
    cursor = _Cursor(
        [
            {
                "periodo": "actual",
                "clientes_entregados": 10,
                "total_bultos": 100,
                "total_hl": 50,
                "total_pallets": 5,
            },
            {
                "periodo": "previo",
                "clientes_entregados": 8,
                "total_bultos": 80,
                "total_hl": 40,
                "total_pallets": 4,
            },
            {
                "periodo": "anio_anterior",
                "clientes_entregados": 7,
                "total_bultos": 70,
                "total_hl": 35,
                "total_pallets": 3,
            },
        ]
    )

    monkeypatch.setattr(svc, "ensure_dropsize_tables", lambda ensure_source=True: None)
    monkeypatch.setattr(svc, "pg_cursor", lambda: cursor)

    result = svc.get_comparativo(
        "TODAS",
        fecha_desde="2026-06-01",
        fecha_hasta="2026-06-30",
    )

    assert result["periodo_actual"] == {
        "fecha_desde": "2026-06-01",
        "fecha_hasta": "2026-06-30",
        "dias": 30,
    }
    assert cursor.params["ini"] == date(2026, 6, 1)
    assert cursor.params["fin"] == date(2026, 6, 30)
    assert cursor.params["prev_ini"] == date(2026, 5, 2)
    assert cursor.params["prev_fin"] == date(2026, 5, 31)
    assert cursor.params["aa_ini"] == date(2025, 6, 1)
    assert cursor.params["aa_fin"] == date(2025, 6, 30)
