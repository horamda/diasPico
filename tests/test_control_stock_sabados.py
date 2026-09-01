from app.services import control_stock_svc as svc


def _row(article_id, abc="C", semanas=None):
    item = {
        "id_articulo": article_id,
        "descripcion": f"Articulo {article_id}",
        "abc": abc,
        "participa": "SI",
        "logistica_incompleta": False,
        "semana1": "",
        "semana2": "",
        "semana3": "",
        "semana4": "",
        "dia_semana1": "",
        "dia_semana2": "",
        "dia_semana3": "",
        "dia_semana4": "",
    }
    for semana, dia in (semanas or {}).items():
        item[semana] = semana.upper()
        item[f"dia_{semana}"] = dia
    return item


def test_planilla_sabado_incluye_articulos_fijos_en_cualquier_semana(monkeypatch):
    monkeypatch.setattr(
        svc,
        "get_abc_articulos",
        lambda mes=None, sucursal="1": {
            "ok": True,
            "mes": "2026-08",
            "sucursal": sucursal,
            "sucursal_nombre": "Casa Central",
            "rows": [
                _row(2776, semanas={"semana3": "Miercoles"}),
                _row(2731, semanas={"semana1": "Lunes"}),
                _row(2777, semanas={"semana4": "Viernes"}),
                _row(9999, semanas={"semana2": "Sabado"}),
            ],
        },
    )
    monkeypatch.setattr(
        svc,
        "_get_saturday_fixed_rows",
        lambda sucursal="1": [
            _row(2776, abc="ACT", semanas={"semana1": "Sabado", "semana2": "Sabado", "semana3": "Sabado", "semana4": "Sabado"}),
            _row(2731, abc="ACT", semanas={"semana1": "Sabado", "semana2": "Sabado", "semana3": "Sabado", "semana4": "Sabado"}),
            _row(2777, abc="ACT", semanas={"semana1": "Sabado", "semana2": "Sabado", "semana3": "Sabado", "semana4": "Sabado"}),
        ],
    )

    data = svc.get_planilla(mes="2026-08", semana="semana2", dia="Sabado", sucursal="2")

    assert [row["id_articulo"] for row in data["rows"]] == [2776, 2731, 2777]
    assert {row["control_semana"] for row in data["rows"]} == {"SEMANA2"}
    assert {row["control_dia"] for row in data["rows"]} == {"Sabado"}


def test_planificacion_suma_tres_articulos_fijos_cada_sabado(monkeypatch):
    monkeypatch.setattr(
        svc,
        "get_abc_articulos",
        lambda mes=None, sucursal="1": {
            "ok": True,
            "mes": "2026-08",
            "sucursal": sucursal,
            "sucursal_nombre": "Dolores",
            "rows": [
                _row(2776, abc="A", semanas={"semana1": "Lunes"}),
                _row(2731, abc="B", semanas={"semana2": "Martes"}),
                _row(2777, abc="C", semanas={"semana3": "Miercoles"}),
                _row(9999, abc="C", semanas={"semana4": "Jueves"}),
            ],
        },
    )
    monkeypatch.setattr(svc, "_get_saturday_fixed_rows", lambda sucursal="1": [])

    data = svc.get_planificacion(mes="2026-08", sucursal="2")

    assert data["por_semana_dia"]["SEMANA1"]["Sabado"] == 3
    assert data["por_semana_dia"]["SEMANA2"]["Sabado"] == 3
    assert data["por_semana_dia"]["SEMANA3"]["Sabado"] == 3
    assert data["por_semana_dia"]["SEMANA4"]["Sabado"] == 3
    assert data["totales_dia"]["Sabado"] == 12


def test_planificacion_agrega_activos_de_sabado_fuera_del_abc(monkeypatch):
    monkeypatch.setattr(
        svc,
        "get_abc_articulos",
        lambda mes=None, sucursal="1": {
            "ok": True,
            "mes": "2026-08",
            "sucursal": sucursal,
            "sucursal_nombre": "Casa Central",
            "rows": [
                _row(1001, abc="A", semanas={"semana1": "Lunes", "semana2": "Martes", "semana3": "Miercoles", "semana4": "Jueves"}),
            ],
        },
    )
    monkeypatch.setattr(
        svc,
        "_get_saturday_fixed_rows",
        lambda sucursal="1": [
            _row(2776, abc="ACT", semanas={"semana1": "Sabado", "semana2": "Sabado", "semana3": "Sabado", "semana4": "Sabado"}),
            _row(2731, abc="ACT", semanas={"semana1": "Sabado", "semana2": "Sabado", "semana3": "Sabado", "semana4": "Sabado"}),
            _row(2777, abc="ACT", semanas={"semana1": "Sabado", "semana2": "Sabado", "semana3": "Sabado", "semana4": "Sabado"}),
        ],
    )

    data = svc.get_planificacion(mes="2026-08", sucursal="1")

    assert data["por_semana_dia"]["SEMANA1"]["Sabado"] == 3
    assert data["por_semana_dia"]["SEMANA2"]["Sabado"] == 3
    assert data["por_semana_dia"]["SEMANA3"]["Sabado"] == 3
    assert data["por_semana_dia"]["SEMANA4"]["Sabado"] == 3
    assert data["total_controles"] == 16
