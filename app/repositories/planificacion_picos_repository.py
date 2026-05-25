from __future__ import annotations

import calendar as cal_mod
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

from psycopg2.extras import execute_values

from app.database import pg_conn, pg_cursor
from app.services.pico_svc import (
    IS_MERCADERIA,
    V_CLIENT_KEY,
    V_IS_REC,
    V_NOT_REMITO,
    V_PALLETS_EXPR,
    V_REC_JOIN,
    V_TRUCK_KEY,
)


_READY = False


def ensure_tables() -> None:
    global _READY
    if _READY:
        return
    sql_path = Path(__file__).resolve().parents[2] / "sql" / "planificacion_picos.sql"
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_path.read_text(encoding="utf-8"))
    _READY = True


def _month_bounds(anio: int, mes: int) -> tuple[date, date]:
    return date(anio, mes, 1), date(anio, mes, cal_mod.monthrange(anio, mes)[1])


def _empresa_filter(empresa_id: str) -> str:
    if empresa_id == "TODAS":
        return ""
    return "AND COALESCE(NULLIF(TRIM(v.empresa), ''), '1') = %(empresa_id)s"


def _sucursal_filter(sucursal_id: str) -> str:
    if sucursal_id == "TODAS":
        return ""
    return "AND COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') = %(sucursal_id)s"


def recalcular_estadisticas_diarias(
    empresa_id: str,
    sucursal_id: str,
    anio: int,
    mes: int,
    config: dict,
) -> dict:
    ensure_tables()
    ini, fin = _month_bounds(anio, mes)
    params = {
        "empresa_id": empresa_id,
        "sucursal_id": sucursal_id,
        "ini": ini,
        "fin": fin,
        "umbral_hl": float(config.get("umbral_pico_hl_pct") or 20),
        "umbral_salidas": float(config.get("umbral_pico_salidas_pct") or 20),
        "umbral_pdv": float(config.get("umbral_pico_pdv_pct") or 20),
    }
    emp_expr = (
        "'TODAS'"
        if empresa_id == "TODAS"
        else "COALESCE(NULLIF(TRIM(v.empresa), ''), '1')"
    )
    suc_expr = (
        "'TODAS'"
        if sucursal_id == "TODAS"
        else "COALESCE(NULLIF(TRIM(v.sucursal), ''), '1')"
    )
    group_exprs = []
    if empresa_id != "TODAS":
        group_exprs.append(emp_expr)
    if sucursal_id != "TODAS":
        group_exprs.append(suc_expr)
    group_exprs.append("v.fecha::date")
    group_by_daily = ", ".join(group_exprs)
    delete_empresa = "" if empresa_id == "TODAS" else "AND empresa_id = %(empresa_id)s"
    delete_sucursal = "AND sucursal_id = %(sucursal_id)s"

    with pg_cursor() as cur:
        cur.execute(
            f"""
            DELETE FROM planificacion_estadistica_diaria
            WHERE fecha BETWEEN %(ini)s AND %(fin)s
              {delete_empresa}
              {delete_sucursal}
            """,
            params,
        )
        cur.execute(
            f"""
            WITH daily AS (
                SELECT
                    {emp_expr} AS empresa_id,
                    {suc_expr} AS sucursal_id,
                    v.fecha::date AS fecha,
                    COALESCE(SUM(COALESCE(v.unidad_medida, 0)), 0) AS hl,
                    COALESCE(SUM(COALESCE(v.bultos, 0)), 0) AS bultos,
                    COALESCE(SUM({V_PALLETS_EXPR}), 0) AS pallets,
                    COALESCE(SUM(CASE WHEN {V_IS_REC} THEN COALESCE(v.unidad_medida_rechazado, 0) ELSE 0 END), 0) AS hl_rechazo,
                    COUNT(DISTINCT {V_TRUCK_KEY}) AS salidas,
                    COUNT(DISTINCT {V_CLIENT_KEY}) AS pdv_unicos
                FROM ventas_detalle v
                LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
                {V_REC_JOIN}
                WHERE v.fecha BETWEEN %(ini)s AND %(fin)s
                  {_empresa_filter(empresa_id)}
                  {_sucursal_filter(sucursal_id)}
                  AND {IS_MERCADERIA}
                  AND {V_NOT_REMITO}
                GROUP BY {group_by_daily}
            ),
            monthly AS (
                SELECT
                    empresa_id,
                    sucursal_id,
                    AVG(NULLIF(hl, 0)) AS avg_hl,
                    AVG(NULLIF(salidas, 0)) AS avg_salidas,
                    AVG(NULLIF(pdv_unicos, 0)) AS avg_pdv
                FROM daily
                GROUP BY empresa_id, sucursal_id
            ),
            enriched AS (
                SELECT
                    d.*,
                    (
                        (COALESCE(m.avg_hl, 0) > 0 AND d.hl > COALESCE(m.avg_hl, 0) * (1 + %(umbral_hl)s / 100.0))
                        OR (COALESCE(m.avg_salidas, 0) > 0 AND d.salidas > COALESCE(m.avg_salidas, 0) * (1 + %(umbral_salidas)s / 100.0))
                        OR (COALESCE(m.avg_pdv, 0) > 0 AND d.pdv_unicos > COALESCE(m.avg_pdv, 0) * (1 + %(umbral_pdv)s / 100.0))
                    ) AS es_dia_pico
                FROM daily d
                JOIN monthly m ON m.empresa_id = d.empresa_id AND m.sucursal_id = d.sucursal_id
            )
            INSERT INTO planificacion_estadistica_diaria (
                empresa_id, sucursal_id, fecha, anio, mes, dia,
                hl, bultos, pallets, rechazos_pct, salidas, pdv_unicos,
                camiones_promedio, camiones_pico,
                empleados_normales, empleados_pico, es_dia_pico, updated_at
            )
            SELECT
                empresa_id,
                sucursal_id,
                fecha,
                EXTRACT(YEAR FROM fecha)::smallint,
                EXTRACT(MONTH FROM fecha)::smallint,
                EXTRACT(DAY FROM fecha)::smallint,
                hl,
                bultos,
                pallets,
                CASE WHEN hl > 0 THEN hl_rechazo / hl * 100 ELSE 0 END,
                salidas,
                pdv_unicos,
                salidas,
                CASE WHEN es_dia_pico THEN salidas ELSE 0 END,
                0,
                0,
                es_dia_pico,
                NOW()
            FROM enriched
            ON CONFLICT (empresa_id, sucursal_id, fecha) DO UPDATE SET
                anio=EXCLUDED.anio,
                mes=EXCLUDED.mes,
                dia=EXCLUDED.dia,
                hl=EXCLUDED.hl,
                bultos=EXCLUDED.bultos,
                pallets=EXCLUDED.pallets,
                rechazos_pct=EXCLUDED.rechazos_pct,
                salidas=EXCLUDED.salidas,
                pdv_unicos=EXCLUDED.pdv_unicos,
                camiones_promedio=EXCLUDED.camiones_promedio,
                camiones_pico=EXCLUDED.camiones_pico,
                empleados_normales=EXCLUDED.empleados_normales,
                empleados_pico=EXCLUDED.empleados_pico,
                es_dia_pico=EXCLUDED.es_dia_pico,
                updated_at=NOW()
            """,
            params,
        )
        return {
            "empresa_id": empresa_id,
            "sucursal_id": sucursal_id,
            "anio": anio,
            "mes": mes,
            "registros": cur.rowcount,
        }


