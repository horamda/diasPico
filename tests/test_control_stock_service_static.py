from pathlib import Path


SERVICE = Path("app/services/control_stock_svc.py")


def test_frescura_planilla_agrupa_por_calibre():
    source = SERVICE.read_text(encoding="utf-8")

    assert "def _calibre_label" in source
    assert "AS calibre_ml" in source
    assert "ORDER BY calibre_ml NULLS LAST" in source
    assert '"calibre_label": _calibre_label(calibre_ml)' in source
