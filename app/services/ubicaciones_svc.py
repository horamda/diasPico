"""Ubicación física de los artículos en el depósito (orden de canchas).

El recorrido de un depósito es cancha → almacén → orden. El orden de canchas y
almacenes sale del orden de aparición en el Excel importado (OrdenCanchas),
porque la columna Orden se reinicia en cada almacén.
"""
from __future__ import annotations

import io
import re
import unicodedata
from threading import Lock

import openpyxl
from psycopg2.extras import execute_values

from app.database import pg_conn, pg_cursor


_READY = False
_LOCK = Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS stock_ubicaciones (
    sucursal VARCHAR(20) NOT NULL,
    id_articulo INTEGER NOT NULL,
    descripcion VARCHAR(255),
    id_almacen INTEGER NOT NULL,
    cancha VARCHAR(60) NOT NULL,
    orden_cancha INTEGER NOT NULL,
    orden_almacen INTEGER NOT NULL,
    orden INTEGER NOT NULL,
    ubicacion VARCHAR(100),
    origen VARCHAR(20) NOT NULL DEFAULT 'excel',
    actualizado_por VARCHAR(120),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (sucursal, id_articulo)
);
CREATE INDEX IF NOT EXISTS idx_stock_ubicaciones_recorrido
    ON stock_ubicaciones(sucursal, orden_cancha, orden_almacen, orden);
