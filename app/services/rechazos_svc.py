from app.database import pg_conn, pg_cursor
from app.services.ventas_svc import ensure_ventas_detalle_table

_RECHAZOS_READY = False


DDL = """
CREATE TABLE IF NOT EXISTS rechazos (
    motivo_key      VARCHAR(255) PRIMARY KEY,
    motivo_rechazo  VARCHAR(255) NOT NULL,
    sector          VARCHAR(100),
    tomar           BOOLEAN NOT NULL DEFAULT FALSE,
    actualizado     TIMESTAMP DEFAULT NOW()
)
"""


def ensure_table() -> None:
    global _RECHAZOS_READY
    if _RECHAZOS_READY:
        return
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                {DDL};
                ALTER TABLE rechazos ADD COLUMN IF NOT EXISTS sector VARCHAR(100);
                CREATE INDEX IF NOT EXISTS idx_rechazos_tomar ON rechazos(tomar);
            """)
    _RECHAZOS_READY = True


def sync_from_detalle() -> dict:
    ensure_table()
    ensure_ventas_detalle_table()
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO rechazos (motivo_key, motivo_rechazo, sector, tomar)
                SELECT LOWER(TRIM(motivo_rechazo)) AS motivo_key,
                       MIN(TRIM(motivo_rechazo))   AS motivo_rechazo,
                       ''                           AS sector,
                       FALSE                       AS tomar
                FROM ventas_detalle
                WHERE motivo_rechazo IS NOT NULL
                  AND TRIM(motivo_rechazo) <> ''
                  AND LOWER(TRIM(COALESCE(documento, ''))) NOT LIKE '%remit%'
                  AND LOWER(TRIM(COALESCE(documento, ''))) NOT LIKE '%comod%'
                  AND LOWER(TRIM(COALESCE(detalle_documento, ''))) NOT LIKE '%remit%'
                  AND LOWER(TRIM(COALESCE(detalle_documento, ''))) NOT LIKE '%comod%'
                GROUP BY LOWER(TRIM(motivo_rechazo))
                ON CONFLICT (motivo_key) DO NOTHING
            """)
            inserted = cur.rowcount
    return {'inserted': inserted}


def list_rechazos() -> list[dict]:
    ensure_table()
    ensure_ventas_detalle_table()
    with pg_cursor() as cur:
        cur.execute("""
            SELECT
                r.motivo_key,
                r.motivo_rechazo,
                r.sector,
                r.tomar,
                COALESCE(x.filas, 0) AS filas,
                COALESCE(x.bultos, 0) AS bultos,
                r.actualizado
            FROM rechazos r
            LEFT JOIN (
                SELECT LOWER(TRIM(motivo_rechazo)) AS motivo_key,
                       COUNT(*) AS filas,
                       SUM(bultos_rechazados) AS bultos
                FROM ventas_detalle
                WHERE motivo_rechazo IS NOT NULL
                  AND TRIM(motivo_rechazo) <> ''
                  AND LOWER(TRIM(COALESCE(documento, ''))) NOT LIKE '%remit%'
                  AND LOWER(TRIM(COALESCE(documento, ''))) NOT LIKE '%comod%'
                  AND LOWER(TRIM(COALESCE(detalle_documento, ''))) NOT LIKE '%remit%'
                  AND LOWER(TRIM(COALESCE(detalle_documento, ''))) NOT LIKE '%comod%'
                GROUP BY LOWER(TRIM(motivo_rechazo))
            ) x ON x.motivo_key = r.motivo_key
            ORDER BY r.tomar DESC, r.motivo_rechazo
        """)
        return [dict(r) for r in cur.fetchall()]


def update_tomar(motivo_key: str, tomar: bool) -> dict:
    ensure_table()
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE rechazos SET tomar = %s, actualizado = NOW()
                WHERE motivo_key = %s
            """, (tomar, motivo_key))
            updated = cur.rowcount
    return {'updated': updated}
