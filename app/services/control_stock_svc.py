from __future__ import annotations

import calendar as cal_mod
import random
from datetime import date, datetime, timedelta
from threading import Lock

import psycopg2.extras

from app.database import pg_conn, pg_cursor
from app.services.articulos_svc import ensure_articulos_table
from app.services.ventas_svc import ensure_ventas_detalle_table


_CONTROL_STOCK_READY = False
_CONTROL_STOCK_LOCK = Lock()
_DISPERSION_MIN_BULTOS = 5.0
_DISPERSION_PCT = 0.20
_PENDIENTES_DESDE = date(2026, 8, 10)


def ensure_control_stock_tables() -> None:
    global _CONTROL_STOCK_READY
    if _CONTROL_STOCK_READY:
        return
    with _CONTROL_STOCK_LOCK:
        if _CONTROL_STOCK_READY:
            return
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS control_stock_conteos (
                        id BIGSERIAL PRIMARY KEY,
                        mes_abc VARCHAR(7) NOT NULL,
                        sucursal VARCHAR(20) NOT NULL DEFAULT '1',
                        semana VARCHAR(20),
                        dia VARCHAR(20),
                        fecha DATE NOT NULL,
                        responsable VARCHAR(120) NOT NULL,
                        hora_inicio TIME,
                        hora_fin TIME,
                        observaciones TEXT,
                        tipo_conteo VARCHAR(20) NOT NULL DEFAULT 'mensual',
                        estado VARCHAR(20) NOT NULL DEFAULT 'guardado',
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    CREATE TABLE IF NOT EXISTS control_stock_conteo_items (
                        conteo_id BIGINT NOT NULL REFERENCES control_stock_conteos(id) ON DELETE CASCADE,
                        id_articulo INTEGER NOT NULL,
                        descripcion VARCHAR(255),
                        abc VARCHAR(5),
                        semana VARCHAR(20),
                        dia VARCHAR(20),
                        cantidad_1 NUMERIC,
                        cantidad_2 NUMERIC,
                        cantidad_3 NUMERIC,
                        cantidad_4 NUMERIC,
                        cantidad_5 NUMERIC,
                        cantidad_6 NUMERIC,
                        unidades_sueltas NUMERIC,
                        stock NUMERIC,
                        diferencia BOOLEAN NOT NULL DEFAULT FALSE,
                        observacion TEXT,
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (conteo_id, id_articulo)
                    );
                    CREATE TABLE IF NOT EXISTS control_stock_responsables (
                        id BIGSERIAL PRIMARY KEY,
                        sucursal VARCHAR(20) NOT NULL,
                        nombre VARCHAR(120) NOT NULL,
                        activo BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        UNIQUE (sucursal, nombre)
                    );
                    CREATE TABLE IF NOT EXISTS control_stock_conteo_item_audit (
                        id BIGSERIAL PRIMARY KEY,
                        conteo_id BIGINT NOT NULL,
                        id_articulo INTEGER NOT NULL,
                        cantidad_1_old NUMERIC,
                        cantidad_2_old NUMERIC,
                        cantidad_3_old NUMERIC,
                        cantidad_4_old NUMERIC,
                        cantidad_5_old NUMERIC,
                        cantidad_6_old NUMERIC,
                        unidades_sueltas_old NUMERIC,
                        stock_old NUMERIC,
                        observacion_old TEXT,
                        cantidad_1_new NUMERIC,
                        cantidad_2_new NUMERIC,
                        cantidad_3_new NUMERIC,
                        cantidad_4_new NUMERIC,
                        cantidad_5_new NUMERIC,
                        cantidad_6_new NUMERIC,
                        unidades_sueltas_new NUMERIC,
                        stock_new NUMERIC,
                        observacion_new TEXT,
                        motivo TEXT NOT NULL,
                        editado_por VARCHAR(120),
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    ALTER TABLE control_stock_conteo_items ADD COLUMN IF NOT EXISTS cantidad_1 NUMERIC;
                    ALTER TABLE control_stock_conteo_items ADD COLUMN IF NOT EXISTS cantidad_2 NUMERIC;
                    ALTER TABLE control_stock_conteo_items ADD COLUMN IF NOT EXISTS cantidad_3 NUMERIC;
                    ALTER TABLE control_stock_conteo_items ADD COLUMN IF NOT EXISTS cantidad_4 NUMERIC;
                    ALTER TABLE control_stock_conteo_items ADD COLUMN IF NOT EXISTS cantidad_5 NUMERIC;
                    ALTER TABLE control_stock_conteo_items ADD COLUMN IF NOT EXISTS cantidad_6 NUMERIC;
                    ALTER TABLE control_stock_conteo_items ADD COLUMN IF NOT EXISTS unidades_sueltas NUMERIC;
                    ALTER TABLE control_stock_conteos ADD COLUMN IF NOT EXISTS tipo_conteo VARCHAR(20) NOT NULL DEFAULT 'mensual';
                    CREATE INDEX IF NOT EXISTS idx_control_stock_conteos_mes
                        ON control_stock_conteos(mes_abc, sucursal, fecha);
                    CREATE INDEX IF NOT EXISTS idx_control_stock_responsables_sucursal
                        ON control_stock_responsables(sucursal, activo, nombre);
                    CREATE INDEX IF NOT EXISTS idx_control_stock_item_audit_item
                        ON control_stock_conteo_item_audit(conteo_id, id_articulo, created_at);
                """)
        _CONTROL_STOCK_READY = True


def _month_range(mes: str | None) -> tuple[str, date, date]:
    if mes:
        parts = mes.split("-")
        if len(parts) != 2:
            raise ValueError("mes debe tener formato YYYY-MM")
        year, month = int(parts[0]), int(parts[1])
    else:
        today = date.today()
        year, month = today.year, today.month - 1
        if month == 0:
            year -= 1
            month = 12
    return (
        f"{year}-{month:02d}",
        date(year, month, 1),
        date(year, month, cal_mod.monthrange(year, month)[1]),
    )


def _current_month_range(mes: str | None) -> tuple[str, date, date]:
    if mes:
        return _month_range(mes)
    today = date.today()
    year, month = today.year, today.month
    return (
        f"{year}-{month:02d}",
        date(year, month, 1),
        date(year, month, cal_mod.monthrange(year, month)[1]),
    )


def _previous_month_label(mes: str) -> str:
    year, month = [int(part) for part in mes.split("-")]
    month -= 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year}-{month:02d}"


def get_frescura_status(fecha_control: str | None = None) -> dict:
    ensure_control_stock_tables()
    control_date = date.today()
    if fecha_control:
        try:
            control_date = date.fromisoformat(str(fecha_control)[:10])
        except Exception:
            control_date = date.today()
    try:
        with pg_cursor() as cur:
            cur.execute(
                """SELECT id, started_at, finished_at, estado, total_items, saved_rows
                   FROM frescura_sync_log
                   ORDER BY started_at DESC, id DESC
                   LIMIT 1"""
            )
            row = cur.fetchone()
    except Exception:
        row = None
    if not row:
        return {
            "ok": True,
            "fecha_control": control_date.isoformat(),
            "last_sync": None,
            "dias_diferencia": None,
            "estado_alerta": "sin_datos",
            "mensaje": "Sin datos de actualizacion de Frescura",
        }
    finished = row.get("finished_at") or row.get("started_at")
    if isinstance(finished, datetime):
        sync_date = finished.date()
        finished_text = finished.isoformat()
    elif isinstance(finished, date):
        sync_date = finished
        finished_text = finished.isoformat()
    else:
        sync_date = None
        finished_text = str(finished or "")
    diff = abs((control_date - sync_date).days) if sync_date else None
    stale = diff is None or diff > 1
    return {
        "ok": True,
        "fecha_control": control_date.isoformat(),
        "last_sync": {
            "id": int(row.get("id") or 0),
            "finished_at": finished_text,
            "estado": row.get("estado") or "",
            "total_items": int(row.get("total_items") or 0),
            "saved_rows": int(row.get("saved_rows") or 0),
        },
        "dias_diferencia": diff,
        "estado_alerta": "desactualizado" if stale else "ok",
        "mensaje": "Frescura desactualizada para esta fecha de control" if stale else "Frescura actualizada",
    }


def _business_days_count(ini: date, fin: date) -> int:
    current = ini
    count = 0
    while current <= fin:
        if current.weekday() < 5:
            count += 1
        current = date.fromordinal(current.toordinal() + 1)
    return count


def _sucursal_id(sucursal: str | None) -> str:
    value = str(sucursal or "1").strip().lower()
    if value == "dolores":
        return "2"
    if value in {"casa central", "central"}:
        return "1"
    return str(sucursal or "1").strip() or "1"


def _sucursal_nombre(sucursal: str | None) -> str:
    suc = _sucursal_id(sucursal)
    if suc == "1":
        return "Casa Central"
    if suc == "2":
        return "Dolores"
    return suc


def _stock_frescura_por_articulo(sucursal: str, ids: list[int]) -> dict[int, float]:
    if not ids:
        return {}
    try:
        with pg_cursor() as cur:
            cur.execute(
                """SELECT codigo_articulo,
                          SUM(COALESCE(stock_bultos, stock_actual, 0)) AS stock_bultos
                   FROM frescura_articulos
                   WHERE sucursal_id = %s
                     AND codigo_articulo = ANY(%s)
                   GROUP BY codigo_articulo""",
                (sucursal, [str(i) for i in sorted(set(ids))]),
            )
            rows = cur.fetchall() or []
    except Exception:
        return {}
    result: dict[int, float] = {}
    for row in rows:
        try:
            result[int(row["codigo_articulo"])] = float(row["stock_bultos"] or 0)
        except Exception:
            continue
    return result


def _marcar_dispersion_frescura(rows: list[tuple], sucursal: str) -> tuple[list[tuple], list[dict]]:
    esperado_por_articulo = _stock_frescura_por_articulo(sucursal, [int(row[0]) for row in rows])
    if not esperado_por_articulo:
        return rows, []
    adjusted: list[tuple] = []
    alertas: list[dict] = []
    for row in rows:
        id_articulo = int(row[0])
        contado = float(row[12] or 0)
        esperado = float(esperado_por_articulo.get(id_articulo, 0) or 0)
        base = max(abs(esperado), 1.0)
        diferencia_abs = abs(contado - esperado)
        tiene_alerta = diferencia_abs >= _DISPERSION_MIN_BULTOS and (diferencia_abs / base) >= _DISPERSION_PCT
        if tiene_alerta:
            alertas.append({
                "id_articulo": id_articulo,
                "descripcion": row[1],
                "stock_contado": round(contado, 2),
                "severidad": "alta" if diferencia_abs >= max(_DISPERSION_MIN_BULTOS * 2, base * 0.50) else "media",
                "mensaje": "Diferencia importante contra stock de Frescura. Revisar con supervisor.",
            })
            row = (
                *row[:13],
                True,
                (str(row[14] or "") + " | Alerta: dispersion importante contra Frescura").strip(" |"),
            )
        adjusted.append(row)
    return adjusted, alertas


def _rows_conteo_desde_items(items: list) -> list[tuple]:
    rows = []
    for item in items:
        try:
            id_articulo = int(item.get("id_articulo"))
        except Exception:
            continue
        stock_raw = item.get("stock")
        stock = None if stock_raw in (None, "") else float(stock_raw)
        rows.append((
            id_articulo,
            str(item.get("descripcion") or "")[:255],
            str(item.get("abc") or "")[:5],
            str(item.get("semana") or "")[:20],
            str(item.get("dia") or "")[:20],
            None if item.get("cantidad_1") in (None, "") else float(item.get("cantidad_1")),
            None if item.get("cantidad_2") in (None, "") else float(item.get("cantidad_2")),
            None if item.get("cantidad_3") in (None, "") else float(item.get("cantidad_3")),
            None if item.get("cantidad_4") in (None, "") else float(item.get("cantidad_4")),
            None if item.get("cantidad_5") in (None, "") else float(item.get("cantidad_5")),
            None if item.get("cantidad_6") in (None, "") else float(item.get("cantidad_6")),
            None if item.get("unidades_sueltas") in (None, "") else float(item.get("unidades_sueltas")),
            stock,
            bool(item.get("diferencia")),
            str(item.get("observacion") or ""),
        ))
    return rows


def _abc(acum_pct: float) -> str:
    if acum_pct <= 80:
        return "A"
    if acum_pct <= 95:
        return "B"
    return "C"


def _split_day(counter: int, total: float) -> str:
    if total <= 0:
        return "Lunes"
    days = ("Lunes", "Martes", "Miercoles", "Jueves", "Viernes")
    slot = total / len(days)
    for idx, day in enumerate(days, start=1):
        if counter < slot * idx:
            return day
    return days[-1]


def _semana_desde_fecha(value: date) -> str:
    first = value.replace(day=1)
    first_dow = first.weekday()
    first_monday_day = 1 if first_dow == 0 else 1 + ((7 - first_dow) % 7)
    if value.day < first_monday_day:
        return "semana1"
    return f"semana{min(4, max(1, ((value.day - first_monday_day) // 7) + 1))}"


def _dia_desde_fecha(value: date) -> str:
    return ("Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo")[value.weekday()]


def _apply_excel_schedule(rows: list[dict]) -> None:
    semanas = ("semana1", "semana2", "semana3", "semana4")
    c_counter = 0
    for row in rows:
        row["semana1"] = ""
        row["semana2"] = ""
        row["semana3"] = ""
        row["semana4"] = ""
        row["dia_semana1"] = ""
        row["dia_semana2"] = ""
        row["dia_semana3"] = ""
        row["dia_semana4"] = ""
        row["lunes"] = ""
        row["martes"] = ""
        row["miercoles"] = ""
        row["jueves"] = ""
        row["viernes"] = ""
        if row["participa"] != "SI":
            continue
        if row["abc"] == "A":
            for semana in semanas:
                row[semana] = semana.upper()
        elif row["abc"] == "B":
            for semana in semanas[:3]:
                row[semana] = semana.upper()
        elif row["abc"] == "C":
            semana = semanas[c_counter % len(semanas)]
            c_counter += 1
            row[semana] = semana.upper()

    day_cols = {
        "Lunes": "lunes",
        "Martes": "martes",
        "Miercoles": "miercoles",
        "Jueves": "jueves",
        "Viernes": "viernes",
    }

    for semana in semanas:
        assigned = [row for row in rows if row["participa"] == "SI" and row.get(semana)]
        total = len(assigned)
        for counter, row in enumerate(assigned, start=1):
            day = _split_day(counter, total)
            row[f"dia_{semana}"] = day
            row[day_cols[day]] = day


def _row_matches_day(row: dict, semana_key: str, dia_key: str) -> bool:
    if dia_key == "todos":
        return True
    dia = row.get(f"dia_{semana_key}") or ""
    return dia.lower() == dia_key


def _first_week_for_row(row: dict) -> str:
    for semana in ("semana1", "semana2", "semana3", "semana4"):
        if row.get(semana):
            return semana
    return ""


def _prepare_planilla_row(row: dict, semana_key: str) -> dict:
    selected = semana_key if semana_key != "todas" else _first_week_for_row(row)
    item = dict(row)
    item["control_semana"] = row.get(selected) or selected.upper()
    item["control_dia"] = row.get(f"dia_{selected}") or ""
    return item


def _logistic_number(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _complete_logistics(item: dict) -> dict:
    bultos_por_pallet = _logistic_number(item.get("bultos_por_pallet"))
    pisos = _logistic_number(item.get("pisos"))
    bultos_por_piso = _logistic_number(item.get("bultos_por_piso"))
    if bultos_por_piso <= 0 and bultos_por_pallet > 0 and pisos > 0:
        bultos_por_piso = bultos_por_pallet / pisos

    item["bultos_por_pallet"] = round(bultos_por_pallet, 2)
    item["pisos"] = round(pisos, 2)
    item["bultos_por_piso"] = round(bultos_por_piso, 2)
    item["logistica_incompleta"] = pisos <= 0 or bultos_por_piso <= 0
    item["logistica_faltante"] = [
        label
        for label, missing in (
            ("pisos", pisos <= 0),
            ("bultos_por_piso", bultos_por_piso <= 0),
        )
        if missing
    ]
    return item


def update_articulo_logistica(id_articulo: int, payload: dict) -> dict:
    ensure_articulos_table()
    articulo_id = int(id_articulo)
    bultos_por_pallet = _logistic_number(payload.get("bultos_por_pallet"))
    pisos = _logistic_number(payload.get("pisos"))
    bultos_por_piso = _logistic_number(payload.get("bultos_por_piso"))
    if pisos <= 0:
        raise ValueError("Pisos debe ser mayor a 0")
    if bultos_por_piso <= 0 and bultos_por_pallet > 0:
        bultos_por_piso = bultos_por_pallet / pisos
    if bultos_por_piso <= 0:
        raise ValueError("Bultos por piso debe ser mayor a 0")

    with pg_cursor() as cur:
        cur.execute(
            """
            UPDATE articulos
               SET bultos_por_pallet = CASE WHEN %(bultos_por_pallet)s > 0 THEN %(bultos_por_pallet)s ELSE bultos_por_pallet END,
                   pisos = %(pisos)s,
                   bultos_por_piso = %(bultos_por_piso)s,
                   actualizado = NOW()
             WHERE id_articulo = %(id_articulo)s
             RETURNING id_articulo, descripcion, bultos_por_pallet, pisos, bultos_por_piso, unidades_por_bulto
            """,
            {
                "id_articulo": articulo_id,
                "bultos_por_pallet": bultos_por_pallet,
                "pisos": pisos,
                "bultos_por_piso": bultos_por_piso,
            },
        )
        row = cur.fetchone()
    if not row:
        raise ValueError("Articulo no encontrado")
    item = dict(row)
    _complete_logistics(item)
    return item


def get_abc_articulos(mes: str | None = None, limit: int | None = None, sucursal: str | None = "1") -> dict:
    ensure_articulos_table()
    ensure_ventas_detalle_table()
    mes_label, ini, fin = _month_range(mes)
    suc = _sucursal_id(sucursal)

    params = {"ini": ini, "fin": fin, "sucursal": suc}
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT
                a.id_articulo,
                COALESCE(NULLIF(TRIM(a.descripcion), ''), MAX(v.descripcion_articulo), '') AS descripcion,
                COALESCE(NULLIF(TRIM(a.unidad_negocio), ''), NULLIF(TRIM(MAX(v.descripcion_unidad_negocio)), ''), NULLIF(TRIM(MAX(v.unidad_negocio)), ''), '') AS negocio,
                COALESCE(NULLIF(NULLIF(TRIM(a.tipo_producto), ''), 'GENERAL'), 'MERCADERIA') AS tipo_producto,
                COALESCE(NULLIF(TRIM(a.activo_cc), ''), NULLIF(TRIM(a.activo), ''), '') AS activo_cc,
                COALESCE(NULLIF(TRIM(a.movil), ''), 'SI') AS movil,
                COALESCE(NULLIF(TRIM(a.anulado), ''), 'NO') AS anulado,
                COALESCE(a.bultos_por_pallet, 0) AS bultos_por_pallet,
                COALESCE(a.bultos_por_piso, 0) AS bultos_por_piso,
                COALESCE(a.pisos, 0) AS pisos,
                COALESCE(a.apilabilidad, 0) AS apilabilidad,
                COALESCE(a.unidades_por_bulto, 0) AS unidades_por_bulto,
                COALESCE(NULLIF(TRIM(a.rotacion_abc), ''), '') AS abc_maestro,
                COALESCE(SUM(COALESCE(v.bultos, 0)), 0) AS bultos
            FROM articulos a
            LEFT JOIN ventas_detalle v
              ON v.id_articulo = a.id_articulo
             AND v.fecha BETWEEN %(ini)s AND %(fin)s
             AND COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') = %(sucursal)s
             AND LOWER(TRIM(COALESCE(v.documento, ''))) NOT LIKE '%%remit%%'
             AND LOWER(TRIM(COALESCE(v.documento, ''))) NOT LIKE '%%comod%%'
             AND LOWER(TRIM(COALESCE(v.detalle_documento, ''))) NOT LIKE '%%remit%%'
             AND LOWER(TRIM(COALESCE(v.detalle_documento, ''))) NOT LIKE '%%comod%%'
            WHERE UPPER(TRIM(COALESCE(a.activo, ''))) IN ('SI', 'S', '1', 'TRUE', 'ACTIVO')
              AND UPPER(TRIM(COALESCE(NULLIF(a.movil, ''), 'SI'))) IN ('SI', 'S', '1', 'TRUE')
              AND UPPER(TRIM(COALESCE(NULLIF(a.anulado, ''), 'NO'))) IN ('NO', 'N', '0', 'FALSE')
              AND UPPER(TRIM(COALESCE(a.tipo_producto, ''))) NOT IN ('P.O.P.', 'ENVASE', 'ESQUELETO', 'MERCHANDISING', '')
            GROUP BY a.id_articulo, a.descripcion, a.unidad_negocio, a.tipo_producto, a.activo_cc, a.activo, a.movil, a.anulado, a.bultos_por_pallet, a.bultos_por_piso, a.pisos, a.apilabilidad, a.unidades_por_bulto, a.rotacion_abc
            ORDER BY bultos DESC, a.id_articulo
            """,
            params,
        )
        raw_rows = [dict(r) for r in (cur.fetchall() or [])]

    total_bultos = sum(float(r.get("bultos") or 0) for r in raw_rows)
    acumulado = 0.0
    rows = []
    for idx, row in enumerate(raw_rows, start=1):
        bultos = float(row.get("bultos") or 0)
        peso_pct = (bultos / total_bultos * 100) if total_bultos else 0
        acumulado += peso_pct
        item = {
            "rank": idx,
            "id_articulo": row.get("id_articulo"),
            "descripcion": row.get("descripcion") or "",
            "negocio": row.get("negocio") or "",
            "tipo_producto": row.get("tipo_producto") or "",
            "stock_si": "SI" if str(row.get("activo_cc") or "").strip() else "",
            "activo": "SI",
            "movil": row.get("movil") or "SI",
            "anulado": row.get("anulado") or "NO",
            "bultos_por_pallet": row.get("bultos_por_pallet"),
            "bultos_por_piso": row.get("bultos_por_piso"),
            "pisos": row.get("pisos"),
            "apilabilidad": round(float(row.get("apilabilidad") or 0), 2),
            "unidades_por_bulto": round(float(row.get("unidades_por_bulto") or 0), 2),
            "bultos": round(bultos, 2),
            "peso_pct": round(peso_pct, 2),
            "acumulado_pct": round(min(acumulado, 100), 2),
            "abc": _abc(acumulado),
            "abc_maestro": row.get("abc_maestro") or "",
            "participa": "SI",
            "status": "OK",
        }
        _complete_logistics(item)
        rows.append(item)

    _apply_excel_schedule(rows)

    if limit:
        rows = rows[: max(1, min(int(limit), 1000))]

    logistica_incompleta = sum(1 for row in rows if row.get("logistica_incompleta"))
    return {
        "ok": True,
        "mes": mes_label,
        "sucursal": suc,
        "sucursal_nombre": _sucursal_nombre(suc),
        "total_articulos": len(raw_rows),
        "total_bultos": round(total_bultos, 2),
        "logistica": {
            "total_articulos": len(rows),
            "incompletos": logistica_incompleta,
            "completos": max(0, len(rows) - logistica_incompleta),
        },
        "rows": rows,
    }


def get_planilla(
    mes: str | None = None,
    semana: str = "TODAS",
    dia: str = "TODOS",
    abc: str = "TODOS",
    sucursal: str | None = "1",
) -> dict:
    data = get_abc_articulos(mes, sucursal=sucursal)
    semana_key = (semana or "TODAS").strip().lower()
    dia_key = (dia or "TODOS").strip().lower()
    abc_key = (abc or "TODOS").strip().upper()
    day_map = {
        "lunes": "lunes",
        "martes": "martes",
        "miercoles": "miercoles",
        "miércoles": "miercoles",
        "jueves": "jueves",
        "viernes": "viernes",
    }

    rows = []
    for row in data["rows"]:
        if semana_key != "todas" and not row.get(semana_key):
            continue
        if dia_key != "todos":
            if semana_key == "todas":
                matches_any_week = any(
                    _row_matches_day(row, item, dia_key)
                    for item in ("semana1", "semana2", "semana3", "semana4")
                    if row.get(item)
                )
                if not matches_any_week:
                    continue
            elif not _row_matches_day(row, semana_key, dia_key):
                continue
        if abc_key != "TODOS" and row.get("abc") != abc_key:
            continue
        rows.append(_prepare_planilla_row(row, semana_key))
    data["rows"] = rows
    data["total_filtrado"] = len(rows)
    incompletos = sum(1 for row in rows if row.get("logistica_incompleta"))
    data["logistica_filtrada"] = {
        "total_articulos": len(rows),
        "incompletos": incompletos,
        "completos": max(0, len(rows) - incompletos),
    }
    data["filtros"] = {"semana": semana, "dia": dia, "abc": abc, "sucursal": data["sucursal"]}
    return data


def generar_control_externo(mes: str | None = None, sucursal: str | None = "1", cantidad: int = 6) -> dict:
    cantidad = max(1, min(20, int(cantidad or 6)))
    suc = _sucursal_id(sucursal)
    data = get_abc_articulos(mes=mes, sucursal=suc)
    rows = [row for row in data.get("rows", []) if row.get("participa") == "SI"]
    grupos = {
        "A": [row for row in rows if row.get("abc") == "A"],
        "B": [row for row in rows if row.get("abc") == "B"],
        "C": [row for row in rows if row.get("abc") == "C"],
    }
    selected: list[dict] = []
    target_por_abc = {"A": 2, "B": 2, "C": 2} if cantidad >= 6 else {}
    for abc_key, target in target_por_abc.items():
        pool = grupos.get(abc_key, [])
        if pool:
            selected.extend(random.sample(pool, min(target, len(pool))))
    selected_ids = {int(row["id_articulo"]) for row in selected}
    faltan = cantidad - len(selected)
    if faltan > 0:
        restantes = [row for row in rows if int(row["id_articulo"]) not in selected_ids]
        if restantes:
            selected.extend(random.sample(restantes, min(faltan, len(restantes))))
    random.shuffle(selected)
    for row in selected:
        row["control_semana"] = "externo"
        row["control_dia"] = "Externo"
    return {
        "ok": True,
        "mes": data.get("mes"),
        "sucursal": suc,
        "sucursal_nombre": _sucursal_nombre(suc),
        "cantidad": len(selected),
        "rows": selected,
    }


def get_planificacion(mes: str | None = None, sucursal: str | None = "1") -> dict:
    data = get_abc_articulos(mes, sucursal=sucursal)
    semanas = ("semana1", "semana2", "semana3", "semana4")
    dias = ("Lunes", "Martes", "Miercoles", "Jueves", "Viernes")

    abc_counts = {"A": 0, "B": 0, "C": 0}
    control_events = {"A": 0, "B": 0, "C": 0}
    por_semana_dia = {
        semana.upper(): {dia: 0 for dia in dias}
        for semana in semanas
    }
    mix_semana = {}

    for semana in semanas:
        abc_set = set()
        for row in data["rows"]:
            if row.get(semana):
                abc_set.add(row["abc"])
                day = row.get(f"dia_{semana}") or ""
                if day in por_semana_dia[semana.upper()]:
                    por_semana_dia[semana.upper()][day] += 1
                control_events[row["abc"]] += 1
        mix_semana[semana.upper()] = "-".join(x for x in ("A", "B", "C") if x in abc_set)

    for row in data["rows"]:
        if row["abc"] in abc_counts:
            abc_counts[row["abc"]] += 1

    total_articulos = len(data["rows"])
    total_controles = sum(control_events.values())
    return {
        "ok": True,
        "mes": data["mes"],
        "sucursal": data["sucursal"],
        "sucursal_nombre": data["sucursal_nombre"],
        "total_articulos": total_articulos,
        "abc_counts": abc_counts,
        "control_events": control_events,
        "frecuencias": {"A": 4, "B": 3, "C": 1},
        "total_controles": total_controles,
        "mix_semana": mix_semana,
        "por_semana_dia": por_semana_dia,
        "totales_dia": {
            dia: sum(por_semana_dia[semana.upper()][dia] for semana in semanas)
            for dia in dias
        },
    }


def get_pendientes_dias(mes: str | None = None, hasta: str | None = None) -> dict:
    ensure_control_stock_tables()
    mes_label, ini, fin = _current_month_range(mes)
    inicio_control = max(ini, _PENDIENTES_DESDE)
    try:
        hasta_dt = date.fromisoformat(str(hasta or date.today().isoformat())[:10])
    except ValueError as exc:
        raise ValueError("hasta debe tener formato YYYY-MM-DD") from exc
    fin_control = min(fin, hasta_dt)
    periodo_activo = fin_control >= inicio_control
    if fin_control < inicio_control:
        fin_control = inicio_control - timedelta(days=1)

    sucursales = ("1", "2")
    plan_por_sucursal: dict[str, dict[tuple[str, str], int]] = {}
    for suc in sucursales:
        plan = get_planificacion(_previous_month_label(mes_label), sucursal=suc)
        plan_por_sucursal[suc] = {
            (semana.lower(), dia): int(cantidad or 0)
            for semana, dias in (plan.get("por_semana_dia") or {}).items()
            for dia, cantidad in (dias or {}).items()
        }

    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT sucursal, fecha, COUNT(*) AS controles
            FROM control_stock_conteos
            WHERE fecha BETWEEN %(ini)s AND %(fin)s
              AND tipo_conteo = 'mensual'
              AND sucursal = ANY(%(sucursales)s)
            GROUP BY sucursal, fecha
            """,
            {"ini": inicio_control, "fin": fin_control, "sucursales": list(sucursales)},
        )
        realizados = {
            (str(r["sucursal"]), r["fecha"]): int(r["controles"] or 0)
            for r in (cur.fetchall() or [])
        }

    por_sucursal: list[dict] = []
    total_pendientes = 0
    total_vencidos = 0
    cursor = inicio_control
    fechas: list[date] = []
    while cursor <= fin_control:
        if cursor.weekday() < 5:
            fechas.append(cursor)
        cursor += timedelta(days=1)

    for suc in sucursales:
        pendientes: list[dict] = []
        realizados_count = 0
        esperados_count = 0
        for fecha_item in fechas:
            semana = _semana_desde_fecha(fecha_item)
            dia = _dia_desde_fecha(fecha_item)
            esperados = int(plan_por_sucursal.get(suc, {}).get((semana, dia), 0))
            if esperados <= 0:
                continue
            done = int(realizados.get((suc, fecha_item), 0))
            esperados_count += 1
            if done > 0:
                realizados_count += 1
                continue
            vencido = fecha_item < date.today()
            total_pendientes += 1
            if vencido:
                total_vencidos += 1
            pendientes.append({
                "fecha": fecha_item.isoformat(),
                "semana": semana,
                "dia": dia,
                "articulos_planificados": esperados,
                "controles_guardados": done,
                "vencido": vencido,
            })
        por_sucursal.append({
            "sucursal": suc,
            "sucursal_nombre": _sucursal_nombre(suc),
            "dias_esperados": esperados_count,
            "dias_realizados": realizados_count,
            "dias_pendientes": len(pendientes),
            "pendientes": pendientes,
        })

    return {
        "ok": True,
        "mes": mes_label,
        "desde": inicio_control.isoformat(),
        "hasta": fin_control.isoformat(),
        "periodo_activo": periodo_activo,
        "total_pendientes": total_pendientes,
        "total_vencidos": total_vencidos,
        "sucursales": por_sucursal,
    }


def guardar_conteo(payload: dict, responsable_default: str = "") -> dict:
    ensure_control_stock_tables()
    mes = str(payload.get("mes") or "").strip()
    if not mes:
        mes = _month_range(None)[0]
    fecha = str(payload.get("fecha") or date.today().isoformat())
    responsable = str(payload.get("responsable") or responsable_default or "").strip()
    if not responsable:
        raise ValueError("responsable es obligatorio")

    items = payload.get("items") or []
    if not isinstance(items, list):
        raise ValueError("items debe ser una lista")

    conteo = {
        "mes_abc": mes,
        "sucursal": _sucursal_id(payload.get("sucursal")),
        "semana": str(payload.get("semana") or "TODAS"),
        "dia": str(payload.get("dia") or "TODOS"),
        "fecha": fecha,
        "responsable": responsable,
        "hora_inicio": payload.get("hora_inicio") or None,
        "hora_fin": payload.get("hora_fin") or None,
        "observaciones": str(payload.get("observaciones") or ""),
        "tipo_conteo": str(payload.get("tipo_conteo") or "mensual").strip().lower()[:20] or "mensual",
    }

    rows = _rows_conteo_desde_items(items)

    rows, alertas_dispersion = _marcar_dispersion_frescura(rows, conteo["sucursal"])

    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT id
                   FROM control_stock_conteos
                   WHERE mes_abc = %(mes_abc)s
                     AND sucursal = %(sucursal)s
                     AND semana = %(semana)s
                     AND dia = %(dia)s
                     AND fecha = %(fecha)s
                     AND responsable = %(responsable)s
                     AND tipo_conteo = %(tipo_conteo)s
                   ORDER BY id DESC
                   LIMIT 1""",
                conteo,
            )
            existing = cur.fetchone()
            if existing:
                raise ValueError(
                    "Ya existe un conteo guardado para esta sucursal, fecha, semana, dia y responsable. "
                    "No se puede volver a grabar el mismo conteo."
                )
            else:
                cur.execute(
                    """INSERT INTO control_stock_conteos(
                           mes_abc, sucursal, semana, dia, fecha, responsable,
                           hora_inicio, hora_fin, observaciones, tipo_conteo
                       )
                       VALUES (
                           %(mes_abc)s, %(sucursal)s, %(semana)s, %(dia)s, %(fecha)s,
                           %(responsable)s, %(hora_inicio)s, %(hora_fin)s, %(observaciones)s, %(tipo_conteo)s
                       )
                       RETURNING id, mes_abc, sucursal, semana, dia, fecha, responsable,
                                 hora_inicio, hora_fin, observaciones, tipo_conteo, estado, created_at""",
                    conteo,
                )
                saved = dict(cur.fetchone() or {})
            if rows:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO control_stock_conteo_items(
                           conteo_id, id_articulo, descripcion, abc, semana, dia,
                           cantidad_1, cantidad_2, cantidad_3, cantidad_4, cantidad_5, cantidad_6, unidades_sueltas,
                           stock, diferencia, observacion
                       )
                       VALUES %s
                       ON CONFLICT (conteo_id, id_articulo) DO UPDATE SET
                           cantidad_1 = EXCLUDED.cantidad_1,
                           cantidad_2 = EXCLUDED.cantidad_2,
                           cantidad_3 = EXCLUDED.cantidad_3,
                           cantidad_4 = EXCLUDED.cantidad_4,
                           cantidad_5 = EXCLUDED.cantidad_5,
                           cantidad_6 = EXCLUDED.cantidad_6,
                           unidades_sueltas = EXCLUDED.unidades_sueltas,
                           stock = EXCLUDED.stock,
                           diferencia = EXCLUDED.diferencia,
                           observacion = EXCLUDED.observacion,
                           updated_at = NOW()""",
                    [(saved["id"], *row) for row in rows],
                )
    saved["items_guardados"] = len(rows)
    saved["alertas_dispersion"] = alertas_dispersion
    saved["total_alertas_dispersion"] = len(alertas_dispersion)
    return saved


def validar_dispersion_conteo(payload: dict) -> dict:
    ensure_control_stock_tables()
    items = payload.get("items") or []
    if not isinstance(items, list):
        raise ValueError("items debe ser una lista")
    sucursal = _sucursal_id(payload.get("sucursal"))
    rows = _rows_conteo_desde_items(items)
    _, alertas = _marcar_dispersion_frescura(rows, sucursal)
    return {
        "sucursal": sucursal,
        "total_items": len(rows),
        "total_alertas_dispersion": len(alertas),
        "alertas_dispersion": alertas,
    }


def editar_conteo_item(conteo_id: int, id_articulo: int, payload: dict, editado_por: str = "") -> dict:
    ensure_control_stock_tables()
    motivo = str(payload.get("motivo") or "").strip()
    if not motivo:
        raise ValueError("motivo es obligatorio")

    def _num(key: str) -> float | None:
        value = payload.get(key)
        if value in (None, ""):
            return None
        number = float(value)
        if number < 0:
            raise ValueError("las cantidades no pueden ser negativas")
        return number

    values = {f"cantidad_{idx}": _num(f"cantidad_{idx}") for idx in range(1, 7)}
    unidades_sueltas = _num("unidades_sueltas")
    stock = sum(float(v or 0) for v in values.values())
    observacion = str(payload.get("observacion") or "").strip()

    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT c.id AS conteo_id, c.fecha, c.responsable, c.sucursal, c.estado,
                          i.id_articulo, i.descripcion, i.abc, i.semana, i.dia,
                          i.cantidad_1, i.cantidad_2, i.cantidad_3, i.cantidad_4, i.cantidad_5, i.cantidad_6,
                          i.unidades_sueltas, i.stock, i.observacion
                   FROM control_stock_conteos c
                   JOIN control_stock_conteo_items i ON i.conteo_id = c.id
                   WHERE c.id = %s AND i.id_articulo = %s
                   FOR UPDATE""",
                (conteo_id, id_articulo),
            )
            current = cur.fetchone()
            if not current:
                raise ValueError("item de control no encontrado")

            cur.execute(
                """INSERT INTO control_stock_conteo_item_audit(
                       conteo_id, id_articulo,
                       cantidad_1_old, cantidad_2_old, cantidad_3_old, cantidad_4_old, cantidad_5_old, cantidad_6_old,
                       unidades_sueltas_old, stock_old, observacion_old,
                       cantidad_1_new, cantidad_2_new, cantidad_3_new, cantidad_4_new, cantidad_5_new, cantidad_6_new,
                       unidades_sueltas_new, stock_new, observacion_new,
                       motivo, editado_por
                   )
                   VALUES (
                       %(conteo_id)s, %(id_articulo)s,
                       %(cantidad_1_old)s, %(cantidad_2_old)s, %(cantidad_3_old)s, %(cantidad_4_old)s, %(cantidad_5_old)s, %(cantidad_6_old)s,
                       %(unidades_sueltas_old)s, %(stock_old)s, %(observacion_old)s,
                       %(cantidad_1_new)s, %(cantidad_2_new)s, %(cantidad_3_new)s, %(cantidad_4_new)s, %(cantidad_5_new)s, %(cantidad_6_new)s,
                       %(unidades_sueltas_new)s, %(stock_new)s, %(observacion_new)s,
                       %(motivo)s, %(editado_por)s
                   )""",
                {
                    "conteo_id": conteo_id,
                    "id_articulo": id_articulo,
                    "cantidad_1_old": current.get("cantidad_1"),
                    "cantidad_2_old": current.get("cantidad_2"),
                    "cantidad_3_old": current.get("cantidad_3"),
                    "cantidad_4_old": current.get("cantidad_4"),
                    "cantidad_5_old": current.get("cantidad_5"),
                    "cantidad_6_old": current.get("cantidad_6"),
                    "unidades_sueltas_old": current.get("unidades_sueltas"),
                    "stock_old": current.get("stock"),
                    "observacion_old": current.get("observacion"),
                    "cantidad_1_new": values["cantidad_1"],
                    "cantidad_2_new": values["cantidad_2"],
                    "cantidad_3_new": values["cantidad_3"],
                    "cantidad_4_new": values["cantidad_4"],
                    "cantidad_5_new": values["cantidad_5"],
                    "cantidad_6_new": values["cantidad_6"],
                    "unidades_sueltas_new": unidades_sueltas,
                    "stock_new": stock,
                    "observacion_new": observacion,
                    "motivo": motivo,
                    "editado_por": editado_por[:120],
                },
            )
            cur.execute(
                """UPDATE control_stock_conteo_items
                   SET cantidad_1 = %(cantidad_1)s,
                       cantidad_2 = %(cantidad_2)s,
                       cantidad_3 = %(cantidad_3)s,
                       cantidad_4 = %(cantidad_4)s,
                       cantidad_5 = %(cantidad_5)s,
                       cantidad_6 = %(cantidad_6)s,
                       unidades_sueltas = %(unidades_sueltas)s,
                       stock = %(stock)s,
                       observacion = %(observacion)s,
                       updated_at = NOW()
                   WHERE conteo_id = %(conteo_id)s AND id_articulo = %(id_articulo)s
                   RETURNING conteo_id, id_articulo, cantidad_1, cantidad_2, cantidad_3, cantidad_4,
                             cantidad_5, cantidad_6, unidades_sueltas, stock, observacion, updated_at""",
                {
                    "conteo_id": conteo_id,
                    "id_articulo": id_articulo,
                    **values,
                    "unidades_sueltas": unidades_sueltas,
                    "stock": stock,
                    "observacion": observacion,
                },
            )
            updated = dict(cur.fetchone() or {})
            cur.execute("UPDATE control_stock_conteos SET updated_at = NOW() WHERE id = %s", (conteo_id,))

    updated["stock"] = float(updated.get("stock") or 0)
    updated["unidades_sueltas"] = float(updated.get("unidades_sueltas") or 0)
    return updated


