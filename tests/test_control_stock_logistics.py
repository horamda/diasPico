import pytest

from app.services import control_stock_svc, upload_svc


@pytest.mark.parametrize('values,expected', [
    ({'bultos_por_pallet': 100, 'pisos': 5}, (5, 20)),
    ({'bultos_por_pallet': 100, 'bultos_por_piso': 20}, (5, 20)),
    ({'bultos_por_pallet': 100}, (0, 0)),
])
def test_complete_only_when_enough_information(values, expected):
    result = control_stock_svc._complete_logistics(values)
    assert (result['pisos'], result['bultos_por_piso']) == expected
    assert result['logistica_incompleta'] == (expected == (0, 0))


def imported(values, old):
    row = upload_svc._art_row({'id_articulo': 123, **values})
    return dict(zip(upload_svc._ART_COLS, upload_svc._preserve_article_logistics(row, old)))


def test_reimport_preserves_missing_manual_logistics():
    row = imported({'bultos_por_pallet': 100}, {'pisos': 5, 'bultos_por_piso': 20, 'unidades_por_bulto': 6})
    assert row['pisos'] == 5
    assert row['bultos_por_piso'] == 20
    assert row['unidades_por_bulto'] == 6


def test_explicit_positive_values_replace_previous_values():
    row = imported({'bultos_por_pallet': 120, 'pisos': 6, 'bultos_por_piso': 20}, {'pisos': 5, 'bultos_por_piso': 24})
    assert row['pisos'] == 6
    assert row['bultos_por_piso'] == 20


def test_single_known_value_does_not_invent_floors():
    row = imported({'bultos_por_pallet': 315}, {})
    assert row['pisos'] is None
    assert row['bultos_por_piso'] is None


def test_reimport_uses_preserved_floors_to_complete_layer():
    row = imported({'bultos_por_pallet': 100}, {'pisos': 5})
    assert row['bultos_por_piso'] == 20


def test_excel_logistics_report_with_alternative_headers():
    from io import BytesIO
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.title = 'Art\u00edculos'
    wb.active.append(['Reporte de articulos'])
    wb.active.append(['Art\u00edculo', 'Descripcion', 'Bultos por pallet', 'Pisos por pallet'])
    wb.active.append([123, 'Producto', 120, 6])
    output = BytesIO()
    wb.save(output)
    rows = upload_svc._parse_articulos_excel(output.getvalue())
    assert len(rows) == 1
    result = dict(zip(upload_svc._ART_FALTANTES_COLS, upload_svc._art_faltantes_row(rows[0])))
    assert result['pisos'] == 6
    assert result['bultos_por_piso'] == 20
    assert upload_svc._article_logistics_diagnostics(rows)['advertencias'] == []


def test_import_warns_when_source_has_no_logistics():
    result = upload_svc._article_logistics_diagnostics([{'id_articulo': 123, 'bultos_por_pallet': 315}])
    assert result['columnas_logisticas_no_detectadas'] == ['pisos', 'bultos_por_piso']
    assert result['filas_con_pisos_o_bultos_por_piso'] == 0
    assert result['advertencias']


def test_import_warns_when_columns_exist_but_are_empty():
    result = upload_svc._article_logistics_diagnostics([{'id_articulo': 123, 'pisos': '', 'bultos_por_piso': 0}])
    assert result['columnas_logisticas_no_detectadas'] == []
    assert result['advertencias']


def test_complementary_import_derives_floors_from_layer():
    row = upload_svc._art_faltantes_row({'id_articulo': 123, 'bultos_por_pallet': 120, 'bultos_por_piso': 20})
    assert dict(zip(upload_svc._ART_FALTANTES_COLS, row))['pisos'] == 6
