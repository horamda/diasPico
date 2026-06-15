from pathlib import Path


TEMPLATE = Path("app/templates/panel_dias_pico_v3.html")
SCRIPT = Path("app/static/app.js")


def test_historico_tab_y_dropsize_usan_ids_consistentes():
    html = TEMPLATE.read_text(encoding="utf-8")
    js = SCRIPT.read_text(encoding="utf-8")

    assert 'onclick="switchTab(\'historico\',this)"' in html
    assert 'id="tab-historico"' in html
    assert "if (t === 'historico')   loadHistorico();" in js
    assert "dropRankingAgrupacion" in js
    assert "dropAgrupación" not in js
