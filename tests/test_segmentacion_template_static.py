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
    query_block = html.split("function queryString()", 1)[1].split("async function loadData()", 1)[0]

    assert "scheduleLoadData" not in cluster_block
    assert "loadData" not in sort_block
    assert 'params.set("cluster"' not in query_block


def test_segmentacion_filtros_globales_aplican_localmente():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert "function passesGlobalFilters(row)" in html
    assert "let rows = [...state.clusters].filter(passesGlobalFilters);" in html
    assert "let rows = filteredPlanRows();" in html
    assert "passesGlobalFilters(row) && Number(row.latitud)" in html
