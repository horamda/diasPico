from __future__ import annotations

from app.database import pg_conn, pg_cursor

_READY = False

_DDL = """
CREATE TABLE IF NOT EXISTS sucursales (
    id          VARCHAR(50) PRIMARY KEY,
    empresa_id  VARCHAR(50) NOT NULL DEFAULT '1',
    nombre      VARCHAR(100) NOT NULL,
    activa      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);
"""

_SEED = """
INSERT INTO sucursales (id, empresa_id, nombre, activa) VALUES
    ('1', '1', 'Casa Central', TRUE),
    ('2', '1', 'Dolores', TRUE)
ON CONFLICT (id) DO NOTHING;
"""


def ensure_table() -> None:
    global _READY
    if _READY:
        return
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_DDL)
            cur.execute(_SEED)
    _READY = True


def listar(empresa_id: str | None = None, solo_activas: bool = False) -> list[dict]:
    ensure_table()
    where = []
    params: dict = {}
    if empresa_id:
        where.append("empresa_id = %(empresa_id)s")
        params["empresa_id"] = empresa_id
    if solo_activas:
        where.append("activa = TRUE")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    with pg_cursor() as cur:
        cur.execute(
            f"SELECT id, empresa_id, nombre, activa FROM sucursales {clause} ORDER BY id",
            params,
        )
        return [dict(r) for r in cur.fetchall()]


def get_sucursales_select(empresa_id: str | None = None) -> list[dict]:
    rows = listar(empresa_id=empresa_id, solo_activas=False)
    return [{"value": r["id"], "label": r["nombre"], "activa": r["activa"]} for r in rows]


def get_label(sucursal_id: str) -> str:
    rows = listar()
    mapping = {r["id"]: r["nombre"] for r in rows}
    return mapping.get(str(sucursal_id), str(sucursal_id))


def guardar(data: dict) -> dict:
    ensure_table()
    sucursal_id = str(data.get("id") or data.get("sucursal_id") or "").strip()
    nombre = str(data.get("nombre") or "").strip()
    empresa_id = str(data.get("empresa_id") or "1").strip()
    activa = bool(data.get("activa", True))
    if not sucursal_id:
        raise ValueError("id requerido")
    if not nombre:
        raise ValueError("nombre requerido")
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO sucursales (id, empresa_id, nombre, activa, updated_at)
            VALUES (%(id)s, %(empresa_id)s, %(nombre)s, %(activa)s, NOW())
            ON CONFLICT (id) DO UPDATE SET
                empresa_id = EXCLUDED.empresa_id,
                nombre     = EXCLUDED.nombre,
                activa     = EXCLUDED.activa,
                updated_at = NOW()
            RETURNING id, empresa_id, nombre, activa
            """,
            {"id": sucursal_id, "empresa_id": empresa_id, "nombre": nombre, "activa": activa},
        )
        return dict(cur.fetchone())


def eliminar(sucursal_id: str) -> bool:
    ensure_table()
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sucursales WHERE id = %s", (sucursal_id,))
            return cur.rowcount > 0
