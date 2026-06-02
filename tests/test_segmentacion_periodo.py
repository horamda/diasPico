from datetime import date

import pytest

from app.services.segmentacion_svc import build_periodo_payload


def test_periodo_default_ytd_vs_anio_anterior():
    periodo = build_periodo_payload(today=date(2026, 5, 25))

    assert periodo["periodo_anio"] == 2026
    assert periodo["periodo_mes"] == 0
    assert periodo["fecha_desde"] == date(2026, 1, 1)
    assert periodo["fecha_hasta"] == date(2026, 5, 25)
    assert periodo["fecha_base_desde"] == date(2025, 1, 1)
    assert periodo["fecha_base_hasta"] == date(2025, 5, 25)


def test_periodo_mensual_usa_fin_de_mes():
    periodo = build_periodo_payload(
        {"periodo_anio": 2026, "periodo_mes": 2},
        today=date(2026, 5, 25),
    )

    assert periodo["fecha_desde"] == date(2026, 1, 1)
    assert periodo["fecha_hasta"] == date(2026, 2, 28)
    assert periodo["fecha_base_desde"] == date(2025, 1, 1)
    assert periodo["fecha_base_hasta"] == date(2025, 2, 28)


def test_periodo_explicito_respeta_fechas_base():
    periodo = build_periodo_payload({
        "periodo_anio": 2026,
        "periodo_mes": 5,
        "fecha_desde": "2026-03-01",
        "fecha_hasta": "2026-05-15",
        "fecha_base_desde": "2025-03-01",
        "fecha_base_hasta": "2025-05-15",
    })

    assert periodo["fecha_desde"] == date(2026, 3, 1)
    assert periodo["fecha_hasta"] == date(2026, 5, 15)
    assert periodo["fecha_base_desde"] == date(2025, 3, 1)
    assert periodo["fecha_base_hasta"] == date(2025, 5, 15)


def test_periodo_con_fecha_fin_corrige_mes_snapshot():
    periodo = build_periodo_payload({
        "periodo_anio": 2026,
        "periodo_mes": 4,
        "fecha_desde": "2026-01-01",
        "fecha_hasta": "2026-05-31",
    })

    assert periodo["periodo_anio"] == 2026
    assert periodo["periodo_mes"] == 5
    assert periodo["fecha_hasta"] == date(2026, 5, 31)


def test_periodo_rechaza_mes_invalido():
    with pytest.raises(ValueError, match="periodo_mes"):
        build_periodo_payload({"periodo_mes": 13})
