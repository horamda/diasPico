from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from psycopg2.extras import execute_values
from app.database import pg_conn, pg_cursor

_READY = False


def ensure_tables() -> None:
    global _READY
    if _READY:
        return
    sql_path = Path(__file__).resolve().parents[2] / "sql" / "operacion_camiones.sql"
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_path.read_text(encoding="utf-8"))
    _READY = True


def upsert_rows(rows: list[dict]) -> int:
    """Batch-upsert rows using execute_values (single round-trip). Returns rows processed."""
    ensure_tables()
    if not rows:
        return 0
    # Deduplicar: el sheet puede tener filas repetidas — quedarse con la última
    seen: dict = {}
    for r in rows:
        key = (r['empresa_id'], r['sucursal_id'], r['fecha'], r['nro_salida'], r['chofer'])
        seen[key] = r
    rows = list(seen.values())

    sync_at = datetime.now(timezone.utc)
    values = [
        (r['empresa_id'], r['sucursal_id'], r['fecha'], r['nro_salida'],
         r['chofer'], r['ayudante_1'], r['ayudante_2'], sync_at)
        for r in rows
    ]
    with pg_conn() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO operacion_camiones
                    (empresa_id, sucursal_id, fecha, nro_salida, chofer,
                     ayudante_1, ayudante_2, sync_at)
                VALUES %s
                ON CONFLICT (empresa_id, sucursal_id, fecha, nro_salida, chofer)
                DO UPDATE SET
                    ayudante_1 = EXCLUDED.ayudante_1,
                    ayudante_2 = EXCLUDED.ayudante_2,
                    sync_at    = EXCLUDED.sync_at
                """,
                values,
                page_size=500,
            )
    return len(rows)


def replace_rows(rows: list[dict], sucursal_id: str, nro_salida: int) -> int:
    """Borra todo lo de (sucursal_id, nro_salida) e inserta desde cero. Sync limpio."""
    ensure_tables()
    if not rows:
        return 0
    empresa_id = rows[0]['empresa_id']
    # Deduplicar filas del sheet
    seen: dict = {}
    for r in rows:
        key = (r['empresa_id'], r['sucursal_id'], r['fecha'], r['nro_salida'], r['chofer'])
        seen[key] = r
    rows = list(seen.values())

    sync_at = datetime.now(timezone.utc)
    values = [
        (r['empresa_id'], r['sucursal_id'], r['fecha'], r['nro_salida'],
         r['chofer'], r['ayudante_1'], r['ayudante_2'], sync_at)
        for r in rows
    ]
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM operacion_camiones WHERE empresa_id=%s AND sucursal_id=%s AND nro_salida=%s",
                (empresa_id, sucursal_id, nro_salida),
            )
            borradas = cur.rowcount
            execute_values(
                cur,
                """
                INSERT INTO operacion_camiones
                    (empresa_id, sucursal_id, fecha, nro_salida, chofer,
                     ayudante_1, ayudante_2, sync_at)
                VALUES %s
                """,
                values,
                page_size=500,
            )
    return len(rows)


def get_resumen_mensual(
    empresa_id: str,
    sucursal_id: str,
    anio: int,
    mes: int,
) -> list[dict]:
    """Returns one row per date with camiones count, salidas count, and unique people."""
    ensure_tables()
    where_suc = "AND sucursal_id = %(sucursal_id)s" if sucursal_id and sucursal_id != "TODAS" else ""
    with pg_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                fecha,
                COUNT(*)                                            AS registros,
                COUNT(DISTINCT nro_salida)                         AS salidas_distintas,
                COUNT(DISTINCT chofer)
                  + COUNT(DISTINCT ayudante_1) FILTER (WHERE ayudante_1 IS NOT NULL AND ayudante_1 <> '')
                  + COUNT(DISTINCT ayudante_2) FILTER (WHERE ayudante_2 IS NOT NULL AND ayudante_2 <> '')
                                                                   AS personas_estimadas
            FROM operacion_camiones
            WHERE empresa_id = %(empresa_id)s
              {where_suc}
              AND DATE_TRUNC('month', fecha) = DATE %(anio_mes)s
            GROUP BY fecha
            ORDER BY fecha
            """,
            {
                "empresa_id": empresa_id,
                "sucursal_id": sucursal_id,
                "anio_mes": f"{anio:04d}-{mes:02d}-01",
            },
        )
        return [dict(r) for r in cur.fetchall()]


