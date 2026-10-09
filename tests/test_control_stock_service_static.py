from pathlib import Path


SERVICE = Path("app/services/control_stock_svc.py")


def test_frescura_planilla_agrupa_por_calibre():
    source = SERVICE.read_text(encoding="utf-8")

    assert "def _calibre_label" in source
    assert "AS calibre_ml" in source
    assert "ORDER BY calibre_ml NULLS LAST" in source
    assert '"calibre_label": _calibre_label(calibre_ml)' in source


def test_planillas_se_ordenan_por_recorrido_del_deposito():
    source = SERVICE.read_text(encoding="utf-8")

    assert 'rows = ubicaciones_svc.ordenar_por_recorrido(rows, data["sucursal"])' in source
    assert 'rows = ubicaciones_svc.ordenar_por_recorrido(rows, suc, id_key="codigo_articulo")' in source
    assert "selected = ubicaciones_svc.ordenar_por_recorrido(selected, suc)" in source
    assert "def get_articulos_sin_ubicacion" in source
