from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from psycopg2 import sql

from app.database import pg_conn, pg_cursor


DATASETS = {
    "resumen": {
        "label": "Resumen de repartos",
        "table": "repartos_resumen",
        "date_col": "fecha_reparto",
    },
    "detalle": {
        "label": "Detalle de entregas",
        "table": "repartos_detalle",
        "date_col": "fecha_entrega_planilla",
    },
    "ventas": {
        "label": "Detalle ventas y rechazos",
        "table": "ventas_detalle",
        "date_col": "fecha",
    },
}


def _dataset(name: str) -> dict:
    key = str(name or "").strip().lower()
    if key not in DATASETS:
        raise ValueError("Bajada Foxtrot no valida")
    return DATASETS[key]


def _to_json_value(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _columns(table: str) -> list[dict]:
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, udt_name, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        rows = [dict(r) for r in cur.fetchall() or []]
    if not rows:
        raise ValueError(f"La tabla {table} no existe o no tiene columnas")
    return [
        {
            "name": r["column_name"],
            "type": r["data_type"],
            "udt": r["udt_name"],
            "nullable": r["is_nullable"] == "YES",
            "editable": r["column_name"] != "id",
        }
        for r in rows
    ]


def list_datasets() -> dict:
    data = []
    for key, cfg in DATASETS.items():
        item = {"key": key, "label": cfg["label"], "table": cfg["table"], "date_col": cfg["date_col"]}
        try:
            cols = _columns(cfg["table"])
            item["exists"] = True
            item["columns"] = len(cols)
        except Exception:
            item["exists"] = False
            item["columns"] = 0
        data.append(item)
    return {"ok": True, "datasets": data}


def list_rows(name: str, desde: str | None, hasta: str | None, sucursal: str | None, limit: int = 200) -> dict:
    cfg = _dataset(name)
    table = cfg["table"]
    date_col = cfg["date_col"]
    cols = _columns(table)
    col_names = [c["name"] for c in cols]
    limit = max(1, min(int(limit or 200), 1000))

    where = []
    params = {}
    if desde:
        where.append(sql.SQL("{} >= %(desde)s").format(sql.Identifier(date_col)))
        params["desde"] = desde
    if hasta:
        where.append(sql.SQL("{} <= %(hasta)s").format(sql.Identifier(date_col)))
        params["hasta"] = hasta
    if sucursal and sucursal != "TODAS" and "sucursal" in col_names:
        where.append(sql.SQL("COALESCE(NULLIF(TRIM(sucursal), ''), '1') = %(sucursal)s"))
        params["sucursal"] = sucursal
    params["limit"] = limit

    query = sql.SQL("SELECT * FROM {}").format(sql.Identifier(table))
    if where:
        query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where)
    order_parts = []
    if date_col in col_names:
        order_parts.append(sql.SQL("{} DESC").format(sql.Identifier(date_col)))
    if "id" in col_names:
        order_parts.append(sql.SQL("id DESC"))
    if order_parts:
        query += sql.SQL(" ORDER BY ") + sql.SQL(", ").join(order_parts)
    query += sql.SQL(" LIMIT %(limit)s")

    with pg_cursor() as cur:
        cur.execute(query, params)
        rows = [
            {k: _to_json_value(v) for k, v in dict(r).items()}
            for r in cur.fetchall() or []
        ]

    return {
        "ok": True,
        "dataset": name,
        "label": cfg["label"],
        "table": table,
        "date_col": date_col,
        "columns": cols,
        "rows": rows,
        "total": len(rows),
    }


def update_row(name: str, row_id: int, values: dict) -> dict:
    cfg = _dataset(name)
    table = cfg["table"]
    cols = _columns(table)
    editable = {c["name"]: c for c in cols if c["editable"]}
    updates = {k: (None if v == "" else v) for k, v in (values or {}).items() if k in editable}
    if not updates:
        raise ValueError("No hay campos editables para guardar")

    assignments = [
        sql.SQL("{} = %({})s").format(sql.Identifier(col), sql.SQL(col))
        for col in updates
    ]
    params = dict(updates)
    params["id"] = int(row_id)
    query = (
        sql.SQL("UPDATE {} SET ").format(sql.Identifier(table))
        + sql.SQL(", ").join(assignments)
        + sql.SQL(" WHERE id = %(id)s RETURNING *")
    )
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            if not row:
                raise ValueError("Fila no encontrada")
            columns = [desc[0] for desc in cur.description]
            data = {columns[i]: _to_json_value(row[i]) for i in range(len(columns))}
    return {"ok": True, "dataset": name, "id": row_id, "row": data}