def list_responsables(sucursal: str | None = "1", incluir_inactivos: bool = False) -> list[dict]:
    ensure_control_stock_tables()
    suc = _sucursal_id(sucursal)
    where = "" if incluir_inactivos else "AND activo"
    with pg_cursor() as cur:
        cur.execute(
            f"""SELECT id, sucursal, nombre, activo, created_at, updated_at
                FROM control_stock_responsables
                WHERE sucursal = %(sucursal)s {where}
                ORDER BY activo DESC, nombre""",
            {"sucursal": suc},
        )
        return [dict(r) for r in cur.fetchall() or []]


def save_responsable(data: dict) -> dict:
    ensure_control_stock_tables()
    suc = _sucursal_id(data.get("sucursal"))
    nombre = str(data.get("nombre") or "").strip()
    if not nombre:
        raise ValueError("nombre es obligatorio")
    activo = bool(data.get("activo", True))
    with pg_cursor() as cur:
        cur.execute(
            """INSERT INTO control_stock_responsables(sucursal, nombre, activo)
               VALUES (%(sucursal)s, %(nombre)s, %(activo)s)
               ON CONFLICT (sucursal, nombre) DO UPDATE SET activo = EXCLUDED.activo, updated_at = NOW()
               RETURNING id, sucursal, nombre, activo, created_at, updated_at""",
            {"sucursal": suc, "nombre": nombre, "activo": activo},
        )
        return dict(cur.fetchone() or {})