def obtener_configuracion(empresa_id: str, sucursal_id: str | None) -> dict:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM configuracion_picos
            WHERE activo = TRUE
              AND empresa_id = %(empresa_id)s
              AND (sucursal_id IS NULL OR sucursal_id = %(sucursal_id)s)
            ORDER BY (sucursal_id = %(sucursal_id)s) DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            {"empresa_id": empresa_id, "sucursal_id": None if sucursal_id == "TODAS" else sucursal_id},
        )
        row = cur.fetchone()
    return dict(row) if row else {
        "empresa_id": empresa_id,
        "sucursal_id": None if sucursal_id == "TODAS" else sucursal_id,
        "umbral_pico_hl_pct": 20,
        "umbral_pico_salidas_pct": 20,
        "umbral_pico_pdv_pct": 20,
        "umbral_alerta_desvio_pct": 15,
        "umbral_critico_desvio_pct": 30,
        "peso_pico_hl": 0.45,
        "peso_pico_salidas": 0.30,
        "peso_pico_pdv": 0.20,
        "activo": True,
    }


def guardar_configuracion(data: dict) -> dict:
    ensure_tables()
    sucursal_id = data.get("sucursal_id")
    if sucursal_id == "TODAS":
        sucursal_id = None
    params = {
        "empresa_id": str(data.get("empresa_id") or "1"),
        "sucursal_id": sucursal_id,
        "umbral_pico_hl_pct": float(data.get("umbral_pico_hl_pct") or 20),
        "umbral_pico_salidas_pct": float(data.get("umbral_pico_salidas_pct") or 20),
        "umbral_pico_pdv_pct": float(data.get("umbral_pico_pdv_pct") or 20),
        "umbral_alerta_desvio_pct": float(data.get("umbral_alerta_desvio_pct") or 15),
        "umbral_critico_desvio_pct": float(data.get("umbral_critico_desvio_pct") or 30),
        "peso_pico_hl": float(data.get("peso_pico_hl") or 0.45),
        "peso_pico_salidas": float(data.get("peso_pico_salidas") or 0.30),
        "peso_pico_pdv": float(data.get("peso_pico_pdv") or 0.20),
        "activo": bool(data.get("activo", True)),
    }
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO configuracion_picos (
                empresa_id, sucursal_id,
                umbral_pico_hl_pct, umbral_pico_salidas_pct, umbral_pico_pdv_pct,
                umbral_alerta_desvio_pct, umbral_critico_desvio_pct,
                peso_pico_hl, peso_pico_salidas, peso_pico_pdv,
                activo, updated_at
            )
            VALUES (
                %(empresa_id)s, %(sucursal_id)s,
                %(umbral_pico_hl_pct)s, %(umbral_pico_salidas_pct)s, %(umbral_pico_pdv_pct)s,
                %(umbral_alerta_desvio_pct)s, %(umbral_critico_desvio_pct)s,
                %(peso_pico_hl)s, %(peso_pico_salidas)s, %(peso_pico_pdv)s,
                %(activo)s, NOW()
            )
            ON CONFLICT (empresa_id, sucursal_id) DO UPDATE SET
                umbral_pico_hl_pct=EXCLUDED.umbral_pico_hl_pct,
                umbral_pico_salidas_pct=EXCLUDED.umbral_pico_salidas_pct,
                umbral_pico_pdv_pct=EXCLUDED.umbral_pico_pdv_pct,
                umbral_alerta_desvio_pct=EXCLUDED.umbral_alerta_desvio_pct,
                umbral_critico_desvio_pct=EXCLUDED.umbral_critico_desvio_pct,
                peso_pico_hl=EXCLUDED.peso_pico_hl,
                peso_pico_salidas=EXCLUDED.peso_pico_salidas,
                peso_pico_pdv=EXCLUDED.peso_pico_pdv,
                activo=EXCLUDED.activo,
                updated_at=NOW()
            RETURNING *
            """,
            params,
        )
        return dict(cur.fetchone())


def obtener_factor_estacionalidad(empresa_id: str, sucursal_id: str, mes: int) -> dict:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM factor_estacionalidad
            WHERE activo = TRUE
              AND empresa_id = %(empresa_id)s
              AND mes = %(mes)s
              AND (sucursal_id IS NULL OR sucursal_id = %(sucursal_id)s)
            ORDER BY (sucursal_id = %(sucursal_id)s) DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            {"empresa_id": empresa_id, "sucursal_id": None if sucursal_id == "TODAS" else sucursal_id, "mes": mes},
        )
        row = cur.fetchone()
    return dict(row) if row else {
        "empresa_id": empresa_id,
        "sucursal_id": None if sucursal_id == "TODAS" else sucursal_id,
        "mes": mes,
        "factor_hl": 1,
        "factor_pdv": 1,
        "factor_salidas": 1,
        "factor_camiones": 1,
        "factor_empleados": 1,
    }


def listar_factores(empresa_id: str = "1", sucursal_id: str | None = None) -> list[dict]:
    ensure_tables()
    params = {"empresa_id": empresa_id, "sucursal_id": None if sucursal_id == "TODAS" else sucursal_id}
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM factor_estacionalidad
            WHERE empresa_id = %(empresa_id)s
              AND (sucursal_id IS NULL OR sucursal_id = %(sucursal_id)s)
            ORDER BY mes, sucursal_id NULLS FIRST
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]


def guardar_factor(data: dict) -> dict:
    ensure_tables()
    sucursal_id = data.get("sucursal_id")
    if sucursal_id == "TODAS":
        sucursal_id = None
    params = {
        "empresa_id": str(data.get("empresa_id") or "1"),
        "sucursal_id": sucursal_id,
        "mes": int(data.get("mes")),
        "factor_hl": float(data.get("factor_hl") or 1),
        "factor_pdv": float(data.get("factor_pdv") or 1),
        "factor_salidas": float(data.get("factor_salidas") or 1),
        "activo": bool(data.get("activo", True)),
    }
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO factor_estacionalidad (
                empresa_id, sucursal_id, mes, factor_hl, factor_pdv, factor_salidas, activo, updated_at
            )
            VALUES (
                %(empresa_id)s, %(sucursal_id)s, %(mes)s, %(factor_hl)s, %(factor_pdv)s,
                %(factor_salidas)s, %(activo)s, NOW()
            )
            ON CONFLICT (empresa_id, sucursal_id, mes) DO UPDATE SET
                factor_hl=EXCLUDED.factor_hl,
                factor_pdv=EXCLUDED.factor_pdv,
                factor_salidas=EXCLUDED.factor_salidas,
                activo=EXCLUDED.activo,
                updated_at=NOW()
            RETURNING *
            """,
            params,
        )
        return dict(cur.fetchone())