"""

_HEADERS = {
    "deposito": "deposito",
    "sucursal": "deposito",
    "almacen": "almacen",
    "articulo": "articulo",
    "codigoarticulo": "articulo",
    "descripciondearticulo": "descripcion",
    "descripcion": "descripcion",
    "orden": "orden",
    "ubicacion": "ubicacion",
    "nombrecancha": "cancha",
    "cancha": "cancha",
}
_REQUIRED = ("deposito", "almacen", "articulo", "orden", "cancha")
_SIN_UBICACION_KEY = (1, 0, 0, 0)


def ensure_ubicaciones_table() -> None:
    global _READY
    if _READY:
        return
    with _LOCK:
        if _READY:
            return
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA)
        _READY = True


def _norm_header(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]", "", text.lower())
    if text.startswith("ubicaci"):
        return "ubicacion"
    return text


def _to_int(value, campo: str, fila: int) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        raise ValueError(f"Fila {fila}: {campo} '{value}' no es un número") from None


def _sucursal(value) -> str:
    text = str(value or "").strip()
    try:
        return str(int(float(text)))
    except ValueError:
        return text


def parse_excel(file_bytes: bytes) -> list[dict]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    try:
        ws = wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None) or ()
        cols = {}
        for idx, name in enumerate(header):
            key = _HEADERS.get(_norm_header(name))
            if key and key not in cols:
                cols[key] = idx
        faltan = [c for c in _REQUIRED if c not in cols]
        if faltan:
            raise ValueError("Faltan columnas en el Excel: " + ", ".join(faltan))

        def cell(row, key):
            idx = cols.get(key)
            return row[idx] if idx is not None and idx < len(row) else None

        parsed = []
        for fila, row in enumerate(rows, start=2):
            if not row or all(v in (None, "") for v in row):
                continue
            ubicacion = cell(row, "ubicacion")
            parsed.append({
                "sucursal": _sucursal(cell(row, "deposito")),
                "id_almacen": _to_int(cell(row, "almacen"), "Almacen", fila),
                "id_articulo": _to_int(cell(row, "articulo"), "Articulo", fila),
                "descripcion": str(cell(row, "descripcion") or "").strip()[:255],
                "orden": _to_int(cell(row, "orden"), "Orden", fila),
                "ubicacion": str(ubicacion).strip()[:100] if ubicacion not in (None, "") else None,
                "cancha": str(cell(row, "cancha") or "").strip()[:60],
                "fila": fila,
            })
    finally:
        wb.close()
    if not parsed:
        raise ValueError("El Excel no tiene filas de datos")
    return parsed


def importar_excel(file_bytes: bytes, usuario: str = "") -> dict:
    """Reemplaza el layout de cada sucursal incluida en el archivo.

    Las filas cargadas a mano (origen='manual') de artículos que no figuran en
    el Excel se conservan; si el Excel trae el artículo, el Excel manda.
    """
    ensure_ubicaciones_table()
    rows = parse_excel(file_bytes)

    vistos: dict[tuple[str, int], int] = {}
    duplicados = []
    for row in rows:
        if not row["sucursal"] or not row["cancha"]:
            raise ValueError(f"Fila {row['fila']}: faltan Deposito o NombreCancha")
        key = (row["sucursal"], row["id_articulo"])
        if key in vistos:
            duplicados.append(f"dep {key[0]} art {key[1]} (filas {vistos[key]} y {row['fila']})")
        vistos[key] = row["fila"]
    if duplicados:
        raise ValueError("Artículos repetidos en el mismo depósito: " + "; ".join(duplicados[:10]))

    # Orden de recorrido por orden de aparición dentro de cada sucursal.
    canchas: dict[str, dict[str, int]] = {}
    almacenes: dict[str, dict[int, int]] = {}
    for row in rows:
        suc = row["sucursal"]
        c_map = canchas.setdefault(suc, {})
        a_map = almacenes.setdefault(suc, {})
        c_map.setdefault(row["cancha"], len(c_map) + 1)
        a_map.setdefault(row["id_almacen"], len(a_map) + 1)
        row["orden_cancha"] = c_map[row["cancha"]]
        row["orden_almacen"] = a_map[row["id_almacen"]]

    sucursales = sorted(canchas)
    ids = sorted({row["id_articulo"] for row in rows})
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id_articulo FROM articulos WHERE id_articulo = ANY(%s)", (ids,))
            en_maestro = {int(r[0]) for r in cur.fetchall()}

            eliminados = 0
            for suc in sucursales:
                suc_ids = [r["id_articulo"] for r in rows if r["sucursal"] == suc]
                cur.execute(
                    """DELETE FROM stock_ubicaciones
                       WHERE sucursal = %s AND origen = 'excel' AND NOT (id_articulo = ANY(%s))""",
                    (suc, suc_ids),
                )
                eliminados += cur.rowcount
            execute_values(
                cur,
                """
                INSERT INTO stock_ubicaciones (
                    sucursal, id_articulo, descripcion, id_almacen, cancha, orden_cancha,
                    orden_almacen, orden, ubicacion, origen, actualizado_por, updated_at
                ) VALUES %s
                ON CONFLICT (sucursal, id_articulo) DO UPDATE SET
                    descripcion = EXCLUDED.descripcion,
                    id_almacen = EXCLUDED.id_almacen,
                    cancha = EXCLUDED.cancha,
                    orden_cancha = EXCLUDED.orden_cancha,
                    orden_almacen = EXCLUDED.orden_almacen,
                    orden = EXCLUDED.orden,
                    ubicacion = EXCLUDED.ubicacion,
                    origen = 'excel',
                    actualizado_por = EXCLUDED.actualizado_por,
                    updated_at = NOW()
                """,
                [
                    (r["sucursal"], r["id_articulo"], r["descripcion"], r["id_almacen"], r["cancha"],
                     r["orden_cancha"], r["orden_almacen"], r["orden"], r["ubicacion"], "excel",
                     usuario or None)
                    for r in rows
                ],
                template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())",
                page_size=500,
            )
            cur.execute(
                "SELECT COUNT(*) FROM stock_ubicaciones WHERE sucursal = ANY(%s) AND origen = 'manual'",
                (sucursales,),
            )
            manuales = int(cur.fetchone()[0])

    sin_maestro = sorted({r["id_articulo"] for r in rows if r["id_articulo"] not in en_maestro})
    advertencias = []
    if sin_maestro:
        advertencias.append(
            f"{len(sin_maestro)} artículo(s) no existen en el maestro de artículos: "
            + ", ".join(str(i) for i in sin_maestro[:20])
        )
    return {
        "ok": True,
        "leidos": len(rows),
        "importados": len(rows),
        "deleted": eliminados,
        "sucursales": {
            suc: {
                "articulos": sum(1 for r in rows if r["sucursal"] == suc),
                "canchas": len(canchas[suc]),
                "almacenes": len(almacenes[suc]),
            }
            for suc in sucursales
        },
        "manuales_conservados": manuales,
        "sin_maestro": sin_maestro,
        "metadata": {"advertencias": advertencias},
    }


def _label(row: dict) -> str:
    texto = f"{row['cancha']} · Alm {row['id_almacen']} · #{row['orden']}"
    if row.get("ubicacion"):
        texto += f" · {row['ubicacion']}"
    return texto


def get_mapa(sucursal: str) -> dict[int, dict]:
    """Ubicación por artículo para una sucursal: {id_articulo: {...}}."""
    ensure_ubicaciones_table()
    with pg_cursor() as cur:
        cur.execute(
            """SELECT id_articulo, id_almacen, cancha, orden_cancha, orden_almacen, orden, ubicacion
               FROM stock_ubicaciones WHERE sucursal = %s""",
            (str(sucursal),),
        )
        return {int(r["id_articulo"]): dict(r) for r in cur.fetchall()}


def ordenar_por_recorrido(rows: list[dict], sucursal: str, id_key: str = "id_articulo") -> list[dict]:
    """Agrega los datos de ubicación a cada fila y las ordena por recorrido.

    El orden es estable: dentro de una misma posición (p. ej. varios lotes del
    mismo artículo) se conserva el orden que traían las filas. Las filas sin
    ubicación quedan al final.
    """
    mapa = get_mapa(sucursal)

    def _id(row) -> int | None:
        try:
            return int(str(row.get(id_key) or "").strip())
        except ValueError:
            return None

    for row in rows:
        ub = mapa.get(_id(row))
        row["con_ubicacion"] = bool(ub)
        row["cancha"] = ub["cancha"] if ub else ""
        row["id_almacen"] = ub["id_almacen"] if ub else None
        row["orden_ubicacion"] = ub["orden"] if ub else None
        row["ubicacion"] = (ub.get("ubicacion") or "") if ub else ""
        row["ubicacion_label"] = _label(ub) if ub else "Sin ubicación"
        row["_ruta"] = (0, ub["orden_cancha"], ub["orden_almacen"], ub["orden"]) if ub else _SIN_UBICACION_KEY
    rows.sort(key=lambda r: r["_ruta"])
    for row in rows:
        row.pop("_ruta", None)
    return rows


def list_ubicaciones(sucursal: str, q: str = "") -> list[dict]:
    ensure_ubicaciones_table()
    params: dict = {"sucursal": str(sucursal)}
    filtro = ""
    if q.strip():
        params["q"] = f"%{q.strip()}%"
        params["q_exacto"] = q.strip()
        filtro = """AND (u.id_articulo::text LIKE %(q)s
                         OR COALESCE(a.descripcion, u.descripcion, '') ILIKE %(q)s
                         OR u.cancha ILIKE %(q)s
                         OR u.id_almacen::text = %(q_exacto)s)"""
    with pg_cursor() as cur:
        cur.execute(
            f"""
            SELECT u.id_articulo,
                   COALESCE(NULLIF(TRIM(a.descripcion), ''), u.descripcion, '') AS descripcion,
                   u.id_almacen, u.cancha, u.orden, u.ubicacion, u.origen,
                   u.actualizado_por, u.updated_at, (a.id_articulo IS NOT NULL) AS en_maestro
            FROM stock_ubicaciones u
            LEFT JOIN articulos a ON a.id_articulo = u.id_articulo
            WHERE u.sucursal = %(sucursal)s {filtro}
            ORDER BY u.orden_cancha, u.orden_almacen, u.orden, u.id_articulo
            """,
            params,
        )
        rows = [dict(r) for r in cur.fetchall()]
    for row in rows:
        row["updated_at"] = row["updated_at"].isoformat() if row.get("updated_at") else ""
    return rows


def list_almacenes(sucursal: str) -> list[dict]:
    ensure_ubicaciones_table()
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT id_almacen, cancha, COUNT(*) AS articulos, MAX(orden) AS max_orden
            FROM stock_ubicaciones
            WHERE sucursal = %s
            GROUP BY id_almacen, cancha, orden_cancha, orden_almacen
            ORDER BY orden_cancha, orden_almacen
            """,
            (str(sucursal),),
        )
        return [dict(r) for r in cur.fetchall()]


