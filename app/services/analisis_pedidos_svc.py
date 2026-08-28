"""
Servicio: Análisis de pedidos de supermercado (SMK).

Cruza un pedido cargado por el usuario (export de la consola, detalle por SKU)
contra el punto de pedido (stock + venta) y, opcionalmente, contra la frescura
de los artículos, para determinar si cada línea del pedido se puede despachar
al supermercado sin dejar sin cobertura a la venta a minoristas.

Reglas de decisión (por SKU del pedido):
  1. Sin stock (stock <= 0)                    -> NO_ENVIAR
  2. Frescura por debajo del mínimo de días    -> NO_ENVIAR
  3. Enviar dejaría menos de N días de stock
     para la venta a minoristas                -> NO_ENVIAR / ENVIAR_PARCIAL
  4. En caso contrario                          -> ENVIAR

El punto de pedido informa STOCK y VTA. CALCULADA (venta diaria sensibilizada).
La cantidad máxima que puedo despachar dejando `dias_min_retail` días de
cobertura es:  max(0, stock - dias_min_retail * venta_diaria).
"""

from __future__ import annotations

import math
import unicodedata
from io import BytesIO
from typing import Any

import openpyxl

# --- Parámetros por defecto (configurables desde la UI) --------------------

DIAS_MIN_RETAIL_DEFAULT = 3          # días de cobertura a preservar para minoristas
UMBRAL_FRESCURA_DIAS_DEFAULT = 60    # vida útil mínima (días) exigida por el super

# --- Etiquetas de estado ---------------------------------------------------

ENVIAR = "ENVIAR"
ENVIAR_PARCIAL = "ENVIAR_PARCIAL"
NO_ENVIAR = "NO_ENVIAR"
REVISAR = "REVISAR"          # el SKU del pedido no está en el punto de pedido


# ---------------------------------------------------------------------------
# Utilidades de normalización
# ---------------------------------------------------------------------------

def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _norm_header(value: Any) -> str:
    """Normaliza un encabezado: sin acentos, mayúsculas, sin puntuación extra."""
    if value is None:
        return ""
    text = _strip_accents(str(value)).upper().strip()
    for ch in (".", ":", "¿", "?", "!", "¡"):
        text = text.replace(ch, " ")
    return " ".join(text.split())


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        try:
            f = float(value)
            return f if not math.isnan(f) else default
        except (ValueError, OverflowError):
            return default
    text = str(value).strip().replace(" ", "")
    if not text:
        return default
    # Formatos "1.234,56" o "1234.56"
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return default


