from pathlib import Path


TEMPLATE = Path("app/templates/segmentacion_clientes.html")


def test_segmentacion_selectores_usen_change_y_recarga_antigua_no_pise_estado():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert 'on("branchFilter", "change"' in html
    assert 'on("clusterFilter", "change"' in html
    assert 'on("sortFilter", "change"' in html
    assert 'on("searchInput", "input"' in html
    assert "state.loadSeq += 1;" in html
    assert "if (seq !== state.loadSeq) return;" in html


def test_segmentacion_cluster_y_orden_no_reemplazan_dataset_base():
    html = TEMPLATE.read_text(encoding="utf-8")

    cluster_block = html.split('on("clusterFilter", "change"', 1)[1].split('});', 1)[0]
    sort_block = html.split('on("sortFilter", "change"', 1)[1].split('});', 1)[0]
    query_block = html.split("function queryString", 1)[1].split("async function loadData()", 1)[0]

    assert "scheduleLoadData" not in cluster_block
    assert "loadData" not in sort_block
    assert 'params.set("cluster"' not in query_block


def test_segmentacion_filtros_globales_aplican_localmente():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert "function passesGlobalFilters(row)" in html
    assert "let rows = [...state.clusters].filter(passesGlobalFilters);" in html
    assert "let rows = filteredPlanRows();" in html
    assert "passesGlobalFilters(row) && Number(row.latitud)" in html


def test_segmentacion_solapa_costo_pdv_conectada_a_reporte():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert 'data-tab="cost-pdv"' in html
    assert 'id="view-cost-pdv"' in html
    assert "function renderCostPdv()" in html
    assert '"cost-pdv": "Actualizando costo por PDV..."' in html
    assert "p75_costo_pdv" in html
    assert "costo_entrega_reportado" in html
    assert "Segmentacion costo" in html
    assert "segmentacion_costo_pdv" in html
    assert "Canal" in html
    assert "Pedidos GM" in html
    assert "Bultos totales" in html
    assert "Precio/bulto" in html
    assert "Fact. total" in html
    assert "Costo dist./bulto" in html
    assert "Rent. entrega" in html
    assert 'id="costPdvPeriodBtn"' in html
    assert 'id="costPdvHistoryBtn"' in html
    assert 'id="costPdvExportXlsx"' in html
    assert "costReportParams(5000, true)" in html
    assert "updateCostPdvExportLink" in html
    assert "costReportSignature" in html
    assert 'state.costReportSignature = "";' in html
    assert 'state.sectionSignatures["cost-pdv"] = signature;' in html


def test_segmentacion_solapas_responsivas():
    html = TEMPLATE.read_text(encoding="utf-8")

    tabs_block = html.split(".tabs {", 1)[1].split("}", 1)[0]
    mobile_block = html.split("@media (max-width: 720px)", 1)[1]

    assert "flex-wrap: wrap;" in tabs_block
    assert "overflow-x: visible;" in tabs_block
    assert ".tabs { flex-wrap: nowrap; overflow-x: auto;" in mobile_block


def test_segmentacion_cartera_clientes_paginada_y_sin_corte_fijo():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert "const FULL_PLAN_LIMIT = 50000;" in html
    assert "const CLIENT_PAGE_SIZE = 500;" in html
    assert 'id="clientsPrevPage"' in html
    assert 'id="clientsNextPage"' in html
    assert 'id="clientsPageMeta"' in html
    clients_block = html.split("function renderClients()", 1)[1].split("function renderTerritory()", 1)[0]
    assert "const pageRows = rows.slice(start, end);" in html
    assert "pageRows.map" in clients_block
    assert "rows.slice(0, 500).map" not in clients_block
    assert "resetClientPage()" in html
    assert "Pallets" in html
    assert "Ticket" in html


def test_segmentacion_tablas_contenido_responsivo():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert "width: max-content;" in html
    assert "scrollbar-gutter: stable;" in html
    assert ".table-wrap th:first-child" in html
    assert ".table-wrap td:first-child" in html
    assert "white-space: normal;" in html.split(".cell-sub {", 1)[1].split("}", 1)[0]
    assert ".reason-cell" in html
    assert ".action-cell" in html
    assert ".comment-cell" in html
    assert 'class="reason-cell"' in html
    assert 'class="action-cell"' in html
    assert 'class="comment-cell"' in html
    assert "white-space:normal;min-width" not in html