def guardar_manual(sucursal: str, id_articulo: int, payload: dict, usuario: str = "") -> dict:
    """Alta o edición manual de la ubicación de un artículo.

    Si el almacén ya existe en la sucursal hereda su cancha y su lugar en el
    recorrido. Un almacén nuevo necesita cancha y queda al final de ella.
    """
    ensure_ubicaciones_table()
    suc = str(sucursal or "").strip()
    if not suc:
        raise ValueError("Falta la sucursal")
    try:
        id_almacen = int(payload.get("id_almacen"))
        orden = int(payload.get("orden"))
    except (TypeError, ValueError):
        raise ValueError("Almacén y orden deben ser números enteros") from None
    if orden < 1:
        raise ValueError("El orden debe ser mayor a 0")
    ubicacion = str(payload.get("ubicacion") or "").strip()[:100] or None
    cancha_nueva = str(payload.get("cancha") or "").strip()[:60]

    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT descripcion FROM articulos WHERE id_articulo = %s", (id_articulo,))
            art = cur.fetchone()
            if not art:
                raise ValueError(f"El artículo {id_articulo} no existe en el maestro de artículos")
            cur.execute(
                """SELECT cancha, orden_cancha, orden_almacen FROM stock_ubicaciones
                   WHERE sucursal = %s AND id_almacen = %s LIMIT 1""",
                (suc, id_almacen),
            )
            existente = cur.fetchone()
            if existente:
                cancha, orden_cancha, orden_almacen = existente
            else:
                if not cancha_nueva:
                    raise ValueError(f"El almacén {id_almacen} no existe en esta sucursal: indicá la cancha")
                cancha = cancha_nueva
                cur.execute(
                    """SELECT MIN(orden_cancha) FILTER (WHERE cancha = %s),
                              COALESCE(MAX(orden_cancha), 0) + 1,
                              COALESCE(MAX(orden_almacen), 0) + 1
                       FROM stock_ubicaciones WHERE sucursal = %s""",
                    (cancha, suc),
                )
                cancha_existente, cancha_siguiente, orden_almacen = cur.fetchone()
                # El recorrido ordena primero por cancha, así que un número de
                # almacén mayor a todos lo deja al final de su cancha.
                orden_cancha = cancha_existente or cancha_siguiente
            cur.execute(
                """
                INSERT INTO stock_ubicaciones (
                    sucursal, id_articulo, descripcion, id_almacen, cancha, orden_cancha,
                    orden_almacen, orden, ubicacion, origen, actualizado_por, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'manual', %s, NOW())
                ON CONFLICT (sucursal, id_articulo) DO UPDATE SET
                    descripcion = EXCLUDED.descripcion,
                    id_almacen = EXCLUDED.id_almacen,
                    cancha = EXCLUDED.cancha,
                    orden_cancha = EXCLUDED.orden_cancha,
                    orden_almacen = EXCLUDED.orden_almacen,
                    orden = EXCLUDED.orden,
                    ubicacion = EXCLUDED.ubicacion,
                    origen = 'manual',
                    actualizado_por = EXCLUDED.actualizado_por,
                    updated_at = NOW()
                """,
                (suc, id_articulo, art[0], id_almacen, cancha, orden_cancha,
                 orden_almacen, orden, ubicacion, usuario or None),
            )
    return {"sucursal": suc, "id_articulo": id_articulo, "id_almacen": id_almacen,
            "cancha": cancha, "orden": orden, "ubicacion": ubicacion or ""}


def eliminar(sucursal: str, id_articulo: int) -> bool:
    ensure_ubicaciones_table()
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM stock_ubicaciones WHERE sucursal = %s AND id_articulo = %s",
                (str(sucursal), id_articulo),
            )
            return cur.rowcount > 0