def get_estadisticas_periodo(
    empresa_id: str,
    sucursal_id: str,
    anio: int,
    mes: int,
) -> dict:
    """
    Returns aggregate stats for a month:
    camiones_dia_promedio, salidas_total, personas_unicas, dias_con_datos.
    """
    ensure_tables()
    where_suc = "AND sucursal_id = %(sucursal_id)s" if sucursal_id and sucursal_id != "TODAS" else ""
    with pg_cursor() as cur:
        cur.execute(
            f"""
            WITH base AS (
                SELECT
                    fecha,
                    COUNT(*)           AS camiones_dia
                FROM operacion_camiones
                WHERE empresa_id = %(empresa_id)s
                  {where_suc}
                  AND DATE_TRUNC('month', fecha) = DATE %(anio_mes)s
                GROUP BY fecha
            ),
            personas AS (
                SELECT
                    COUNT(DISTINCT chofer)     AS choferes,
                    COUNT(DISTINCT ayudante_1) FILTER (WHERE ayudante_1 IS NOT NULL AND ayudante_1 <> '') AS ay1,
                    COUNT(DISTINCT ayudante_2) FILTER (WHERE ayudante_2 IS NOT NULL AND ayudante_2 <> '') AS ay2
                FROM operacion_camiones
                WHERE empresa_id = %(empresa_id)s
                  {where_suc}
                  AND DATE_TRUNC('month', fecha) = DATE %(anio_mes)s
            )
            SELECT
                COALESCE(ROUND(AVG(b.camiones_dia), 1), 0)::float AS camiones_dia_promedio,
                COALESCE(SUM(b.camiones_dia), 0)::int              AS salidas_total,
                COALESCE(COUNT(*), 0)::int                         AS dias_con_datos,
                COALESCE((p.choferes + p.ay1 + p.ay2), 0)::int    AS personas_unicas
            FROM base b, personas p
            GROUP BY p.choferes, p.ay1, p.ay2
            """,
            {
                "empresa_id": empresa_id,
                "sucursal_id": sucursal_id,
                "anio_mes": f"{anio:04d}-{mes:02d}-01",
            },
        )
        row = cur.fetchone()
        if row:
            return dict(row)
        return {
            "camiones_dia_promedio": 0.0,
            "salidas_total": 0,
            "dias_con_datos": 0,
            "personas_unicas": 0,
        }


def get_anios_disponibles(empresa_id: str) -> dict:
    """Retorna años y meses con datos, más la fecha mínima y máxima."""
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT
                EXTRACT(YEAR  FROM fecha)::int AS anio,
                EXTRACT(MONTH FROM fecha)::int AS mes,
                COUNT(*) AS registros
            FROM operacion_camiones
            WHERE empresa_id = %(empresa_id)s
            GROUP BY anio, mes
            ORDER BY anio DESC, mes DESC
            """,
            {"empresa_id": empresa_id},
        )
        rows = [dict(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT MIN(fecha) AS min_fecha, MAX(fecha) AS max_fecha "
            "FROM operacion_camiones WHERE empresa_id = %(empresa_id)s",
            {"empresa_id": empresa_id},
        )
        rango = dict(cur.fetchone() or {})

    return {
        "periodos": rows,
        "min_fecha": rango.get("min_fecha").isoformat() if rango.get("min_fecha") else None,
        "max_fecha": rango.get("max_fecha").isoformat() if rango.get("max_fecha") else None,
        "anio_mas_reciente": rows[0]["anio"] if rows else None,
        "mes_mas_reciente":  rows[0]["mes"]  if rows else None,
    }


def get_detalle_mensual(
    empresa_id: str,
    sucursal_id: str,
    anio: int,
    mes: int,
) -> list[dict]:
    """
    Returns one row per (sucursal_id, fecha, nro_salida) with:
    camiones, choferes, ayudantes, personas (chofer + ayudantes por turno).
    nro_salida: 1 = primera salida, 2 = segunda salida.
    """
    ensure_tables()
    where_suc = "AND sucursal_id = %(sucursal_id)s" if sucursal_id and sucursal_id != "TODAS" else ""
    with pg_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                sucursal_id,
                fecha,
                nro_salida,
                COUNT(*)                                                             AS camiones,
                COUNT(DISTINCT chofer)                                               AS choferes,
                COUNT(ayudante_1) FILTER (WHERE ayudante_1 IS NOT NULL AND ayudante_1 <> '') +
                COUNT(ayudante_2) FILTER (WHERE ayudante_2 IS NOT NULL AND ayudante_2 <> '')
                                                                                     AS ayudantes,
                COUNT(*) +
                COUNT(ayudante_1) FILTER (WHERE ayudante_1 IS NOT NULL AND ayudante_1 <> '') +
                COUNT(ayudante_2) FILTER (WHERE ayudante_2 IS NOT NULL AND ayudante_2 <> '')
                                                                                     AS personas
            FROM operacion_camiones
            WHERE empresa_id = %(empresa_id)s
              {where_suc}
              AND DATE_TRUNC('month', fecha) = DATE %(anio_mes)s
            GROUP BY sucursal_id, fecha, nro_salida
            ORDER BY sucursal_id, fecha, nro_salida
            """,
            {
                "empresa_id": empresa_id,
                "sucursal_id": sucursal_id,
                "anio_mes": f"{anio:04d}-{mes:02d}-01",
            },
        )
        rows = cur.fetchall()
        return [
            {**dict(r), "fecha": r["fecha"].isoformat()}
            for r in rows
        ]