def listar_variables(empresa_id: str = "1", sucursal_id: str | None = "TODAS", solo_activas: bool = True) -> list[dict]:
    ensure_tables()
    sucursal_id = sucursal_id or "TODAS"
    params = {"empresa_id": empresa_id, "sucursal_id": sucursal_id}
    activo_sql = "AND activo = TRUE" if solo_activas else ""
    with pg_cursor() as cur:
        cur.execute(
            f"""
            SELECT *
            FROM planificacion_variables
            WHERE empresa_id = %(empresa_id)s
              AND (sucursal_id IS NULL OR sucursal_id = 'TODAS' OR sucursal_id = %(sucursal_id)s)
              {activo_sql}
            ORDER BY activo DESC, categoria NULLS LAST, codigo
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]


def guardar_variable(data: dict) -> dict:
    ensure_tables()
    params = {
        "empresa_id": str(data.get("empresa_id") or "1"),
        "sucursal_id": data.get("sucursal_id") or "TODAS",
        "codigo": str(data.get("codigo") or "").strip().upper(),
        "nombre": str(data.get("nombre") or "").strip(),
        "categoria": str(data.get("categoria") or "OPERACION").strip().upper(),
        "unidad": str(data.get("unidad") or "").strip().upper(),
        "activo": bool(data.get("activo", True)),
    }
    if not params["codigo"]:
        raise ValueError("codigo requerido")
    if not params["nombre"]:
        raise ValueError("nombre requerido")
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO planificacion_variables (
                empresa_id, sucursal_id, codigo, nombre, categoria, unidad, activo, updated_at
            )
            VALUES (
                %(empresa_id)s, %(sucursal_id)s, %(codigo)s, %(nombre)s,
                %(categoria)s, %(unidad)s, %(activo)s, NOW()
            )
            ON CONFLICT (empresa_id, sucursal_id, codigo) DO UPDATE SET
                nombre=EXCLUDED.nombre,
                categoria=EXCLUDED.categoria,
                unidad=EXCLUDED.unidad,
                activo=EXCLUDED.activo,
                updated_at=NOW()
            RETURNING *
            """,
            params,
        )
        return dict(cur.fetchone())


