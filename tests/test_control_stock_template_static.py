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

    assert 'class="frescura-calibre-row"' in html
    assert 'colspan="7"' in html
    assert "frescura-mobile-code" in html
    assert "r.calibre_label||'Sin calibre'" in html


def test_control_frescura_fecha_ok_no_ok_y_fecha_real():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert "<th>Articulo</th><th>Descripcion</th><th>fecvtolote</th><th>Bultos</th><th>Unids</th>" in html
    assert "<th>fecha OK / No OK</th><th>fecha real</th>" in html
    assert "function frescuraFechaControlada(idx)" in html
    assert 'data-fr-ok="${idx}"' in html
    assert 'data-fr-real="${idx}"' in html
    assert "fecha_vencimiento:frescuraFechaControlada(idx)" in html


def test_control_frescura_responsive_conserva_carga_y_agrupa_calibre():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert 'class="frescura-mobile-toolbar"' in html
    assert 'id="frescuraMobileProgress"' in html
    assert "function actualizarCampoFrescura(idx,campo,valor,origen)" in html
    assert "row[`_control_${campo}`]=valor;" in html
    assert 'class="frescura-calibre-title"' in html
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in html