def update_responsable(responsable_id: int, data: dict) -> dict:
    ensure_control_stock_tables()
    fields = []
    params = {"id": responsable_id}
    if "nombre" in data:
        nombre = str(data.get("nombre") or "").strip()
        if not nombre:
            raise ValueError("nombre no puede ser vacio")
        fields.append("nombre = %(nombre)s")
        params["nombre"] = nombre
    if "activo" in data:
        fields.append("activo = %(activo)s")
        params["activo"] = bool(data.get("activo"))
    if not fields:
        raise ValueError("sin cambios")
    with pg_cursor() as cur:
        cur.execute(
            f"""UPDATE control_stock_responsables
                SET {', '.join(fields)}, updated_at = NOW()
                WHERE id = %(id)s
                RETURNING id, sucursal, nombre, activo, created_at, updated_at""",
            params,
        )
        row = cur.fetchone()
    if not row:
        raise ValueError("responsable no encontrado")
    return dict(row)


def get_resumen_mensual(mes: str | None = None, sucursal: str | None = "1") -> dict:
    ensure_control_stock_tables()
    mes_label, ini, fin = _current_month_range(mes)
    suc = _sucursal_id(sucursal)
    with pg_cursor() as cur:
        cur.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (c.sucursal, c.fecha, c.responsable, c.semana, c.dia)
                    c.*
                FROM control_stock_conteos c
                WHERE c.sucursal = %(sucursal)s
                  AND c.fecha BETWEEN %(ini)s AND %(fin)s
                ORDER BY c.sucursal, c.fecha, c.responsable, c.semana, c.dia, c.updated_at DESC, c.id DESC
            )
            SELECT
                c.id,
                c.fecha,
                c.responsable,
                c.semana,
                c.dia,
                c.hora_inicio,
                c.hora_fin,
                COUNT(i.id_articulo) FILTER (WHERE i.stock IS NOT NULL) AS articulos_contados,
                STRING_AGG(
                    CONCAT(i.id_articulo::text, ' - ', COALESCE(NULLIF(i.descripcion, ''), 'Sin descripcion')),
                    E'\n'
                    ORDER BY i.id_articulo
                ) FILTER (WHERE i.stock IS NOT NULL) AS articulos_detalle,
                COALESCE(SUM(i.stock), 0) AS bultos_contados,
                COALESCE(SUM(i.unidades_sueltas), 0) AS unidades_sueltas,
                CASE
                  WHEN c.hora_inicio IS NOT NULL AND c.hora_fin IS NOT NULL
                  THEN EXTRACT(EPOCH FROM (
                    (DATE '2000-01-01' + c.hora_fin) -
                    (DATE '2000-01-01' + c.hora_inicio)
                  )) / 60
                  ELSE NULL
                END AS minutos
            FROM latest c
            LEFT JOIN control_stock_conteo_items i ON i.conteo_id = c.id
            GROUP BY c.id, c.fecha, c.responsable, c.semana, c.dia, c.hora_inicio, c.hora_fin
            ORDER BY c.fecha, c.responsable, c.id
            """,
            {"sucursal": suc, "ini": ini, "fin": fin},
        )
        diarios = []
        for r in cur.fetchall() or []:
            diarios.append({
                "id": int(r["id"]),
                "fecha": r["fecha"].isoformat() if r.get("fecha") else "",
                "responsable": r.get("responsable") or "",
                "semana": r.get("semana") or "",
                "dia": r.get("dia") or "",
                "hora_inicio": str(r.get("hora_inicio") or ""),
                "hora_fin": str(r.get("hora_fin") or ""),
                "articulos_contados": int(r.get("articulos_contados") or 0),
                "articulos_detalle": r.get("articulos_detalle") or "",
                "bultos_contados": float(r.get("bultos_contados") or 0),
                "unidades_sueltas": float(r.get("unidades_sueltas") or 0),
                "minutos": round(float(r["minutos"]), 1) if r.get("minutos") is not None else None,
            })

    por_controlador: dict[str, dict] = {}
    for row in diarios:
        key = row["responsable"] or "Sin responsable"
        acc = por_controlador.setdefault(key, {
            "responsable": key,
            "dias": 0,
            "controles": 0,
            "articulos_contados": 0,
            "bultos_contados": 0.0,
            "unidades_sueltas": 0.0,
            "minutos": 0.0,
        })
        acc["controles"] += 1
        acc["articulos_contados"] += row["articulos_contados"]
        acc["bultos_contados"] += row["bultos_contados"]
        acc["unidades_sueltas"] += row["unidades_sueltas"]
        if row["minutos"] is not None:
            acc["minutos"] += row["minutos"]

    dias_por_controlador: dict[str, set] = {}
    for row in diarios:
        dias_por_controlador.setdefault(row["responsable"] or "Sin responsable", set()).add(row["fecha"])
    for key, days in dias_por_controlador.items():
        por_controlador[key]["dias"] = len(days)
        por_controlador[key]["bultos_contados"] = round(por_controlador[key]["bultos_contados"], 2)
        por_controlador[key]["unidades_sueltas"] = round(por_controlador[key]["unidades_sueltas"], 2)
        por_controlador[key]["minutos"] = round(por_controlador[key]["minutos"], 1)

    with pg_cursor() as cur:
        cur.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (c.sucursal, c.fecha, c.responsable, c.semana, c.dia)
                    c.id
                FROM control_stock_conteos c
                WHERE c.sucursal = %(sucursal)s
                  AND c.fecha BETWEEN %(ini)s AND %(fin)s
                ORDER BY c.sucursal, c.fecha, c.responsable, c.semana, c.dia, c.updated_at DESC, c.id DESC
            )
            SELECT i.id_articulo, COUNT(*) FILTER (WHERE i.stock IS NOT NULL) AS controles
            FROM latest c
            JOIN control_stock_conteo_items i ON i.conteo_id = c.id
            GROUP BY i.id_articulo
            """,
            {"sucursal": suc, "ini": ini, "fin": fin},
        )
        controles_articulo = {int(r["id_articulo"]): int(r["controles"] or 0) for r in (cur.fetchall() or [])}

    abc_mes = _previous_month_label(mes_label)
    abc_rows = get_abc_articulos(abc_mes, sucursal=suc)["rows"]
    objetivo_por_abc = {"A": 4, "B": 3, "C": 1}
    cumplimiento_abc = {
        key: {"abc": key, "articulos": 0, "objetivo": 0, "realizados": 0, "pendientes": 0, "vencidos": 0, "cumplimiento_pct": 0.0}
        for key in ("A", "B", "C")
    }
    pendientes_detalle = []
    for article in abc_rows:
        abc = str(article.get("abc") or "C")
        target = objetivo_por_abc.get(abc, 1)
        done = controles_articulo.get(int(article["id_articulo"]), 0)
        pending = max(0, target - done)
        row = cumplimiento_abc.setdefault(abc, {"abc": abc, "articulos": 0, "objetivo": 0, "realizados": 0, "pendientes": 0, "vencidos": 0, "cumplimiento_pct": 0.0})
        row["articulos"] += 1
        row["objetivo"] += target
        row["realizados"] += min(done, target)
        row["pendientes"] += pending
        if pending:
            row["vencidos"] += 1
            pendientes_detalle.append({
                "id_articulo": int(article["id_articulo"]),
                "descripcion": article.get("descripcion") or "",
                "abc": abc,
                "objetivo": target,
                "controles": done,
                "pendientes": pending,
            })
    for row in cumplimiento_abc.values():
        row["cumplimiento_pct"] = round((row["realizados"] / row["objetivo"] * 100) if row["objetivo"] else 0, 1)

    total_articulos = sum(r["articulos_contados"] for r in diarios)
    total_minutos = sum(float(r["minutos"] or 0) for r in diarios)
    dias_controlados = len({r["fecha"] for r in diarios if r["fecha"]})
    dias_habiles = _business_days_count(ini, fin)
    kpis = {
        "abc_mes": abc_mes,
        "objetivo_controles": sum(r["objetivo"] for r in cumplimiento_abc.values()),
        "controles_objetivo_realizados": sum(r["realizados"] for r in cumplimiento_abc.values()),
        "controles_pendientes": sum(r["pendientes"] for r in cumplimiento_abc.values()),
        "articulos_vencidos": sum(r["vencidos"] for r in cumplimiento_abc.values()),
        "cumplimiento_pct": round(
            (sum(r["realizados"] for r in cumplimiento_abc.values()) / sum(r["objetivo"] for r in cumplimiento_abc.values()) * 100)
            if sum(r["objetivo"] for r in cumplimiento_abc.values()) else 0,
            1,
        ),
        "dias_controlados": dias_controlados,
        "dias_habiles": dias_habiles,
        "cobertura_dias_pct": round((dias_controlados / dias_habiles * 100) if dias_habiles else 0, 1),
        "articulos_por_hora": round((total_articulos / (total_minutos / 60)) if total_minutos else 0, 1),
    }

    return {
        "ok": True,
        "mes": mes_label,
        "sucursal": suc,
        "sucursal_nombre": _sucursal_nombre(suc),
        "kpis": kpis,
        "cumplimiento_abc": [cumplimiento_abc[key] for key in ("A", "B", "C")],
        "pendientes_top": sorted(pendientes_detalle, key=lambda x: ({"A": 0, "B": 1, "C": 2}.get(x["abc"], 3), -x["pendientes"], x["id_articulo"]))[:20],
        "diarios": diarios,
        "por_controlador": sorted(por_controlador.values(), key=lambda x: x["responsable"]),
    }


