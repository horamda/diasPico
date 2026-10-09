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


def test_control_frescura_agrupa_por_cancha_en_tabla_y_mobile():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert '<tr class="ubic-group-row"><td colspan="9">' in html
    assert "frescura-mobile-code" in html
    assert "function grupoUbicacion(r){return r.cancha||'Sin ubicación'}" in html
    assert "${esc(r.descripcion_articulo)}${ubicacionTag(r)}" in html


def test_conteo_agrupa_por_cancha_y_avisa_sin_ubicacion():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert '<tr class="ubic-group-row"><td colspan="18">' in html
    assert "${esc(r.descripcion)}${ubicacionTag(r)}" in html
    assert "avisoSinUbicacion(data.sin_ubicacion)" in html


def test_control_frescura_fecha_ok_no_ok_y_fecha_real():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert "<th>Articulo</th><th>Descripcion</th><th>Vencimiento esperado</th><th>Bultos contados</th><th>En pallets cerrados</th><th>Sueltos (bultos + unidades)</th><th>Unidades contadas</th>" in html
    assert "<th>¿Coincide la fecha?</th><th>Fecha real (si no coincide)</th>" in html
    assert "function frescuraFechaControlada(idx)" in html
    assert 'data-fr-ok="${idx}"' in html
    assert 'data-fr-real="${idx}"' in html
    assert "fecha_vencimiento:frescuraFechaControlada(idx)" in html


def test_control_frescura_responsive_conserva_carga_y_agrupa_cancha():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert 'class="frescura-mobile-toolbar"' in html
    assert 'id="frescuraMobileProgress"' in html
    assert "function actualizarCampoFrescura(idx,campo,valor,origen)" in html
    assert "row[`_control_${campo}`]=valor;" in html
    assert 'class="frescura-cancha-title"' in html
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in html


def test_control_frescura_separa_pallets_cerrados_y_sueltos_con_fecha_por_parte():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert "function splitPallets(bultos,capacidad)" in html
    assert "return !!sp&&sp.cerrados>0&&(sp.sueltos>0||Number(unidades)>0);" in html
    assert "splitCheckHtml(idx,r,'p')" in html and "splitCheckHtml(idx,r,'s')" in html
    assert "...(frSplitGrupos(idx)?{distribucion_fechas:frSplitGrupos(idx)}:{})," in html


def test_control_frescura_mobile_un_lote_por_pantalla_y_busquedas_acotadas():
    html = TEMPLATE.read_text(encoding="utf-8")

    # Un solo lote dibujado en mobile, con navegación y lista.
    assert "const r=frescuraRows[idx];" in html and "${frCardHtml(r,idx)}" in html
    assert 'aria-label="Lote anterior"' in html and 'aria-label="Lote siguiente"' in html
    assert "function frMobileNextPending()" in html and "function frAbrirListaLotes()" in html
    # Las búsquedas por lote no recorren toda la página en cada tecla.
    assert "function frQ(idx,selector)" in html
    assert "actualizarSplitFrescura(idx,cb??0,cu??0);" not in html
