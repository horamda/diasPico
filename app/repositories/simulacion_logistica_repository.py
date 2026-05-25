from __future__ import annotations

import json
from pathlib import Path

from app.database import pg_conn, pg_cursor

_READY = False


def ensure_tables() -> None:
    global _READY
    if _READY:
        return
    sql_path = Path(__file__).resolve().parents[2] / "sql" / "simulaciones_logisticas.sql"
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_path.read_text(encoding="utf-8"))
    _READY = True


# ── Datos base históricos ────────────────────────────────────────────────────

def get_base_mensual(empresa_id: str, sucursal_id: str, anio: int, mes: int) -> dict | None:
    """Retorna las estadísticas mensuales del período indicado desde planificacion_estadistica_diaria."""
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT
                empresa_id,
                sucursal_id,
                anio,
                mes,
                COUNT(*) AS dias_con_datos,
                COALESCE(SUM(hl), 0)      AS hl,
                COALESCE(SUM(bultos), 0)  AS bultos,
                COALESCE(SUM(pallets), 0) AS pallets,
                COALESCE(SUM(salidas), 0) AS salidas,
                COALESCE(SUM(pdv_unicos), 0) AS pdv_unicos,
                COALESCE(SUM(CASE WHEN es_dia_pico THEN 1 ELSE 0 END), 0) AS dias_pico,
                COALESCE(AVG(NULLIF(camiones_promedio, 0)), 0) AS camiones_promedio,
                COALESCE(MAX(camiones_pico), 0)                AS camiones_pico,
                COALESCE(AVG(NULLIF(empleados_normales, 0)), 0) AS empleados_normales,
                COALESCE(MAX(empleados_pico), 0)               AS empleados_pico,
                COALESCE(SUM(rechazos_pct * hl) / NULLIF(SUM(hl), 0), 0) AS rechazos_pct
            FROM planificacion_estadistica_diaria
            WHERE empresa_id  = %(empresa_id)s
              AND sucursal_id = %(sucursal_id)s
              AND anio = %(anio)s
              AND mes  = %(mes)s
            GROUP BY empresa_id, sucursal_id, anio, mes
            """,
            {"empresa_id": empresa_id, "sucursal_id": sucursal_id, "anio": anio, "mes": mes},
        )
        row = cur.fetchone()
    return dict(row) if row else None


# ── CRUD simulaciones ────────────────────────────────────────────────────────

def save_simulacion(data: dict) -> dict:
    ensure_tables()
    recom = data.get("recomendaciones_json")
    if isinstance(recom, list):
        recom = json.dumps(recom, ensure_ascii=False)
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO simulaciones_logisticas (
                empresa_id, sucursal_id, anio, mes, anio_base, mes_base,
                crecimiento_esperado, ausentismo_esperado, camiones_disponibles,
                dias_trabajados, dias_pico_esperados,
                hl_base, bultos_base, pallets_base, up_base, pdv_base,
                salidas_base, camiones_base, personas_base, rechazos_base,
                dropsize_base, dias_trabajados_base, dias_pico_base,
                hl_plan, bultos_plan, pallets_plan, up_plan, pdv_plan,
                salidas_necesarias, camiones_necesarios, personas_necesarias,
                camiones_dia_pico, personas_dia_pico, salidas_dia_pico,
                camiones_adicionales,
                riesgo_score, riesgo_nivel, recomendaciones_json,
                estado, observaciones, updated_at
            ) VALUES (
                %(empresa_id)s, %(sucursal_id)s, %(anio)s, %(mes)s,
                %(anio_base)s, %(mes_base)s,
                %(crecimiento_esperado)s, %(ausentismo_esperado)s, %(camiones_disponibles)s,
                %(dias_trabajados)s, %(dias_pico_esperados)s,
                %(hl_base)s, %(bultos_base)s, %(pallets_base)s, %(up_base)s, %(pdv_base)s,
                %(salidas_base)s, %(camiones_base)s, %(personas_base)s, %(rechazos_base)s,
                %(dropsize_base)s, %(dias_trabajados_base)s, %(dias_pico_base)s,
                %(hl_plan)s, %(bultos_plan)s, %(pallets_plan)s, %(up_plan)s, %(pdv_plan)s,
                %(salidas_necesarias)s, %(camiones_necesarios)s, %(personas_necesarias)s,
                %(camiones_dia_pico)s, %(personas_dia_pico)s, %(salidas_dia_pico)s,
                %(camiones_adicionales)s,
                %(riesgo_score)s, %(riesgo_nivel)s, %(recomendaciones_json)s,
                %(estado)s, %(observaciones)s, NOW()
            )
            RETURNING *
            """,
            {**data, "recomendaciones_json": recom, "estado": data.get("estado", "ABIERTA")},
        )
        return dict(cur.fetchone())


