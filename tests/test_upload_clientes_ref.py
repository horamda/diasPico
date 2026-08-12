from datetime import datetime

from app.services import upload_svc
from app.utils.coerce import to_dec
from app.utils.col_maps import CLIENTES_MAP


def test_clientes_import_preserva_descripcion_ref():
    row = upload_svc._cli_row({"cliente": "10001", "descripcion": "REF"}, datetime(2026, 6, 2))

    assert CLIENTES_MAP["descripcion"][0] == "descripcion"
    assert upload_svc._CLI_COLS[:3] == ["cliente", "descripcion", "sucursal"]
    assert row[:3] == ("10001", "REF", "")


def test_to_dec_preserva_decimal_sin_cero_inicial():
    assert to_dec(".114") == 0.114
    assert to_dec(".005") == 0.005


def test_ventas_detalle_corrige_hl_parseado_como_entero_por_region():
    row = upload_svc._ventas_det_row(
        datetime(2026, 8, 4).date(),
        {
            "bultos": 10,
            "bultos_rechazados": 10,
            "unidad_medida": 1135,
            "unidad_medida_rechazado": 1135,
        },
        "1",
    )

    assert row[15] == 1.135
    assert row[16] == 1.135


def test_ventas_detalle_corrige_hl_parseado_como_entero_en_rechazo_mayor():
    row = upload_svc._ventas_det_row(
        datetime(2026, 8, 4).date(),
        {
            "bultos": 35,
            "bultos_rechazados": 35,
            "unidad_medida": 3973,
            "unidad_medida_rechazado": 3973,
        },
        "1",
    )

    assert row[15] == 3.973
    assert row[16] == 3.973
