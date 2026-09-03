from pathlib import Path


TEMPLATE = Path("app/templates/control_stock.html")


def test_control_frescura_tiene_vista_mobile_de_lotes():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert 'id="frescuraControlCards"' in html
    assert "function renderFrescuraMobileCards()" in html
    assert "#viewFrescura>.table-wrap{display:none!important}" in html
    assert "#viewFrescura>.table-wrap:last-of-type{display:block!important" in html
    assert "if(frescuraRows.length) renderFrescuraMobileCards();" in html


def test_control_frescura_mobile_usa_inputs_visibles_para_guardar():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert "function frescuraInput(selector)" in html
    assert 'document.querySelector(`#frescuraControlCards ${selector}`)' in html
    assert 'document.querySelector(`#frescuraControlBody ${selector}`)' in html
    assert "const b=frescuraInput(`[data-fr-b=\"${idx}\"]`)?.value ?? '';" in html
    assert "stock_contado_bultos:frescuraInput(`[data-fr-b=\"${idx}\"]`)?.value ?? ''," in html


def test_control_frescura_muestra_calibre_en_tabla_y_mobile():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert "<th>Calibre</th><th>Articulo</th>" in html
    assert "${esc(r.calibre_label||'Sin calibre')} · ${esc(r.codigo_articulo)}" in html
