import io

import openpyxl
import pytest

from app.services import ubicaciones_svc


HEADER = ("Deposito", "Almacen", "Articulo", "Descripcion de articulo", "Orden", "Ubicación", "NombreCancha")


def _xlsx(rows, header=HEADER) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_excel_lee_columnas_con_acentos_y_omite_filas_vacias():
    data = _xlsx([
        (1, 14, 7038, "BRAHMA X12", 3, None, "Cancha2"),
        (None, None, None, None, None, None, None),
        ("2", "91", "32423", "GATORADE", "111", "P1-A", "CanchaMKP"),
    ])

    rows = ubicaciones_svc.parse_excel(data)

    assert [(r["sucursal"], r["id_almacen"], r["id_articulo"], r["orden"], r["cancha"]) for r in rows] == [
        ("1", 14, 7038, 3, "Cancha2"),
        ("2", 91, 32423, 111, "CanchaMKP"),
    ]
    assert rows[0]["ubicacion"] is None
    assert rows[1]["ubicacion"] == "P1-A"


def test_parse_excel_informa_columnas_faltantes():
    data = _xlsx([(1, 14, 7038)], header=("Deposito", "Almacen", "Articulo"))

    with pytest.raises(ValueError, match="orden, cancha"):
        ubicaciones_svc.parse_excel(data)


def test_parse_excel_informa_fila_con_numero_invalido():
    data = _xlsx([(1, "X", 7038, "BRAHMA", 1, None, "Cancha1")])

    with pytest.raises(ValueError, match="Fila 2: Almacen"):
        ubicaciones_svc.parse_excel(data)


def test_importar_rechaza_articulo_repetido_en_el_mismo_deposito(monkeypatch):
    monkeypatch.setattr(ubicaciones_svc, "ensure_ubicaciones_table", lambda: None)
    data = _xlsx([
        (1, 1, 7038, "BRAHMA", 1, None, "Cancha1"),
        (1, 2, 7038, "BRAHMA", 5, None, "Cancha3"),
        (2, 1, 7038, "BRAHMA", 1, None, "Cancha1"),
    ])

    with pytest.raises(ValueError, match="dep 1 art 7038"):
        ubicaciones_svc.importar_excel(data)


def test_ordenar_por_recorrido_sigue_cancha_almacen_orden_y_deja_sin_ubicacion_al_final(monkeypatch):
    mapa = {
        10: {"id_almacen": 14, "cancha": "Cancha2", "orden_cancha": 2, "orden_almacen": 3, "orden": 1, "ubicacion": None},
        20: {"id_almacen": 1, "cancha": "Cancha1", "orden_cancha": 1, "orden_almacen": 1, "orden": 7, "ubicacion": "R1"},
        30: {"id_almacen": 93, "cancha": "Cancha1", "orden_cancha": 1, "orden_almacen": 2, "orden": 1, "ubicacion": None},
    }
    monkeypatch.setattr(ubicaciones_svc, "get_mapa", lambda sucursal: mapa)
    rows = [
        {"codigo_articulo": "99", "lote": "A"},
        {"codigo_articulo": "10", "lote": "B"},
        {"codigo_articulo": "30", "lote": "C"},
        {"codigo_articulo": "20", "lote": "D2"},
        {"codigo_articulo": "20", "lote": "D1"},
    ]

    result = ubicaciones_svc.ordenar_por_recorrido(rows, "1", id_key="codigo_articulo")

    assert [r["lote"] for r in result] == ["D2", "D1", "C", "B", "A"]
    assert result[0]["ubicacion_label"] == "Cancha1 · Alm 1 · #7 · R1"
    assert result[-1]["con_ubicacion"] is False
    assert result[-1]["ubicacion_label"] == "Sin ubicación"
    assert all("_ruta" not in r for r in result)