def guardar_variable_valor(data: dict) -> dict:
    ensure_tables()
    params = {
        "variable_id": int(data.get("variable_id")),
        "empresa_id": str(data.get("empresa_id") or "1"),
        "sucursal_id": str(data.get("sucursal_id") or "TODAS"),
        "fecha": data.get("fecha"),
        "valor": None if data.get("valor") in (None, "") else float(data.get("valor")),
        "origen": str(data.get("origen") or "MANUAL").strip().upper(),
    }
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO planificacion_variables_valores (
                variable_id, empresa_id, sucursal_id, fecha, valor, origen, updated_at
            )
            VALUES (
                %(variable_id)s, %(empresa_id)s, %(sucursal_id)s, %(fecha)s,
                %(valor)s, %(origen)s, NOW()
            )
            ON CONFLICT (variable_id, empresa_id, sucursal_id, fecha, origen) DO UPDATE SET
                valor=EXCLUDED.valor,
                updated_at=NOW()
            RETURNING *
            """,
            params,
        )
        return dict(cur.fetchone())


def obtener_variables_plan(planificacion_id: int) -> list[dict]:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT
                vp.*,
                v.codigo,
                v.nombre,
                v.categoria,
                v.unidad,
                v.activo
            FROM planificacion_variables_plan vp
            JOIN planificacion_variables v ON v.id = vp.variable_id
            WHERE vp.planificacion_id = %s
            ORDER BY v.activo DESC, v.categoria NULLS LAST, v.codigo
            """,
            (planificacion_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def reemplazar_variables_plan(planificacion_id: int, rows: Iterable[dict]) -> None:
    ensure_tables()
    rows = list(rows)
    if not rows:
        return
    values = [
        (
            planificacion_id,
            int(r["variable_id"]),
            r.get("valor_base"),
            r.get("valor_plan"),
            r.get("valor_real"),
            r.get("desvio"),
            r.get("impacto"),
        )
        for r in rows
    ]
    with pg_conn() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO planificacion_variables_plan (
                    planificacion_id, variable_id, valor_base, valor_plan, valor_real,
                    desvio, impacto
                ) VALUES %s
                ON CONFLICT (planificacion_id, variable_id) DO UPDATE SET
                    valor_base=EXCLUDED.valor_base,
                    valor_plan=EXCLUDED.valor_plan,
                    valor_real=EXCLUDED.valor_real,
                    desvio=EXCLUDED.desvio,
                    impacto=EXCLUDED.impacto,
                    updated_at=NOW()
                """,
                values,
            )


def obtener_estadistica_mensual(empresa_id: str, sucursal_id: str, anio: int, mes: int) -> dict | None:
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
                COALESCE(SUM(hl), 0) AS hl,
                COALESCE(SUM(bultos), 0) AS bultos,
                COALESCE(SUM(pallets), 0) AS pallets,
                COALESCE(SUM(salidas), 0) AS salidas,
                COALESCE(SUM(pdv_unicos), 0) AS pdv_unicos,
                COALESCE(SUM(CASE WHEN es_dia_pico THEN 1 ELSE 0 END), 0) AS dias_pico,
                COALESCE(AVG(NULLIF(camiones_promedio, 0)), 0) AS camiones_promedio,
                COALESCE(MAX(camiones_pico), 0) AS camiones_pico,
                COALESCE(AVG(NULLIF(empleados_normales, 0)), 0) AS empleados_normales,
                COALESCE(MAX(empleados_pico), 0) AS empleados_pico,
                COALESCE(SUM(rechazos_pct * hl) / NULLIF(SUM(hl), 0), 0) AS rechazos_pct
            FROM planificacion_estadistica_diaria
            WHERE empresa_id = %(empresa_id)s
              AND sucursal_id = %(sucursal_id)s
              AND anio = %(anio)s
              AND mes = %(mes)s
            GROUP BY empresa_id, sucursal_id, anio, mes
            """,
            {"empresa_id": empresa_id, "sucursal_id": sucursal_id, "anio": anio, "mes": mes},
        )
        row = cur.fetchone()
    return dict(row) if row else None


def obtener_estadistica_diaria(empresa_id: str, sucursal_id: str, anio: int, mes: int) -> list[dict]:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM planificacion_estadistica_diaria
            WHERE empresa_id = %(empresa_id)s
              AND sucursal_id = %(sucursal_id)s
              AND anio = %(anio)s
              AND mes = %(mes)s
            ORDER BY fecha
            """,
            {"empresa_id": empresa_id, "sucursal_id": sucursal_id, "anio": anio, "mes": mes},
        )
        return [dict(r) for r in cur.fetchall()]


def obtener_feriados(ini: date, fin: date) -> set[date]:
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT fecha
            FROM feriados
            WHERE fecha BETWEEN %(ini)s AND %(fin)s
            """,
            {"ini": ini, "fin": fin},
        )
        return {r["fecha"] for r in cur.fetchall()}


