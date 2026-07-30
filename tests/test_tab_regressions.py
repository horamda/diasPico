from pathlib import Path


TEMPLATE = Path("app/templates/panel_dias_pico_v3.html")
SCRIPT = Path("app/static/app.js")


def test_load_mes_define_anio_anterior_antes_del_banner_de_proyeccion():
    js = SCRIPT.read_text(encoding="utf-8")
    load_mes = js.split("async function loadMes()", 1)[1].split("function kpiMetricCard", 1)[0]
    definition = "const anioAnt = diasAnt[0]?.fecha_ant?.slice(0, 4)"
    usage = "${MESES[vM]} ${anioAnt}"
    assert definition in load_mes
    assert usage in load_mes
    assert load_mes.index(definition) < load_mes.index(usage)


def test_historico_tab_y_dropsize_usan_ids_consistentes():
    html = TEMPLATE.read_text(encoding="utf-8")
    js = SCRIPT.read_text(encoding="utf-8")

    assert 'onclick="switchTab(\'historico\',this)"' in html
    assert 'id="tab-historico"' in html
    assert 'onclick="switchTab(\'venta-anual\',this)"' in html
    assert 'id="tab-venta-anual"' in html
    assert 'id="ventaAnualSucursal"' in html
    assert 'id="ventaAnualPeriodo"' in html
    assert 'id="ventaAnualAnio"' in html
    assert 'id="ventaAnualAnioBase"' in html
    assert 'id="ventaAnualMes"' in html
    assert 'id="ventaAnualDesde"' in html
    assert 'id="ventaAnualHasta"' in html
    assert 'id="ventaAnualDivision"' in html
    assert 'id="ventaAnualUnidadNegocio"' in html
    assert 'onchange="onVentaAnualPeriodoChange()"' in html
    assert 'onchange="loadVentaAnual()"' in html
    assert "if (t === 'historico')   loadHistorico();" in js
    assert "if (t === 'venta-anual') loadVentaAnual();" in js
    assert 'initVentaAnualDefaults' in js
    assert 'syncVentaAnualPeriodoUI' in js
    assert 'onVentaAnualSucursalChange' in js
    assert 'onVentaAnualPeriodoChange' in js
    assert 'ventaAnualQueryParams' in js
    assert "renderVentaAnualChart" in js
    assert "ventaAnualChart" in js
    assert "dropRankingAgrupacion" in js
    assert "dropAgrupaciÃ³n" not in js
