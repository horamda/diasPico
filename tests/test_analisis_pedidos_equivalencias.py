from app.services import analisis_pedidos_svc as svc


def test_resuelve_equivalencia_solo_si_codigo_no_esta_en_punto_pedido():
    lineas = [
        {"codigo": "24683", "cantidad_pedida": 5},
        {"codigo": "24878", "cantidad_pedida": 2},
    ]
    pp_index = {
        "19026": {"stock": 10},
        "24878": {"stock": 8},
    }

    resolved = svc._resolver_equivalencias_faltantes(
        lineas,
        pp_index,
        {"24683": "19026", "24878": "13502"},
    )

    assert resolved[0]["codigo"] == "19026"
    assert resolved[0]["codigo_original"] == "24683"
    assert resolved[0]["codigo_equivalente_usado"] is True
    assert resolved[1]["codigo"] == "24878"
    assert resolved[1]["codigo_original"] == "24878"
    assert resolved[1]["codigo_equivalente_usado"] is False


def test_equivalencias_por_defecto_incluyen_tabla_smk():
    equivalencias = svc._default_equivalencias_map()

    assert equivalencias["24683"] == "19026"
    assert equivalencias["46668"] == "31557"
    assert equivalencias["56250"] == "24882"