def guardar_planificacion(plan: dict) -> dict:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO planificacion_picos (
                empresa_id, sucursal_id, anio_plan, mes_plan, anio_base, mes_base,
                hl_base, dias_pico_base, rechazos_pct_base, salidas_base, pdv_unicos_base,
                camiones_promedio_base, camiones_pico_base, empleados_normal_base, empleados_pico_base,
                factor_hl, factor_pdv, factor_salidas, factor_rechazos, factor_dias_pico,
                factor_camiones, factor_empleados,
                hl_plan, dias_pico_plan, rechazos_pct_plan, salidas_plan, pdv_unicos_plan,
                camiones_promedio_plan, camiones_pico_plan, empleados_normal_plan, empleados_pico_plan,
                estado, metodo_distribucion, observaciones, updated_at
            )
            VALUES (
                %(empresa_id)s, %(sucursal_id)s, %(anio_plan)s, %(mes_plan)s, %(anio_base)s, %(mes_base)s,
                %(hl_base)s, %(dias_pico_base)s, %(rechazos_pct_base)s, %(salidas_base)s, %(pdv_unicos_base)s,
                %(camiones_promedio_base)s, %(camiones_pico_base)s, %(empleados_normal_base)s, %(empleados_pico_base)s,
                %(factor_hl)s, %(factor_pdv)s, %(factor_salidas)s, %(factor_rechazos)s, %(factor_dias_pico)s,
                %(factor_camiones)s, %(factor_empleados)s,
                %(hl_plan)s, %(dias_pico_plan)s, %(rechazos_pct_plan)s, %(salidas_plan)s, %(pdv_unicos_plan)s,
                %(camiones_promedio_plan)s, %(camiones_pico_plan)s, %(empleados_normal_plan)s, %(empleados_pico_plan)s,
                %(estado)s, %(metodo_distribucion)s, %(observaciones)s, NOW()
            )
            ON CONFLICT (empresa_id, sucursal_id, anio_plan, mes_plan) DO UPDATE SET
                anio_base=EXCLUDED.anio_base,
                mes_base=EXCLUDED.mes_base,
                hl_base=EXCLUDED.hl_base,
                dias_pico_base=EXCLUDED.dias_pico_base,
                rechazos_pct_base=EXCLUDED.rechazos_pct_base,
                salidas_base=EXCLUDED.salidas_base,
                pdv_unicos_base=EXCLUDED.pdv_unicos_base,
                camiones_promedio_base=EXCLUDED.camiones_promedio_base,
                camiones_pico_base=EXCLUDED.camiones_pico_base,
                empleados_normal_base=EXCLUDED.empleados_normal_base,
                empleados_pico_base=EXCLUDED.empleados_pico_base,
                factor_hl=EXCLUDED.factor_hl,
                factor_pdv=EXCLUDED.factor_pdv,
                factor_salidas=EXCLUDED.factor_salidas,
                factor_rechazos=EXCLUDED.factor_rechazos,
                factor_dias_pico=EXCLUDED.factor_dias_pico,
                factor_camiones=EXCLUDED.factor_camiones,
                factor_empleados=EXCLUDED.factor_empleados,
                hl_plan=EXCLUDED.hl_plan,
                dias_pico_plan=EXCLUDED.dias_pico_plan,
                rechazos_pct_plan=EXCLUDED.rechazos_pct_plan,
                salidas_plan=EXCLUDED.salidas_plan,
                pdv_unicos_plan=EXCLUDED.pdv_unicos_plan,
                camiones_promedio_plan=EXCLUDED.camiones_promedio_plan,
                camiones_pico_plan=EXCLUDED.camiones_pico_plan,
                empleados_normal_plan=EXCLUDED.empleados_normal_plan,
                empleados_pico_plan=EXCLUDED.empleados_pico_plan,
                estado=EXCLUDED.estado,
                metodo_distribucion=EXCLUDED.metodo_distribucion,
                observaciones=EXCLUDED.observaciones,
                updated_at=NOW()
            RETURNING *
            """,
            plan,
        )
        return dict(cur.fetchone())


def reemplazar_dias_planificacion(planificacion_id: int, rows: Iterable[dict]) -> None:
    ensure_tables()
    rows = list(rows)
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM planificacion_picos_dias WHERE planificacion_id = %s", (planificacion_id,))
            if not rows:
                return
            values = [
                (
                    planificacion_id,
                    r["fecha"],
                    r["dia_semana"],
                    r.get("hl_plan", 0),
                    r.get("salidas_plan", 0),
                    r.get("pdv_plan", 0),
                    bool(r.get("es_pico_planificado")),
                    r.get("camiones_plan", 0),
                    r.get("empleados_plan", 0),
                    r.get("estado", "NORMAL"),
                    r.get("fecha_base"),
                    r.get("criterio_asignacion"),
                    r.get("score_asignacion", 0),
                    r.get("observaciones"),
                )
                for r in rows
            ]
            execute_values(
                cur,
                """
                INSERT INTO planificacion_picos_dias (
                    planificacion_id, fecha, dia_semana,
                    hl_plan, salidas_plan, pdv_plan, es_pico_planificado,
                    camiones_plan, empleados_plan, estado,
                    fecha_base, criterio_asignacion, score_asignacion, observaciones
                ) VALUES %s
                """,
                values,
            )


def obtener_planificacion(planificacion_id: int) -> dict | None:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute("SELECT * FROM planificacion_picos WHERE id = %s", (planificacion_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def obtener_planificacion_por_periodo(empresa_id: str, sucursal_id: str, anio: int, mes: int) -> dict | None:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM planificacion_picos
            WHERE empresa_id = %(empresa_id)s
              AND sucursal_id = %(sucursal_id)s
              AND anio_plan = %(anio)s
              AND mes_plan = %(mes)s
            LIMIT 1
            """,
            {"empresa_id": empresa_id, "sucursal_id": sucursal_id, "anio": anio, "mes": mes},
        )
        row = cur.fetchone()
    return dict(row) if row else None


