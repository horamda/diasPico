from datetime import datetime

from app.services import upload_svc
from app.utils.col_maps import CLIENTES_MAP


def test_clientes_import_preserva_descripcion_ref():
    row = upload_svc._cli_row({"cliente": "10001", "descripcion": "REF"}, datetime(2026, 6, 2))

    assert CLIENTES_MAP["descripcion"][0] == "descripcion"
    assert upload_svc._CLI_COLS[:3] == ["cliente", "descripcion", "sucursal"]
    assert row[:3] == ("10001", "REF", "")