def get_simulacion(simulacion_id: int) -> dict | None:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            "SELECT * FROM simulaciones_logisticas WHERE id = %s",
            (simulacion_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    r = dict(row)
    if r.get("recomendaciones_json") and isinstance(r["recomendaciones_json"], str):
        try:
            r["recomendaciones"] = json.loads(r["recomendaciones_json"])
        except Exception:
            r["recomendaciones"] = []
    return r


def list_simulaciones(
    empresa_id: str = "1",
    sucursal_id: str | None = None,
    limit: int = 30,
) -> list[dict]:
    ensure_tables()
    where = ["empresa_id = %(empresa_id)s"]
    params: dict = {"empresa_id": empresa_id, "limit": int(limit)}
    if sucursal_id and sucursal_id != "TODAS":
        where.append("sucursal_id = %(sucursal_id)s")
        params["sucursal_id"] = sucursal_id
    sql = f"""
        SELECT id, empresa_id, sucursal_id, anio, mes, anio_base, mes_base,
               crecimiento_esperado, ausentismo_esperado, camiones_disponibles,
               dias_trabajados, dias_pico_esperados,
               hl_plan, bultos_plan, pallets_plan, pdv_plan,
               camiones_necesarios, personas_necesarias,
               camiones_dia_pico, personas_dia_pico,
               camiones_adicionales, riesgo_score, riesgo_nivel, estado,
               created_at, updated_at
        FROM simulaciones_logisticas
        WHERE {' AND '.join(where)}
        ORDER BY anio DESC, mes DESC, id DESC
        LIMIT %(limit)s
    """
    with pg_cursor() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def update_estado(simulacion_id: int, estado: str) -> None:
    ensure_tables()
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE simulaciones_logisticas SET estado=%s, updated_at=NOW() WHERE id=%s",
                (estado, simulacion_id),
            )


# ── Avance mensual ───────────────────────────────────────────────────────────

def save_avance(data: dict) -> dict:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO avances_simulaciones_logisticas (
                simulacion_id, dias_transcurridos,
                hl_real, bultos_real, pallets_real, pdv_real,
                salidas_real, camiones_real, personas_real, rechazos_real,
                avance_esperado,
                dispersion_hl_pct, dispersion_bultos_pct, dispersion_pallets_pct,
                dispersion_pdv_pct, dispersion_salidas_pct,
                dispersion_camiones_pct, dispersion_personas_pct,
                dispersion_rechazos_pct
            ) VALUES (
                %(simulacion_id)s, %(dias_transcurridos)s,
                %(hl_real)s, %(bultos_real)s, %(pallets_real)s, %(pdv_real)s,
                %(salidas_real)s, %(camiones_real)s, %(personas_real)s, %(rechazos_real)s,
                %(avance_esperado)s,
                %(dispersion_hl_pct)s, %(dispersion_bultos_pct)s, %(dispersion_pallets_pct)s,
                %(dispersion_pdv_pct)s, %(dispersion_salidas_pct)s,
                %(dispersion_camiones_pct)s, %(dispersion_personas_pct)s,
                %(dispersion_rechazos_pct)s
            )
            RETURNING *
            """,
            data,
        )
        return dict(cur.fetchone())


def get_avances(simulacion_id: int) -> list[dict]:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            "SELECT * FROM avances_simulaciones_logisticas WHERE simulacion_id=%s ORDER BY created_at",
            (simulacion_id,),
        )
        return [dict(r) for r in cur.fetchall()]


# ── Cierre mensual ───────────────────────────────────────────────────────────

def save_cierre(data: dict) -> dict:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO cierres_simulaciones_logisticas (
                simulacion_id,
                hl_real, bultos_real, pallets_real, up_real, pdv_real,
                salidas_real, camiones_real, personas_real, rechazos_real,
                dias_pico_real, ausentismo_real, dropsize_real,
                error_hl_pct, error_bultos_pct, error_pallets_pct,
                error_pdv_pct, error_salidas_pct, error_camiones_pct,
                error_personas_pct, error_rechazos_pct,
                conclusiones
            ) VALUES (
                %(simulacion_id)s,
                %(hl_real)s, %(bultos_real)s, %(pallets_real)s, %(up_real)s, %(pdv_real)s,
                %(salidas_real)s, %(camiones_real)s, %(personas_real)s, %(rechazos_real)s,
                %(dias_pico_real)s, %(ausentismo_real)s, %(dropsize_real)s,
                %(error_hl_pct)s, %(error_bultos_pct)s, %(error_pallets_pct)s,
                %(error_pdv_pct)s, %(error_salidas_pct)s, %(error_camiones_pct)s,
                %(error_personas_pct)s, %(error_rechazos_pct)s,
                %(conclusiones)s
            )
            ON CONFLICT (simulacion_id) DO UPDATE SET
                hl_real=EXCLUDED.hl_real,
                bultos_real=EXCLUDED.bultos_real,
                pallets_real=EXCLUDED.pallets_real,
                up_real=EXCLUDED.up_real,
                pdv_real=EXCLUDED.pdv_real,
                salidas_real=EXCLUDED.salidas_real,
                camiones_real=EXCLUDED.camiones_real,
                personas_real=EXCLUDED.personas_real,
                rechazos_real=EXCLUDED.rechazos_real,
                dias_pico_real=EXCLUDED.dias_pico_real,
                ausentismo_real=EXCLUDED.ausentismo_real,
                dropsize_real=EXCLUDED.dropsize_real,
                error_hl_pct=EXCLUDED.error_hl_pct,
                error_bultos_pct=EXCLUDED.error_bultos_pct,
                error_pallets_pct=EXCLUDED.error_pallets_pct,
                error_pdv_pct=EXCLUDED.error_pdv_pct,
                error_salidas_pct=EXCLUDED.error_salidas_pct,
                error_camiones_pct=EXCLUDED.error_camiones_pct,
                error_personas_pct=EXCLUDED.error_personas_pct,
                error_rechazos_pct=EXCLUDED.error_rechazos_pct,
                conclusiones=EXCLUDED.conclusiones
            RETURNING *
            """,
            data,
        )
        return dict(cur.fetchone())


