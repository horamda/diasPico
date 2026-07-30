from pathlib import Path


TEMPLATE = Path("app/templates/panel_dias_pico_v3.html")
SCRIPT = Path("app/static/app.js")


def test_kpi_tab_tiene_layout_compacto_y_bandas_por_unidad():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert 'class="kpi-grid kpi-grid-stack"' in html
    assert '#tab-kpis .kpi-group-body{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;align-items:start;}' in html
    assert '#tab-kpis .kpi-band-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px;}' in html
    assert '#tab-kpis .kpi{padding:6px 7px;min-height:50px;border-radius:6px;}' in html
    assert '#tab-kpis .kpi-lbl{font-size:7px;line-height:1.05;min-height:15px;margin-bottom:2px;letter-spacing:.2px;}' in html
    assert '#tab-kpis .kpi-goal{margin-top:3px;display:flex;justify-content:center;}' in html
    assert "Experiencia de clientes" in html
    assert "Detalle diario del mes" in html
    assert 'id="rechazoPctCharts"' in html
    assert 'id="rechazoPdvChart"' in html
    assert 'id="rechazoBultosChart"' in html
    assert 'id="rechazoHlChart"' in html
    assert "Períodos críticos — R3.4.1" in html
    assert "Distribución por sucursal" in html
    assert "Pestañas principales" in html
    assert "Planificación de picos" in html
    assert "Año del plan" in html
    assert "Mes del plan" in html
    assert "Generar plan" in html
    assert "Recalcular plan" in html
    assert "dropRankingAgrupacion" in html
    assert "Ranking por sucursal / segmento" in html


def test_kpi_tab_render_agrupa_positivo_y_rechazo_por_unidad():
    js = SCRIPT.read_text(encoding="utf-8")

    assert "function kpiMetricCard(" in js
    assert "function kpiBand(" in js
    assert "function kpiGroup(" in js
    assert "Bultos rechazados" in js
    assert "Bultos con rechazo parcial" in js
    assert "HL con rechazo completo" in js
    assert "kpiBand('Positivos', 'good'" in js
    assert "kpiBand('Rechazos', 'bad'" in js
    assert "spanAll = false" in js
    assert "span-all" in js
    assert "kpi-group-body" in js
    assert "kpiGroup('Operación'" in js
    assert "PDV únicos" in js
    assert "Salidas de camiones" in js
    assert "Período:" in js
    assert "Métrica:" in js
    assert "Histórico recalculado" in js
    assert "Períodos críticos" in js
    assert "Recalculando histórico" in js
    assert "Días pico del plan" in js
    assert "Generar plan" in js
    assert "rmcyo_pct_rechazo_bultos" in js
    assert "rmcyo_pct_rechazo_pedidos" in js
    assert "function renderRechazoPctCharts()" in js
    assert "pct_rechazo_pedidos" in js
    assert "pct_rechazo_bultos" in js
    assert "pct_rechazo_hl" in js
