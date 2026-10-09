from datetime import date

from app.services import portal_dashboard_svc as svc


def _dia(fecha, hl, bultos=None, pedidos=0, salidas=0):
    return {"fecha": fecha, "hectolitros": hl, "bultos": bultos if bultos is not None else hl * 10,
            "pedidos": pedidos, "camiones_salidos": salidas}


def test_ultimo_dia_con_datos_ignora_dias_futuros_y_vacios():
    dias = [_dia("2026-10-01", 100), _dia("2026-10-06", 80), _dia("2026-10-10", 0)]
    assert svc._ultimo_dia_con_datos(dias, date(2026, 10, 9)) == date(2026, 10, 6)
    assert svc._ultimo_dia_con_datos([_dia("2026-10-01", 0)], date(2026, 10, 9)) is None


def test_comparar_corta_ambos_anios_en_el_mismo_dia():
    actual = [_dia("2026-10-01", 100), _dia("2026-10-06", 80)]
    previo = [_dia("2025-10-01", 90), _dia("2025-10-06", 60), _dia("2025-10-07", 120), _dia("2025-10-20", 500)]

    data = svc._comparar(actual, previo, previo, date(2026, 10, 6), date(2025, 10, 6), date(2025, 10, 7))

    hl = data["metricas"][0]
    # Mes a la fecha: 180 contra 150 (no contra los 270 que daría cortar en el día de hoy).
    assert (hl["mtd"], hl["mtd_prev"], hl["mtd_delta_pct"]) == (180, 150, 20.0)
    # Último día contra el mismo día de la semana del año anterior.
    assert (hl["dia"], hl["dia_prev"], hl["dia_delta_pct"]) == (80, 120, -33.3)
    assert hl["mes_prev_total"] == 770
    assert data["dias_reparto"] == 2 and data["dias_reparto_prev"] == 2


def test_delta_pct_sin_base_devuelve_none():
    assert svc._delta_pct(10, 0) is None
    assert svc._delta_pct(None, 5) is None