def listar_planificaciones(empresa_id: str = "1", sucursal_id: str | None = None, limit: int = 24) -> list[dict]:
    ensure_tables()
    where = ["empresa_id = %(empresa_id)s"]
    params = {"empresa_id": empresa_id, "limit": int(limit)}
    if sucursal_id and sucursal_id != "TODAS":
        where.append("sucursal_id = %(sucursal_id)s")
        params["sucursal_id"] = sucursal_id
    with pg_cursor() as cur:
        cur.execute(
            f"""
            SELECT *
            FROM planificacion_picos
            WHERE {" AND ".join(where)}
            ORDER BY anio_plan DESC, mes_plan DESC, updated_at DESC
            LIMIT %(limit)s
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]


def guardar_real(planificacion_id: int, real: dict) -> dict:
    ensure_tables()
    params = {**real, "planificacion_id": planificacion_id}
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO planificacion_picos_real (
                planificacion_id, fecha_actualizacion,
                hl_real, dias_pico_real, rechazos_pct_real, salidas_real, pdv_unicos_real,
                camiones_promedio_real, camiones_pico_real, empleados_normal_real, empleados_pico_real,
                desvio_hl_pct, desvio_dias_pico_pct, desvio_rechazos_pct, desvio_salidas_pct,
                desvio_pdv_pct, desvio_camiones_pct, desvio_empleados_pct,
                estado_general, updated_at
            )
            VALUES (
                %(planificacion_id)s, CURRENT_DATE,
                %(hl_real)s, %(dias_pico_real)s, %(rechazos_pct_real)s, %(salidas_real)s, %(pdv_unicos_real)s,
                %(camiones_promedio_real)s, %(camiones_pico_real)s, %(empleados_normal_real)s, %(empleados_pico_real)s,
                %(desvio_hl_pct)s, %(desvio_dias_pico_pct)s, %(desvio_rechazos_pct)s, %(desvio_salidas_pct)s,
                %(desvio_pdv_pct)s, %(desvio_camiones_pct)s, %(desvio_empleados_pct)s,
                %(estado_general)s, NOW()
            )
            ON CONFLICT (planificacion_id) DO UPDATE SET
                fecha_actualizacion=CURRENT_DATE,
                hl_real=EXCLUDED.hl_real,
                dias_pico_real=EXCLUDED.dias_pico_real,
                rechazos_pct_real=EXCLUDED.rechazos_pct_real,
                salidas_real=EXCLUDED.salidas_real,
                pdv_unicos_real=EXCLUDED.pdv_unicos_real,
                camiones_promedio_real=EXCLUDED.camiones_promedio_real,
                camiones_pico_real=EXCLUDED.camiones_pico_real,
                empleados_normal_real=EXCLUDED.empleados_normal_real,
                empleados_pico_real=EXCLUDED.empleados_pico_real,
                desvio_hl_pct=EXCLUDED.desvio_hl_pct,
                desvio_dias_pico_pct=EXCLUDED.desvio_dias_pico_pct,
                desvio_rechazos_pct=EXCLUDED.desvio_rechazos_pct,
                desvio_salidas_pct=EXCLUDED.desvio_salidas_pct,
                desvio_pdv_pct=EXCLUDED.desvio_pdv_pct,
                desvio_camiones_pct=EXCLUDED.desvio_camiones_pct,
                desvio_empleados_pct=EXCLUDED.desvio_empleados_pct,
                estado_general=EXCLUDED.estado_general,
                updated_at=NOW()
            RETURNING *
            """,
            params,
        )
        return dict(cur.fetchone())