def _to_codigo(value: Any) -> str:
    """Normaliza un código de artículo a string comparable (sin .0 de floats)."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    return str(value).strip()


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return None


# ---------------------------------------------------------------------------
# Lectura de planillas
# ---------------------------------------------------------------------------

def _load_sheet_rows(
    content: bytes,
    *,
    preferred_sheet: str | None = None,
    header_keywords: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    """
    Devuelve una lista de dicts {ENCABEZADO_NORMALIZADO: valor}.
    Detecta la fila de encabezado buscando `header_keywords` (si se pasan);
    si no, usa la primera fila no vacía.
    """
    wb = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    try:
        ws = None
        if preferred_sheet and preferred_sheet in wb.sheetnames:
            ws = wb[preferred_sheet]
        else:
            # Elegir la hoja con más filas (evita hojas 'Instructivo').
            ws = max(wb.worksheets, key=lambda s: (s.max_row or 0))

        raw = list(ws.iter_rows(values_only=True))
        if not raw:
            return []

        header_idx = 0
        if header_keywords:
            for i, r in enumerate(raw[:15]):
                normed = {_norm_header(c) for c in r if c is not None}
                if any(any(kw in cell for cell in normed) for kw in header_keywords):
                    header_idx = i
                    break

        header = [_norm_header(c) for c in raw[header_idx]]
        rows: list[dict[str, str]] = []
        for r in raw[header_idx + 1:]:
            if r is None or all(c is None or str(c).strip() == "" for c in r):
                continue
            row = {}
            for h, v in zip(header, r):
                if h:
                    row[h] = v
            if row:
                rows.append(row)
        return rows
    finally:
        wb.close()


def parse_pedido(content: bytes) -> dict[str, Any]:
    """
    Parsea el pedido del super (export consola, detalle por SKU).
    Espera columnas del estilo: SolicitudId, Cliente, Entrega,
    ProductoCodigo, ProductoDescripcion, CantidadEntregada.
    """
    rows = _load_sheet_rows(content, header_keywords=("PRODUCTOCODIGO", "CANTIDADENTREGADA"))
    lineas: list[dict[str, Any]] = []
    clientes: set[str] = set()
    solicitudes: set[str] = set()
    entregas: set[str] = set()

    for row in rows:
        codigo = _to_codigo(_first_present(row, "PRODUCTOCODIGO", "ARTICULO", "CODIGO", "PRODUCTO CODIGO"))
        if not codigo:
            continue
        cantidad = _to_float(_first_present(
            row, "CANTIDADENTREGADA", "CANTIDAD ENTREGADA", "CANTIDAD", "CANT", "BULTOS",
        ))
        descripcion = _first_present(row, "PRODUCTODESCRIPCION", "DESCRIPCION", "PRODUCTO DESCRIPCION") or ""
        cliente = _first_present(row, "CLIENTE") or ""
        solicitud = _to_codigo(_first_present(row, "SOLICITUDID", "SOLICITUD", "PEDIDO", "NUMERO"))
        entrega = _first_present(row, "ENTREGA", "FECHA ENTREGA") or ""

        if cliente:
            clientes.add(str(cliente).strip())
        if solicitud:
            solicitudes.add(solicitud)
        if entrega:
            entregas.add(str(entrega).strip())

        lineas.append({
            "codigo": codigo,
            "descripcion": str(descripcion).strip(),
            "cantidad_pedida": cantidad,
            "cliente": str(cliente).strip(),
            "solicitud": solicitud,
            "entrega": str(entrega).strip(),
        })

    # Consolidar líneas repetidas del mismo SKU (suma cantidades).
    consolidado: dict[str, dict[str, Any]] = {}
    for ln in lineas:
        key = ln["codigo"]
        if key not in consolidado:
            consolidado[key] = dict(ln)
        else:
            consolidado[key]["cantidad_pedida"] += ln["cantidad_pedida"]

    return {
        "lineas": list(consolidado.values()),
        "clientes": sorted(clientes),
        "solicitudes": sorted(solicitudes),
        "entregas": sorted(entregas),
    }


def parse_punto_pedido(content: bytes) -> dict[str, dict[str, Any]]:
    """
    Parsea el punto de pedido. Devuelve un índice {codigo: {stock, venta, ...}}.
    """
    rows = _load_sheet_rows(
        content,
        preferred_sheet="Reporte",
        header_keywords=("ARTICULO", "STOCK", "VTA PROMEDIO"),
    )
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        codigo = _to_codigo(_first_present(row, "ARTICULO", "ARTICULO COMPANIA", "CODIGO"))
        if not codigo:
            continue
        stock = _to_float(_first_present(row, "STOCK"))
        vta_prom = _to_float(_first_present(row, "VTA PROMEDIO", "VENTA PROMEDIO"))
        vta_calc = _to_float(_first_present(row, "VTA CALCULADA", "VENTA CALCULADA"))
        venta_diaria = vta_calc if vta_calc > 0 else vta_prom
        index[codigo] = {
            "descripcion": str(_first_present(row, "DESCRIPCION") or "").strip(),
            "stock": stock,
            "venta_promedio": vta_prom,
            "venta_calculada": vta_calc,
            "venta_diaria": venta_diaria,
            "dias_stock": _to_float(_first_present(row, "DIAS DE STOCK")),
            "politica": _to_float(_first_present(row, "POLITICA")),
            "bultos_x_pallet": _to_float(_first_present(row, "BULTOS X PALLETS", "BULTOS X PALLET")),
        }
    return index


# ---------------------------------------------------------------------------
# Frescura (opcional, desde la tabla frescura_articulos si hay DB)
# ---------------------------------------------------------------------------

def cargar_frescura(codigos: list[str], sucursal_id: str | None = None) -> dict[str, dict[str, Any]]:
    """
    Devuelve {codigo: {dias_frescura, estado_frescura}} tomando el peor lote
    (menor cantidad de días restantes) por código. Si no hay DB o falla, {}.
    """
    if not codigos:
        return {}
    try:
        from app.database import pg_conn
    except Exception:
        return {}
    try:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                params: dict[str, Any] = {"codigos": list({str(c) for c in codigos})}
                filtro_suc = ""
                if sucursal_id:
                    filtro_suc = "AND sucursal_id = %(suc)s"
                    params["suc"] = str(sucursal_id)
                cur.execute(
                    f"""
                    SELECT codigo_articulo,
                           MIN(dias_frescura_restantes) AS dias
                    FROM frescura_articulos
                    WHERE codigo_articulo = ANY(%(codigos)s)
                      {filtro_suc}
                    GROUP BY codigo_articulo
                    """,
                    params,
                )
                out: dict[str, dict[str, Any]] = {}
                for codigo, dias in cur.fetchall():
                    out[_to_codigo(codigo)] = {"dias_frescura": None if dias is None else int(dias)}
                return out
    except Exception:
        # La frescura es un enriquecimiento opcional: nunca romper el análisis.
        return {}


# ---------------------------------------------------------------------------
# Núcleo de análisis
# ---------------------------------------------------------------------------

def _analizar_linea(
    linea: dict[str, Any],
    pp: dict[str, Any] | None,
    fr: dict[str, Any] | None,
    *,
    dias_min_retail: float,
    umbral_frescura_dias: float,
) -> dict[str, Any]:
    codigo = linea["codigo"]
    cantidad_pedida = float(linea["cantidad_pedida"] or 0)
    descripcion = linea.get("descripcion") or (pp or {}).get("descripcion") or ""

    if pp is None:
        return {
            "codigo": codigo,
            "descripcion": descripcion,
            "cantidad_pedida": cantidad_pedida,
            "stock": None,
            "venta_diaria": None,
            "dias_stock_actual": None,
            "dias_stock_post": None,
            "dias_frescura": (fr or {}).get("dias_frescura"),
            "cantidad_a_enviar": 0.0,
            "estado": REVISAR,
            "motivos": ["SKU no encontrado en el punto de pedido: revisar manualmente."],
        }

    stock = float(pp.get("stock") or 0)
    venta_diaria = float(pp.get("venta_diaria") or 0)
    dias_frescura = (fr or {}).get("dias_frescura")

    # Cobertura actual y máximo despachable dejando `dias_min_retail` días.
    dias_stock_actual = (stock / venta_diaria) if venta_diaria > 0 else None
    if venta_diaria > 0:
        max_enviable = max(0.0, stock - dias_min_retail * venta_diaria)
    else:
        # Sin venta diaria no hay riesgo de quiebre para minoristas.
        max_enviable = stock
    max_enviable = math.floor(max_enviable)

    motivos: list[str] = []
    estado = ENVIAR
    cantidad_a_enviar = cantidad_pedida

    # Regla 1: sin stock.
    if stock <= 0:
        estado = NO_ENVIAR
        cantidad_a_enviar = 0.0
        motivos.append("Sin stock disponible en depósito.")

    # Regla 2: frescura por debajo del mínimo.
    frescura_rechaza = (
        dias_frescura is not None and dias_frescura < umbral_frescura_dias
    )
    if frescura_rechaza:
        estado = NO_ENVIAR
        cantidad_a_enviar = 0.0
        motivos.append(
            f"Frescura insuficiente: {dias_frescura} días < mínimo {int(umbral_frescura_dias)} días."
        )

    # Regla 3: preservar cobertura para la venta a minoristas.
    if estado != NO_ENVIAR:
        if cantidad_pedida > max_enviable:
            if max_enviable <= 0:
                estado = NO_ENVIAR
                cantidad_a_enviar = 0.0
                motivos.append(
                    f"Enviar dejaría menos de {int(dias_min_retail)} días de stock para minoristas."
                )
            else:
                estado = ENVIAR_PARCIAL
                cantidad_a_enviar = float(max_enviable)
                motivos.append(
                    f"Se puede enviar hasta {int(max_enviable)} (de {int(cantidad_pedida)}) "
                    f"para preservar {int(dias_min_retail)} días de cobertura minorista."
                )
        else:
            motivos.append("OK: hay stock y cobertura suficientes.")

    stock_post = stock - cantidad_a_enviar
    dias_stock_post = (stock_post / venta_diaria) if venta_diaria > 0 else None

    return {
        "codigo": codigo,
        "descripcion": descripcion,
        "cantidad_pedida": cantidad_pedida,
        "stock": stock,
        "venta_diaria": round(venta_diaria, 2),
        "dias_stock_actual": None if dias_stock_actual is None else round(dias_stock_actual, 1),
        "dias_stock_post": None if dias_stock_post is None else round(dias_stock_post, 1),
        "dias_frescura": dias_frescura,
        "max_enviable": float(max_enviable),
        "cantidad_a_enviar": cantidad_a_enviar,
        "estado": estado,
        "motivos": motivos,
    }


def analizar(
    pedido_bytes: bytes,
    punto_pedido_bytes: bytes,
    *,
    dias_min_retail: float = DIAS_MIN_RETAIL_DEFAULT,
    umbral_frescura_dias: float = UMBRAL_FRESCURA_DIAS_DEFAULT,
    usar_frescura: bool = True,
    sucursal_id: str | None = None,
) -> dict[str, Any]:
    """
    Ejecuta el análisis completo y devuelve resultados + resumen.
    """
    pedido = parse_pedido(pedido_bytes)
    pp_index = parse_punto_pedido(punto_pedido_bytes)

    lineas = pedido["lineas"]
    frescura_index: dict[str, dict[str, Any]] = {}
    if usar_frescura:
        frescura_index = cargar_frescura([ln["codigo"] for ln in lineas], sucursal_id)

    resultados = [
        _analizar_linea(
            ln,
            pp_index.get(ln["codigo"]),
            frescura_index.get(ln["codigo"]),
            dias_min_retail=dias_min_retail,
            umbral_frescura_dias=umbral_frescura_dias,
        )
        for ln in lineas
    ]

    # Orden: primero lo que requiere atención.
    orden = {NO_ENVIAR: 0, ENVIAR_PARCIAL: 1, REVISAR: 2, ENVIAR: 3}
    resultados.sort(key=lambda r: (orden.get(r["estado"], 9), -(r["cantidad_pedida"] or 0)))

    resumen = {
        "total_skus": len(resultados),
        "enviar": sum(1 for r in resultados if r["estado"] == ENVIAR),
        "enviar_parcial": sum(1 for r in resultados if r["estado"] == ENVIAR_PARCIAL),
        "no_enviar": sum(1 for r in resultados if r["estado"] == NO_ENVIAR),
        "revisar": sum(1 for r in resultados if r["estado"] == REVISAR),
        "bultos_pedidos": round(sum(r["cantidad_pedida"] or 0 for r in resultados), 2),
        "bultos_a_enviar": round(sum(r["cantidad_a_enviar"] or 0 for r in resultados), 2),
        "frescura_aplicada": bool(frescura_index),
    }
    # Veredicto global del pedido.
    if resumen["no_enviar"] == 0 and resumen["revisar"] == 0 and resumen["enviar_parcial"] == 0:
        veredicto = "PEDIDO_COMPLETO"
    elif resumen["enviar"] == 0 and resumen["enviar_parcial"] == 0:
        veredicto = "PEDIDO_RECHAZADO"
    else:
        veredicto = "PEDIDO_PARCIAL"

    return {
        "ok": True,
        "veredicto": veredicto,
        "cliente": ", ".join(pedido["clientes"]) if pedido["clientes"] else "",
        "solicitudes": pedido["solicitudes"],
        "entregas": pedido["entregas"],
        "parametros": {
            "dias_min_retail": dias_min_retail,
            "umbral_frescura_dias": umbral_frescura_dias,
            "usar_frescura": usar_frescura,
        },
        "resumen": resumen,
        "resultados": resultados,
    }


# ---------------------------------------------------------------------------
# Exportación a Excel
# ---------------------------------------------------------------------------

def exportar_xlsx(analisis: dict[str, Any]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()
    ws = wb.active
    ws.title = "Análisis pedido"

    colores = {
        ENVIAR: "C6EFCE",
        ENVIAR_PARCIAL: "FFEB9C",
        NO_ENVIAR: "FFC7CE",
        REVISAR: "D9D9D9",
    }

    # Encabezado de contexto
    ws["A1"] = "Análisis de pedido a supermercado"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Cliente: {analisis.get('cliente', '')}"
    ws["A3"] = f"Solicitud(es): {', '.join(analisis.get('solicitudes', []))}"
    ws["A4"] = f"Veredicto: {analisis.get('veredicto', '')}"
    p = analisis.get("parametros", {})
    ws["A5"] = (
        f"Días mín. minoristas: {p.get('dias_min_retail')} · "
        f"Frescura mín.: {p.get('umbral_frescura_dias')} días · "
        f"Frescura aplicada: {'sí' if analisis.get('resumen', {}).get('frescura_aplicada') else 'no'}"
    )

    headers = [
        "Código", "Descripción", "Cant. pedida", "Stock", "Venta diaria",
        "Días stock actual", "Días stock post", "Frescura (días)",
        "Cant. a enviar", "Estado", "Motivos",
    ]
    header_row = 7
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=header_row, column=col, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="305496")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for i, r in enumerate(analisis.get("resultados", []), start=header_row + 1):
        ws.cell(row=i, column=1, value=r["codigo"])
        ws.cell(row=i, column=2, value=r["descripcion"])
        ws.cell(row=i, column=3, value=r["cantidad_pedida"])
        ws.cell(row=i, column=4, value=r["stock"])
        ws.cell(row=i, column=5, value=r["venta_diaria"])
        ws.cell(row=i, column=6, value=r["dias_stock_actual"])
        ws.cell(row=i, column=7, value=r["dias_stock_post"])
        ws.cell(row=i, column=8, value=r["dias_frescura"])
        ws.cell(row=i, column=9, value=r["cantidad_a_enviar"])
        estado_cell = ws.cell(row=i, column=10, value=r["estado"])
        estado_cell.fill = PatternFill("solid", fgColor=colores.get(r["estado"], "FFFFFF"))
        estado_cell.font = Font(bold=True)
        ws.cell(row=i, column=11, value=" ".join(r["motivos"]))

    anchos = [12, 34, 12, 10, 12, 14, 14, 13, 13, 16, 60]
    for col, w in enumerate(anchos, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = w
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    out = BytesIO()
    wb.save(out)
    return out.getvalue()