def get_articulos_controlados(mes: str | None = None, sucursal: str | None = "1") -> dict:
    ensure_control_stock_tables()
    mes_label, ini, fin = _current_month_range(mes)
    suc = _sucursal_id(sucursal)
    base = get_abc_articulos(mes_label, sucursal=suc)

    with pg_cursor() as cur:
        cur.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (c.sucursal, c.fecha, c.responsable, c.semana, c.dia)
                    c.id
                FROM control_stock_conteos c
                WHERE c.sucursal = %(sucursal)s
                  AND c.fecha BETWEEN %(ini)s AND %(fin)s
                ORDER BY c.sucursal, c.fecha, c.responsable, c.semana, c.dia, c.updated_at DESC, c.id DESC
            )
            SELECT
                i.id_articulo,
                COUNT(*) FILTER (WHERE i.stock IS NOT NULL) AS controles
            FROM latest c
            JOIN control_stock_conteo_items i ON i.conteo_id = c.id
            GROUP BY i.id_articulo
            """,
            {"sucursal": suc, "ini": ini, "fin": fin},
        )
        counts = {int(r["id_articulo"]): int(r["controles"] or 0) for r in (cur.fetchall() or [])}

    rows = []
    for row in base["rows"]:
        controles = counts.get(int(row["id_articulo"]), 0)
        item = dict(row)
        item["controles"] = controles
        for idx in range(1, 5):
            item[f"control_{idx}"] = "X" if controles >= idx else ""
        item["estado_control"] = "OK" if controles else "Pendiente"
        rows.append(item)

    return {
        "ok": True,
        "mes": mes_label,
        "sucursal": suc,
        "sucursal_nombre": _sucursal_nombre(suc),
        "total_articulos": len(rows),
        "total_controlados": sum(1 for r in rows if r["controles"] > 0),
        "total_pendientes": sum(1 for r in rows if r["controles"] == 0),
        "rows": rows,
    }


def get_resumen_por_articulo(
    fecha_control: str | None = None,
    sucursal: str | None = "1",
    responsable: str | None = None,
) -> dict:
    ensure_control_stock_tables()
    if not fecha_control:
        fecha_control = date.today().isoformat()
    try:
        fecha_dt = date.fromisoformat(str(fecha_control))
    except ValueError as exc:
        raise ValueError("fecha debe tener formato YYYY-MM-DD") from exc
    suc = _sucursal_id(sucursal)
    responsable_txt = str(responsable or "").strip()

    with pg_cursor() as cur:
        cur.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (c.sucursal, c.fecha, c.responsable, c.semana, c.dia)
                    c.*
                FROM control_stock_conteos c
                WHERE c.sucursal = %(sucursal)s
                  AND c.fecha = %(fecha)s
                  AND (%(responsable)s = '' OR c.responsable = %(responsable)s)
                ORDER BY c.sucursal, c.fecha, c.responsable, c.semana, c.dia, c.updated_at DESC, c.id DESC
            ),
            detalle AS (
                SELECT
                    i.id_articulo,
                    COALESCE(NULLIF(i.descripcion, ''), 'Sin descripcion') AS descripcion,
                    COALESCE(NULLIF(i.abc, ''), '-') AS abc,
                    SUM(COALESCE(i.stock, 0)) AS total_bultos,
                    SUM(COALESCE(i.unidades_sueltas, 0)) AS total_unidades,
                    COUNT(*) AS controles,
                    STRING_AGG(DISTINCT c.responsable, ', ' ORDER BY c.responsable) AS responsables,
                    JSON_AGG(
                        JSON_BUILD_OBJECT(
                            'conteo_id', c.id,
                            'responsable', c.responsable,
                            'semana', c.semana,
                            'dia', c.dia,
                            'cantidad_1', i.cantidad_1,
                            'cantidad_2', i.cantidad_2,
                            'cantidad_3', i.cantidad_3,
                            'cantidad_4', i.cantidad_4,
                            'cantidad_5', i.cantidad_5,
                            'cantidad_6', i.cantidad_6,
                            'unidades_sueltas', i.unidades_sueltas,
                            'stock', i.stock,
                            'observacion', i.observacion
                        )
                        ORDER BY c.responsable, c.id
                    ) AS controles_detalle
                FROM latest c
                JOIN control_stock_conteo_items i ON i.conteo_id = c.id
                WHERE i.stock IS NOT NULL
                GROUP BY i.id_articulo, i.descripcion, i.abc
            )
            SELECT *
            FROM detalle
            ORDER BY
                CASE abc WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'C' THEN 3 ELSE 4 END,
                id_articulo
            """,
            {"sucursal": suc, "fecha": fecha_dt, "responsable": responsable_txt},
        )
        rows = []
        for r in cur.fetchall() or []:
            rows.append({
                "id_articulo": int(r["id_articulo"]),
                "descripcion": r.get("descripcion") or "",
                "abc": r.get("abc") or "",
                "total_bultos": float(r.get("total_bultos") or 0),
                "total_unidades": float(r.get("total_unidades") or 0),
                "controles": int(r.get("controles") or 0),
                "responsables": r.get("responsables") or "",
                "controles_detalle": r.get("controles_detalle") or [],
            })

        cur.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (c.sucursal, c.fecha, c.responsable, c.semana, c.dia)
                    c.*
                FROM control_stock_conteos c
                WHERE c.sucursal = %(sucursal)s
                  AND c.fecha = %(fecha)s
                  AND (%(responsable)s = '' OR c.responsable = %(responsable)s)
                ORDER BY c.sucursal, c.fecha, c.responsable, c.semana, c.dia, c.updated_at DESC, c.id DESC
            )
            SELECT
                COUNT(*) AS controles,
                MIN(hora_inicio) AS hora_inicio,
                MAX(hora_fin) AS hora_fin,
                STRING_AGG(DISTINCT responsable, ', ' ORDER BY responsable) AS responsables
            FROM latest
            """,
            {"sucursal": suc, "fecha": fecha_dt, "responsable": responsable_txt},
        )
        header = dict(cur.fetchone() or {})

    return {
        "ok": True,
        "fecha": fecha_dt.isoformat(),
        "sucursal": suc,
        "sucursal_nombre": _sucursal_nombre(suc),
        "responsable": responsable_txt,
        "controles": int(header.get("controles") or 0),
        "hora_inicio": str(header.get("hora_inicio") or ""),
        "hora_fin": str(header.get("hora_fin") or ""),
        "responsables": header.get("responsables") or "",
        "total_articulos": len(rows),
        "total_bultos": round(sum(r["total_bultos"] for r in rows), 2),
        "total_unidades": round(sum(r["total_unidades"] for r in rows), 2),
        "rows": rows,
    }


def get_abc_mensual(anio: int | str | None = None, sucursal: str | None = "1") -> dict:
    today = date.today()
    year = int(anio or today.year)
    suc = _sucursal_id(sucursal)
    month_names = (
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    )
    articles: dict[int, dict] = {}
    max_month = 12 if year < today.year else max(0, min(12, today.month - 1))
    if year > today.year:
        max_month = 0

    for month in range(1, max_month + 1):
        mes_label = f"{year}-{month:02d}"
        data = get_abc_articulos(mes_label, sucursal=suc)
        for row in data["rows"]:
            article_id = int(row["id_articulo"])
            item = articles.setdefault(article_id, {
                "id_articulo": article_id,
                "descripcion": row.get("descripcion") or "",
                "negocio": row.get("negocio") or "",
                "tipo_producto": row.get("tipo_producto") or "",
                "meses": {},
            })
            if not item["descripcion"] and row.get("descripcion"):
                item["descripcion"] = row["descripcion"]
            if not item["negocio"] and row.get("negocio"):
                item["negocio"] = row["negocio"]
            if (not item["tipo_producto"] or item["tipo_producto"] == "GENERAL") and row.get("tipo_producto"):
                item["tipo_producto"] = row["tipo_producto"]
            item["meses"][month_names[month - 1]] = row.get("abc") or ""

    rows = []
    for item in articles.values():
        meses = item["meses"]
        abc_values = [meses.get(name, "") for name in month_names[:max_month]]
        loaded_values = [value for value in abc_values[:max_month] if value]
        cambios = sum(1 for prev, curr in zip(loaded_values, loaded_values[1:]) if prev != curr)
        observaciones = "Vario a lo largo del año" if cambios else "Sin variacion"
        rows.append({
            "id_articulo": item["id_articulo"],
            "descripcion": item["descripcion"],
            "negocio": item["negocio"],
            "tipo_producto": item["tipo_producto"],
            "cambios": cambios,
            "observaciones": observaciones,
            **{name: meses.get(name, "") for name in month_names},
        })

    abc_order = {"A": 0, "B": 1, "C": 2, "": 3}
    rows.sort(key=lambda r: (abc_order.get(str(r.get("enero") or ""), 3), int(r["id_articulo"])))
    return {
        "ok": True,
        "anio": year,
        "sucursal": suc,
        "sucursal_nombre": _sucursal_nombre(suc),
        "meses": list(month_names),
        "hasta_mes": max_month,
        "total_articulos": len(rows),
        "articulos_con_cambios": sum(1 for r in rows if r["cambios"] > 0),
        "rows": rows,
    }