def obtener_real(planificacion_id: int) -> dict | None:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute("SELECT * FROM planificacion_picos_real WHERE planificacion_id = %s", (planificacion_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def actualizar_dias_reales(plan: dict, alerta_pct: float = 15) -> int:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            UPDATE planificacion_picos_dias d
            SET
                hl_real = COALESCE(e.hl, 0),
                salidas_real = COALESCE(e.salidas, 0),
                pdv_real = COALESCE(e.pdv_unicos, 0),
                es_pico_real = COALESCE(e.es_dia_pico, FALSE),
                camiones_real = COALESCE(e.camiones_promedio, 0),
                empleados_real = COALESCE(e.empleados_normales, 0),
                estado = CASE
                    WHEN COALESCE(e.hl, 0) <= d.hl_plan
                     AND COALESCE(e.salidas, 0) <= d.salidas_plan
                     AND COALESCE(e.pdv_unicos, 0) <= d.pdv_plan THEN 'NORMAL'
                    WHEN GREATEST(
                        CASE WHEN d.hl_plan > 0 THEN (COALESCE(e.hl, 0) - d.hl_plan) / d.hl_plan * 100 ELSE 0 END,
                        CASE WHEN d.salidas_plan > 0 THEN (COALESCE(e.salidas, 0) - d.salidas_plan) / d.salidas_plan * 100 ELSE 0 END,
                        CASE WHEN d.pdv_plan > 0 THEN (COALESCE(e.pdv_unicos, 0) - d.pdv_plan) / d.pdv_plan * 100 ELSE 0 END
                    ) <= %(alerta_pct)s THEN 'ALERTA'
                    ELSE 'CRITICO'
                END,
                updated_at = NOW()
            FROM planificacion_estadistica_diaria e
            WHERE d.planificacion_id = %(planificacion_id)s
              AND e.empresa_id = %(empresa_id)s
              AND e.sucursal_id = %(sucursal_id)s
              AND e.fecha = d.fecha
            """,
            {
                "planificacion_id": plan["id"],
                "empresa_id": plan["empresa_id"],
                "sucursal_id": plan["sucursal_id"],
                "alerta_pct": alerta_pct,
            },
        )
        return cur.rowcount


def obtener_dias_planificacion(planificacion_id: int) -> list[dict]:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM planificacion_picos_dias
            WHERE planificacion_id = %s
            ORDER BY fecha
            """,
            (planificacion_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def listar_escenarios(planificacion_id: int) -> list[dict]:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM planificacion_picos_escenarios
            WHERE planificacion_id = %s
            ORDER BY activo DESC, updated_at DESC, id DESC
            """,
            (planificacion_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def obtener_escenario_activo(planificacion_id: int) -> dict | None:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM planificacion_picos_escenarios
            WHERE planificacion_id = %s AND activo = TRUE
            LIMIT 1
            """,
            (planificacion_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def obtener_escenario(planificacion_id: int, escenario_id: int) -> dict | None:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM planificacion_picos_escenarios
            WHERE planificacion_id = %(planificacion_id)s AND id = %(escenario_id)s
            """,
            {"planificacion_id": planificacion_id, "escenario_id": escenario_id},
        )
        row = cur.fetchone()
    return dict(row) if row else None


def guardar_escenario(planificacion_id: int, data: dict) -> dict:
    ensure_tables()
    params = {
        "planificacion_id": planificacion_id,
        "nombre": str(data.get("nombre") or "Ajuste manual").strip()[:120],
        "tipo": str(data.get("tipo") or "MANUAL").strip().upper()[:20],
        "hl_plan": float(data.get("hl_plan") or 0),
        "dias_pico_plan": float(data.get("dias_pico_plan") or 0),
        "rechazos_pct_plan": float(data.get("rechazos_pct_plan") or 0),
        "salidas_plan": float(data.get("salidas_plan") or 0),
        "pdv_unicos_plan": float(data.get("pdv_unicos_plan") or 0),
        "camiones_promedio_plan": float(data.get("camiones_promedio_plan") or 0),
        "camiones_pico_plan": float(data.get("camiones_pico_plan") or 0),
        "empleados_normal_plan": float(data.get("empleados_normal_plan") or 0),
        "empleados_pico_plan": float(data.get("empleados_pico_plan") or 0),
        "observaciones": data.get("observaciones"),
    }
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO planificacion_picos_escenarios (
                planificacion_id, nombre, tipo, activo,
                hl_plan, dias_pico_plan, rechazos_pct_plan, salidas_plan, pdv_unicos_plan,
                camiones_promedio_plan, camiones_pico_plan, empleados_normal_plan, empleados_pico_plan,
                observaciones, updated_at
            )
            VALUES (
                %(planificacion_id)s, %(nombre)s, %(tipo)s, FALSE,
                %(hl_plan)s, %(dias_pico_plan)s, %(rechazos_pct_plan)s, %(salidas_plan)s, %(pdv_unicos_plan)s,
                %(camiones_promedio_plan)s, %(camiones_pico_plan)s, %(empleados_normal_plan)s, %(empleados_pico_plan)s,
                %(observaciones)s, NOW()
            )
            ON CONFLICT (planificacion_id, nombre) DO UPDATE SET
                tipo=EXCLUDED.tipo,
                hl_plan=EXCLUDED.hl_plan,
                dias_pico_plan=EXCLUDED.dias_pico_plan,
                rechazos_pct_plan=EXCLUDED.rechazos_pct_plan,
                salidas_plan=EXCLUDED.salidas_plan,
                pdv_unicos_plan=EXCLUDED.pdv_unicos_plan,
                camiones_promedio_plan=EXCLUDED.camiones_promedio_plan,
                camiones_pico_plan=EXCLUDED.camiones_pico_plan,
                empleados_normal_plan=EXCLUDED.empleados_normal_plan,
                empleados_pico_plan=EXCLUDED.empleados_pico_plan,
                observaciones=EXCLUDED.observaciones,
                updated_at=NOW()
            RETURNING *
            """,
            params,
        )
        return dict(cur.fetchone())


def activar_escenario(planificacion_id: int, escenario_id: int) -> dict:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            "UPDATE planificacion_picos_escenarios SET activo = FALSE WHERE planificacion_id = %s",
            (planificacion_id,),
        )
        cur.execute(
            """
            UPDATE planificacion_picos_escenarios
            SET activo = TRUE, updated_at = NOW()
            WHERE planificacion_id = %(planificacion_id)s AND id = %(escenario_id)s
            RETURNING *
            """,
            {"planificacion_id": planificacion_id, "escenario_id": escenario_id},
        )
        row = cur.fetchone()
    if not row:
        raise ValueError("Escenario no encontrado")
    return dict(row)


def obtener_capacidad(empresa_id: str, sucursal_id: str, ini: date, fin: date) -> list[dict]:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM capacidad_operativa
            WHERE empresa_id = %(empresa_id)s
              AND sucursal_id = %(sucursal_id)s
              AND fecha BETWEEN %(ini)s AND %(fin)s
            ORDER BY fecha
            """,
            {"empresa_id": empresa_id, "sucursal_id": sucursal_id, "ini": ini, "fin": fin},
        )
        return [dict(r) for r in cur.fetchall()]


def guardar_capacidad(data: dict) -> dict:
    ensure_tables()
    params = {
        "empresa_id": str(data.get("empresa_id") or "1"),
        "sucursal_id": str(data.get("sucursal_id") or "TODAS"),
        "fecha": data.get("fecha"),
        "camiones_disponibles": float(data.get("camiones_disponibles") or 0),
        "choferes": float(data.get("choferes") or 0),
        "acompanantes": float(data.get("acompanantes") or 0),
        "operarios_almacen": float(data.get("operarios_almacen") or 0),
        "capacidad_hl": float(data.get("capacidad_hl") or 0),
        "capacidad_pallets": float(data.get("capacidad_pallets") or 0),
    }
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO capacidad_operativa (
                empresa_id, sucursal_id, fecha, camiones_disponibles, choferes,
                acompanantes, operarios_almacen, capacidad_hl, capacidad_pallets, updated_at
            )
            VALUES (
                %(empresa_id)s, %(sucursal_id)s, %(fecha)s, %(camiones_disponibles)s, %(choferes)s,
                %(acompanantes)s, %(operarios_almacen)s, %(capacidad_hl)s, %(capacidad_pallets)s, NOW()
            )
            ON CONFLICT (empresa_id, sucursal_id, fecha) DO UPDATE SET
                camiones_disponibles=EXCLUDED.camiones_disponibles,
                choferes=EXCLUDED.choferes,
                acompanantes=EXCLUDED.acompanantes,
                operarios_almacen=EXCLUDED.operarios_almacen,
                capacidad_hl=EXCLUDED.capacidad_hl,
                capacidad_pallets=EXCLUDED.capacidad_pallets,
                updated_at=NOW()
            RETURNING *
            """,
            params,
        )
        return dict(cur.fetchone())


# ── Capacidad mensual ─────────────────────────────────────────────────────────

def obtener_capacidad_mensual(empresa_id: str, sucursal_id: str, anio: int, mes: int) -> dict | None:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT * FROM capacidad_mensual
            WHERE empresa_id = %(empresa_id)s
              AND sucursal_id = %(sucursal_id)s
              AND anio = %(anio)s
              AND mes = %(mes)s
            """,
            {"empresa_id": empresa_id, "sucursal_id": sucursal_id, "anio": anio, "mes": mes},
        )
        row = cur.fetchone()
    return dict(row) if row else None


def guardar_capacidad_mensual(data: dict) -> dict:
    ensure_tables()
    params = {
        "empresa_id": str(data.get("empresa_id") or "1"),
        "sucursal_id": str(data.get("sucursal_id") or "TODAS"),
        "anio": int(data.get("anio")),
        "mes": int(data.get("mes")),
        "camiones_disponibles": int(data.get("camiones_disponibles") or 0),
        "choferes": int(data.get("choferes") or 0),
        "ayudantes": int(data.get("ayudantes") or 0),
        "capacidad_hl": float(data.get("capacidad_hl") or 0),
        "observaciones": data.get("observaciones") or None,
    }
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO capacidad_mensual (
                empresa_id, sucursal_id, anio, mes,
                camiones_disponibles, choferes, ayudantes, capacidad_hl,
                observaciones, updated_at
            )
            VALUES (
                %(empresa_id)s, %(sucursal_id)s, %(anio)s, %(mes)s,
                %(camiones_disponibles)s, %(choferes)s, %(ayudantes)s, %(capacidad_hl)s,
                %(observaciones)s, NOW()
            )
            ON CONFLICT (empresa_id, sucursal_id, anio, mes) DO UPDATE SET
                camiones_disponibles=EXCLUDED.camiones_disponibles,
                choferes=EXCLUDED.choferes,
                ayudantes=EXCLUDED.ayudantes,
                capacidad_hl=EXCLUDED.capacidad_hl,
                observaciones=EXCLUDED.observaciones,
                updated_at=NOW()
            RETURNING *
            """,
            params,
        )
        saved = dict(cur.fetchone())
    propagar_capacidad_mensual(saved)
    return saved