def get_cierre(simulacion_id: int) -> dict | None:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            "SELECT * FROM cierres_simulaciones_logisticas WHERE simulacion_id=%s",
            (simulacion_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


# ── Aprendizaje ──────────────────────────────────────────────────────────────

def save_aprendizaje(data: dict) -> dict:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO aprendizaje_simulaciones_logisticas (
                empresa_id, sucursal_id, mes, anio, simulacion_id,
                error_hl_pct, error_camiones_pct, error_personas_pct, error_salidas_pct,
                factor_ajuste_hl, factor_ajuste_camiones,
                factor_ajuste_personas, factor_ajuste_salidas
            ) VALUES (
                %(empresa_id)s, %(sucursal_id)s, %(mes)s, %(anio)s, %(simulacion_id)s,
                %(error_hl_pct)s, %(error_camiones_pct)s, %(error_personas_pct)s,
                %(error_salidas_pct)s,
                %(factor_ajuste_hl)s, %(factor_ajuste_camiones)s,
                %(factor_ajuste_personas)s, %(factor_ajuste_salidas)s
            )
            RETURNING *
            """,
            data,
        )
        return dict(cur.fetchone())


def get_aprendizaje(empresa_id: str, sucursal_id: str, mes: int, n: int = 3) -> dict:
    """Promedio de factores de ajuste de los últimos N cierres para esa sucursal+mes."""
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT
                AVG(factor_ajuste_hl)        AS factor_ajuste_hl,
                AVG(factor_ajuste_camiones)  AS factor_ajuste_camiones,
                AVG(factor_ajuste_personas)  AS factor_ajuste_personas,
                AVG(factor_ajuste_salidas)   AS factor_ajuste_salidas,
                COUNT(*)                     AS registros
            FROM (
                SELECT factor_ajuste_hl, factor_ajuste_camiones,
                       factor_ajuste_personas, factor_ajuste_salidas
                FROM aprendizaje_simulaciones_logisticas
                WHERE empresa_id  = %(empresa_id)s
                  AND sucursal_id = %(sucursal_id)s
                  AND mes = %(mes)s
                ORDER BY anio DESC, id DESC
                LIMIT %(n)s
            ) sub
            """,
            {"empresa_id": empresa_id, "sucursal_id": sucursal_id, "mes": mes, "n": n},
        )
        row = cur.fetchone()
    return dict(row) if row else {}
