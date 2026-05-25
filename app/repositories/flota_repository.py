from __future__ import annotations

from pathlib import Path

from app.database import pg_conn, pg_cursor


_READY = False


def ensure_tables() -> None:
    global _READY
    if _READY:
        return
    sql_path = Path(__file__).resolve().parents[2] / "sql" / "flota_operativa.sql"
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_path.read_text(encoding="utf-8"))
    _READY = True


def listar_vehiculos(
    empresa_id: str = "1",
    sucursal_id: str = "TODAS",
    anio: int | None = None,
    mes: int | None = None,
    incluir_anulados: bool = False,
) -> list[dict]:
    ensure_tables()
    where = []
    params: dict = {"empresa_id": empresa_id, "anio": anio, "mes": mes}
    if empresa_id and empresa_id != "TODAS":
        where.append("v.empresa_id = %(empresa_id)s")
    if sucursal_id and sucursal_id != "TODAS":
        where.append("v.sucursal_id = %(sucursal_id)s")
        params["sucursal_id"] = sucursal_id
    if not incluir_anulados:
        where.append("v.anulado = FALSE")

    disponibilidad_join = ""
    disponibilidad_fields = """
        NULL::bigint AS disponibilidad_id,
        NULL::boolean AS activo_mes_override,
        NULL::varchar AS motivo_mes,
        NULL::text AS observaciones_mes,
        (v.activo_base AND NOT v.anulado) AS activo_mes
    """
    if anio and mes:
        disponibilidad_join = """
            LEFT JOIN flota_disponibilidad_mensual d
              ON d.vehiculo_id = v.id
             AND d.anio = %(anio)s
             AND d.mes = %(mes)s
        """
        disponibilidad_fields = """
            d.id AS disponibilidad_id,
            d.activo AS activo_mes_override,
            d.motivo AS motivo_mes,
            d.observaciones AS observaciones_mes,
            (COALESCE(d.activo, v.activo_base) AND NOT v.anulado) AS activo_mes
        """

    with pg_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                v.id,
                v.empresa_id,
                v.sucursal_id,
                v.codigo,
                v.descripcion,
                v.marca,
                v.modelo,
                v.placa,
                v.carga_maxima_kg::float AS carga_maxima_kg,
                v.capacidad_up::float AS capacidad_up,
                v.propio,
                v.deposito_default_id,
                v.deposito_default_nombre,
                v.anulado,
                v.activo_base,
                v.fuente,
                v.observaciones,
                {disponibilidad_fields}
            FROM flota_vehiculos v
            {disponibilidad_join}
            WHERE {" AND ".join(where) if where else "TRUE"}
            ORDER BY v.sucursal_id, v.codigo
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]


def obtener_vehiculo(vehiculo_id: int) -> dict | None:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT
                id, empresa_id, sucursal_id, codigo, descripcion, marca, modelo,
                placa, carga_maxima_kg::float AS carga_maxima_kg,
                capacidad_up::float AS capacidad_up, propio, deposito_default_id,
                deposito_default_nombre, anulado, activo_base, fuente, observaciones
            FROM flota_vehiculos
            WHERE id = %s
            """,
            (vehiculo_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def eliminar_vehiculo(vehiculo_id: int) -> bool:
    ensure_tables()
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM flota_vehiculos WHERE id = %s", (vehiculo_id,))
            return cur.rowcount > 0


def sync_desde_transportes(empresa_id: str = "1") -> dict:
    ensure_tables()
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO flota_vehiculos (
                    empresa_id, sucursal_id, codigo, descripcion, marca, modelo,
                    placa, carga_maxima_kg, capacidad_up, propio,
                    deposito_default_id, deposito_default_nombre,
                    anulado, activo_base, fuente, updated_at
                )
                SELECT
                    %(empresa_id)s,
                    CASE
                        WHEN LOWER(COALESCE(t.sucursal,'')) LIKE '%%central%%' THEN '1'
                        WHEN LOWER(COALESCE(t.sucursal,'')) LIKE '%%dolor%%'  THEN '2'
                        ELSE COALESCE(NULLIF(TRIM(t.sucursal),''), 'DESCONOCIDA')
                    END,
                    t.codigo::text,
                    t.descripcion,
                    t.marca,
                    t.modelo,
                    t.placa,
                    t.carga_maxima_kg,
                    t.capacidad_up,
                    COALESCE(t.propio, TRUE),
                    t.deposito_defecto::text,
                    t.descripcion_deposito_defecto,
                    COALESCE(t.anulado, FALSE),
                    TRUE,
                    'TRANSPORTES',
                    NOW()
                FROM transportes t
                WHERE t.descripcion IS NOT NULL
                ON CONFLICT (empresa_id, codigo) DO UPDATE SET
                    sucursal_id              = EXCLUDED.sucursal_id,
                    descripcion              = EXCLUDED.descripcion,
                    marca                    = EXCLUDED.marca,
                    modelo                   = EXCLUDED.modelo,
                    placa                    = EXCLUDED.placa,
                    carga_maxima_kg          = EXCLUDED.carga_maxima_kg,
                    capacidad_up             = EXCLUDED.capacidad_up,
                    propio                   = EXCLUDED.propio,
                    deposito_default_id      = EXCLUDED.deposito_default_id,
                    deposito_default_nombre  = EXCLUDED.deposito_default_nombre,
                    anulado                  = EXCLUDED.anulado,
                    fuente                   = EXCLUDED.fuente,
                    updated_at               = NOW()
                """,
                {"empresa_id": empresa_id},
            )
            total = cur.rowcount
    return {"sincronizados": total}


