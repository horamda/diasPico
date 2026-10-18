from datetime import datetime

from app.services import upload_svc
from app.utils.coerce import to_dec
from app.utils.col_maps import CLIENTES_MAP


def test_clientes_import_preserva_descripcion_ref():
    row = upload_svc._cli_row({"cliente": "10001", "descripcion": "REF"}, datetime(2026, 6, 2))

    assert CLIENTES_MAP["descripcion"][0] == "descripcion"
    assert upload_svc._CLI_COLS[:3] == ["cliente", "descripcion", "sucursal"]
    assert row[:3] == ("10001", "REF", "")


def test_to_dec_preserva_decimal_sin_cero_inicial():
    assert to_dec(".114") == 0.114
    assert to_dec(".005") == 0.005


def test_ventas_detalle_corrige_hl_parseado_como_entero_por_region():
    row = upload_svc._ventas_det_row(
        datetime(2026, 8, 4).date(),
        {
            "bultos": 10,
            "bultos_rechazados": 10,
            "unidad_medida": 1135,
            "unidad_medida_rechazado": 1135,
        },
        "1",
    )

    assert row[15] == 1.135
    assert row[16] == 1.135


def test_ventas_detalle_corrige_hl_parseado_como_entero_en_rechazo_mayor():
    row = upload_svc._ventas_det_row(
        datetime(2026, 8, 4).date(),
        {
            "bultos": 35,
            "bultos_rechazados": 35,
            "unidad_medida": 3973,
            "unidad_medida_rechazado": 3973,
        },
        "1",
    )

    assert row[15] == 3.973
    assert row[16] == 3.973


def test_importa_vendedor_asignado_separado_de_dias_visita():
    from app.utils.col_maps import map_headers
    headers = ['Cliente', 'Fuerza de venta 1 descripcion personal comercial', 'Dias de visita']
    mapped = map_headers(headers, CLIENTES_MAP)
    campo = 'fuerza_venta_1_descripcion_personal_comercial'
    assert mapped[campo] == 1
    row = upload_svc._cli_row({'cliente':'100', campo:' Ana ', 'fuerza_venta_1_dias_visita':'MAR,VIE'}, datetime(2026, 6, 2))
    assert len(row) == len(upload_svc._CLI_COLS)
    values = dict(zip(upload_svc._CLI_COLS, row))
    assert values[campo] == 'Ana'
    assert values['fuerza_venta_1_dias_visita'] == 'MAR,VIE'


def test_clientes_conserva_columnas_desconocidas_y_valores_originales():
    raw = 'Cliente;Programa nuevo;Codigo futuro;Comentario\n001;SI;0007;' + ('x' * 400) + '\n'
    parsed = upload_svc._parse_clientes_csv(raw.encode())
    row = dict(zip(upload_svc._CLI_COLS, upload_svc._cli_row(parsed[0], datetime(2026,10,18))))
    assert row['cliente'] == '001'
    assert row['datos_csv'].adapted == {'Cliente':'001', 'Programa nuevo':'SI', 'Codigo futuro':'0007', 'Comentario':'x'*400}
    assert len(row['comentario']) == 255
    assert upload_svc._analyze_clientes_rows(parsed)['columnas_csv_conservadas'] == 4


def test_clientes_rechaza_archivo_ambiguo_antes_de_cargar():
    import pytest
    for raw in ['Cliente;X\n1;a\n1;b', 'Cliente;X\n;a', 'Cliente;X\n1',
                'Cliente;X\n1;a;b', 'Cliente;X;X\n1;a;b', 'Cliente;\n1;a']:
        with pytest.raises(ValueError):
            upload_svc._parse_clientes_csv(raw.encode())
