from app.services import analisis_pedidos_svc as svc
from io import BytesIO

from openpyxl import load_workbook


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


def test_exportar_pedidos_genericos_completa_template():
    content = svc.exportar_pedidos_genericos_xlsx({
        "cliente": "100",
        "resultados": [
            {
                "solicitud": "9001",
                "entrega": "30/08/2026",
                "cliente": "CENCOSUD -   CALLE 3 389",
                "codigo": "19026",
                "cantidad_a_enviar": 5,
            },
            {
                "solicitud": "9001",
                "entrega": "30/08/2026",
                "cliente": "CENCOSUD -   CALLE 3 389",
                "codigo": "13502",
                "cantidad_a_enviar": 0,
            },
        ],
    })

    wb = load_workbook(BytesIO(content), data_only=True)
    assert wb.sheetnames == ["Pedidos", "Documentos"]
    ws = wb["Pedidos"]
    assert "A3:L3" in {str(rng) for rng in ws.merged_cells.ranges}
    assert ws["A4"].value == "Nro.Pedido"
    assert "Art" in str(ws["F4"].value)
    assert ws.column_dimensions["L"].width == 25
    assert ws["A6"].value == "9001"
    assert ws["C6"].value == "214"
    assert ws["D6"].value == "RMCYO"
    assert ws["F6"].value == "19026"
    assert ws["G6"].value == 5
    assert ws["K6"].value == 20
    assert ws["A7"].value is None
    wb.close()


def test_clientes_smk_por_defecto_normalizan_nombre():
    clientes = svc._default_clientes_smk_map()

    assert svc.resolver_cliente_smk("CENCOSUD -   CALLE 3 389", clientes) == "214"
    assert svc.resolver_cliente_smk("DIARCO -   RUTA NACIONAL Nø 2 KM", clientes) == "11603"
    assert svc.resolver_cliente_smk("1029", clientes) == "1029"


def test_recalcula_cumplimiento_con_cantidad_final():
    payload = svc._recalcular_resumen_resultados({
        "resumen": {},
        "resultados": [
            {"estado": svc.ENVIAR, "cantidad_pedida": 60, "cantidad_a_enviar": 40},
            {"estado": svc.NO_ENVIAR, "cantidad_pedida": 40, "cantidad_a_enviar": 30, "envio_forzado": True},
        ],
    })

    assert payload["resumen"]["bultos_pedidos"] == 100
    assert payload["resumen"]["bultos_a_enviar"] == 70
    assert payload["resumen"]["cumplimiento_pct"] == 70
    assert payload["resumen"]["objetivo_cumplido"] is True