def guardar_disponibilidad(data: dict) -> dict:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO flota_disponibilidad_mensual (
                vehiculo_id, empresa_id, sucursal_id, anio, mes,
                activo, motivo, observaciones, updated_at
            )
            SELECT
                v.id, v.empresa_id, v.sucursal_id, %(anio)s, %(mes)s,
                %(activo)s, %(motivo)s, %(observaciones)s, NOW()
            FROM flota_vehiculos v
            WHERE v.id = %(vehiculo_id)s
            ON CONFLICT (vehiculo_id, anio, mes) DO UPDATE SET
                empresa_id=EXCLUDED.empresa_id,
                sucursal_id=EXCLUDED.sucursal_id,
                activo=EXCLUDED.activo,
                motivo=EXCLUDED.motivo,
                observaciones=EXCLUDED.observaciones,
                updated_at=NOW()
            RETURNING
                id, vehiculo_id, empresa_id, sucursal_id, anio, mes,
                activo, motivo, observaciones, created_at, updated_at
            """,
            data,
        )
        row = cur.fetchone()
        return dict(row) if row else {}


def guardar_vehiculo(data: dict) -> dict:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO flota_vehiculos (
                empresa_id, sucursal_id, codigo, descripcion, marca, modelo,
                placa, carga_maxima_kg, capacidad_up, propio,
                deposito_default_id, deposito_default_nombre, anulado,
                activo_base, fuente, observaciones, updated_at
            ) VALUES (
                %(empresa_id)s, %(sucursal_id)s, %(codigo)s, %(descripcion)s,
                %(marca)s, %(modelo)s, %(placa)s, %(carga_maxima_kg)s,
                %(capacidad_up)s, %(propio)s, %(deposito_default_id)s,
                %(deposito_default_nombre)s, %(anulado)s, %(activo_base)s,
                %(fuente)s, %(observaciones)s, NOW()
            )
            ON CONFLICT (empresa_id, codigo) DO UPDATE SET
                sucursal_id=EXCLUDED.sucursal_id,
                descripcion=EXCLUDED.descripcion,
                marca=EXCLUDED.marca,
                modelo=EXCLUDED.modelo,
                placa=EXCLUDED.placa,
                carga_maxima_kg=EXCLUDED.carga_maxima_kg,
                capacidad_up=EXCLUDED.capacidad_up,
                propio=EXCLUDED.propio,
                deposito_default_id=EXCLUDED.deposito_default_id,
                deposito_default_nombre=EXCLUDED.deposito_default_nombre,
                anulado=EXCLUDED.anulado,
                activo_base=EXCLUDED.activo_base,
                fuente=EXCLUDED.fuente,
                observaciones=EXCLUDED.observaciones,
                updated_at=NOW()
            RETURNING
                id, empresa_id, sucursal_id, codigo, descripcion, marca, modelo,
                placa, carga_maxima_kg::float AS carga_maxima_kg,
                capacidad_up::float AS capacidad_up, propio, deposito_default_id,
                deposito_default_nombre, anulado, activo_base, fuente, observaciones
            """,
            data,
        )
        return dict(cur.fetchone())
