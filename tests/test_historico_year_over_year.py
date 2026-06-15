from pathlib import Path


TEMPLATE = Path("app/templates/panel_dias_pico_v3.html")
SCRIPT = Path("app/static/app.js")


def test_historico_tiene_comparacion_mensual_ano_vs_ano():
    html = TEMPLATE.read_text(encoding="utf-8")
    js = SCRIPT.read_text(encoding="utf-8")

    assert "Volumen mes a mes año vs año" in html
    assert 'id="volumenAnualMeta"' in html
    assert 'id="volumenAnualHistorico"' in html
    assert "loadHistoricoVolumenAnual" in js
    assert "renderHistoricoVolumenAnualChart" in js
    assert "historicoVolumenChart" in js
    assert "await loadHistoricoVolumenAnual(seq, suc, m, u, meses);" in js