def propagar_capacidad_mensual(config: dict) -> int:
    """Llena capacidad_operativa para cada dia del mes usando la configuracion mensual."""
    ensure_tables()
    empresa_id = config["empresa_id"]
    sucursal_id = config["sucursal_id"]
    anio = int(config["anio"])
    mes = int(config["mes"])
    ini = date(anio, mes, 1)
    fin = date(anio, mes, cal_mod.monthrange(anio, mes)[1])

    dias = [ini + timedelta(days=i) for i in range((fin - ini).days + 1)]
    values = [
        (
            empresa_id,
            sucursal_id,
            d,
            config["camiones_disponibles"],
            config["choferes"],
            config["ayudantes"],
            0,
            config["capacidad_hl"],
            0,
        )
        for d in dias
    ]
    with pg_conn() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO capacidad_operativa (
                    empresa_id, sucursal_id, fecha,
                    camiones_disponibles, choferes, acompanantes, operarios_almacen,
                    capacidad_hl, capacidad_pallets, updated_at
                ) VALUES %s
                ON CONFLICT (empresa_id, sucursal_id, fecha) DO UPDATE SET
                    camiones_disponibles=EXCLUDED.camiones_disponibles,
                    choferes=EXCLUDED.choferes,
                    acompanantes=EXCLUDED.acompanantes,
                    capacidad_hl=EXCLUDED.capacidad_hl,
                    updated_at=NOW()
                """,
                [(empresa_id, sucursal_id, d, config["camiones_disponibles"],
                  config["choferes"], config["ayudantes"], 0,
                  config["capacidad_hl"], 0) for d in dias],
                template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
            )
            return cur.rowcount


def sync_empleados_desde_sheets(
    empresa_id: str,
    dias_data: list[dict],
) -> int:
    """Actualiza estadistica_diaria desde datos de sheets.

    dias_data: lista devuelta por get_camiones_diarios().
    Sincroniza: empleados_normales, empleados_pico, camiones_reales,
                recargas_count, personas_recargas.
    """
    ensure_tables()
    if not dias_data:
        return 0

    values = [
        (
            empresa_id,
            str(item.get("sucursal_id") or "TODAS"),
            item["fecha"],
            int(item.get("choferes") or 0) + int(item.get("ayudantes") or 0),
            int(item.get("choferes") or 0) + int(item.get("ayudantes") or 0),
            int(item.get("camiones") or 0),
            int(item.get("recargas_count") or 0),
            int(item.get("personas_recargas") or 0),
        )
        for item in dias_data
    ]
    with pg_conn() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                UPDATE planificacion_estadistica_diaria AS e
                SET
                    empleados_normales = v.empleados,
                    empleados_pico     = CASE WHEN e.es_dia_pico THEN v.empleados_pico ELSE e.empleados_pico END,
                    camiones_reales    = v.camiones_reales,
                    recargas_count     = v.recargas_count,
                    personas_recargas  = v.personas_recargas,
                    updated_at         = NOW()
                FROM (VALUES %s) AS v(
                    empresa_id, sucursal_id, fecha,
                    empleados, empleados_pico,
                    camiones_reales, recargas_count, personas_recargas
                )
                WHERE e.empresa_id  = v.empresa_id
                  AND e.sucursal_id = v.sucursal_id
                  AND e.fecha       = v.fecha::date
                """,
                values,
                template="(%s, %s, %s::date, %s, %s, %s, %s, %s)",
            )
            return cur.rowcount
