from __future__ import annotations

from threading import Lock
from typing import Any

import psycopg2.extras
from werkzeug.security import check_password_hash, generate_password_hash

from app.database import pg_conn, pg_cursor

_TABLES_READY = False
_TABLES_LOCK = Lock()


_DEFAULT_MODULES = (
    {
        'codigo': 'importaciones_datos',
        'titulo': 'Importaciones de datos',
        'descripcion': 'Carga centralizada de archivos, maestros y sincronizaciones externas.',
        'ruta': '/importaciones-datos',
        'image_url': None,
        'orden': 5,
    },
    {
        'codigo': 'dias_pico',
        'titulo': 'Panel Dias Pico',
        'descripcion': 'Analisis operativo de dias pico, volumenes y desempeno por sucursal.',
        'ruta': '/dias-pico',
        'image_url': 'https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&w=1200&q=60',
        'orden': 10,
    },
    {
        'codigo': 'cluster_clientes',
        'titulo': 'Cluster de Clientes',
        'descripcion': 'Segmentacion DPO, score logistico-comercial y plan de servicio por cliente.',
        'ruta': '/segmentacion-clientes',
        'image_url': 'https://images.unsplash.com/photo-1552664730-d307ca884978?auto=format&fit=crop&w=1200&q=60',
        'orden': 20,
    },
    {
        'codigo': 'frescura_oportunidades',
        'titulo': 'Frescura y oportunidades',
        'descripcion': 'Articulos con frescura critica y oportunidades comerciales por cliente.',
        'ruta': '/frescura-oportunidades',
        'image_url': 'https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=1200&q=60',
        'orden': 25,
    },
    {
        'codigo': 'control_stock',
        'titulo': 'Control de stock',
        'descripcion': 'ABC de articulos activos de Casa Central segun bultos vendidos el ultimo mes.',
        'ruta': '/control-stock',
        'image_url': None,
        'orden': 27,
    },
    {
        'codigo': 'analisis_pedidos',
        'titulo': 'Control de pedidos SMK',
        'descripcion': 'Cruce de pedidos de supermercado contra punto de pedido, stock y frescura.',
        'ruta': '/analisis-pedidos',
        'image_url': None,
        'orden': 28,
    },
    {
        'codigo': 'panel_proyecto',
        'titulo': 'Mantenimiento del sistema',
        'descripcion': 'Estado tecnico del sistema, base de datos, indices y mantenimiento.',
        'ruta': '/dashboard',
        'image_url': 'https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=1200&q=60',
        'orden': 30,
    },
)


def ensure_tables() -> None:
    global _TABLES_READY
    if _TABLES_READY:
        return
    with _TABLES_LOCK:
        if _TABLES_READY:
            return
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS portal_usuarios (
                        id                  BIGSERIAL PRIMARY KEY,
                        username            VARCHAR(80) NOT NULL UNIQUE,
                        password_hash       TEXT NOT NULL,
                        nombre              VARCHAR(120) NOT NULL,
                        activo              BOOLEAN NOT NULL DEFAULT TRUE,
                        es_admin            BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS portal_modulos (
                        id                  BIGSERIAL PRIMARY KEY,
                        codigo              VARCHAR(80) NOT NULL UNIQUE,
                        titulo              VARCHAR(120) NOT NULL,
                        descripcion         TEXT NOT NULL DEFAULT '',
                        ruta                VARCHAR(255) NOT NULL,
                        image_url           TEXT,
                        orden               INTEGER NOT NULL DEFAULT 100,
                        activo              BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS portal_usuario_modulo (
                        usuario_id          BIGINT NOT NULL REFERENCES portal_usuarios(id) ON DELETE CASCADE,
                        modulo_id           BIGINT NOT NULL REFERENCES portal_modulos(id) ON DELETE CASCADE,
                        puede_ver           BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (usuario_id, modulo_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_portal_usuarios_activo
                        ON portal_usuarios(activo, es_admin, username);
                    CREATE INDEX IF NOT EXISTS idx_portal_modulos_orden
                        ON portal_modulos(activo, orden, titulo);
                    CREATE INDEX IF NOT EXISTS idx_portal_usuario_modulo_user
                        ON portal_usuario_modulo(usuario_id, puede_ver);
                """)

                for mod in _DEFAULT_MODULES:
                    cur.execute(
                        """INSERT INTO portal_modulos(codigo, titulo, descripcion, ruta, image_url, orden, activo)
                           VALUES (%(codigo)s, %(titulo)s, %(descripcion)s, %(ruta)s, %(image_url)s, %(orden)s, TRUE)
                           ON CONFLICT (codigo) DO NOTHING""",
                        mod,
                    )
                cur.execute(
                    """UPDATE portal_modulos
                       SET titulo = 'Mantenimiento del sistema',
                           descripcion = 'Estado tecnico del sistema, base de datos, indices y mantenimiento.',
                           updated_at = NOW()
                       WHERE codigo = 'panel_proyecto'
                         AND titulo IN ('Panel Proyecto', 'Panel proyecto', 'Portal_Logistica')"""
                )

                # Conservar acceso para usuarios ya creados en modulos
                # operativos agregados despues del setup inicial.
                cur.execute(
                    "SELECT id FROM portal_modulos WHERE codigo IN ('importaciones_datos', 'control_stock', 'analisis_pedidos')"
                )
                for import_module in cur.fetchall() or []:
                    cur.execute(
                        """INSERT INTO portal_usuario_modulo(usuario_id, modulo_id, puede_ver)
                           SELECT id, %s, TRUE FROM portal_usuarios WHERE activo
                           ON CONFLICT (usuario_id, modulo_id) DO NOTHING""",
                        (import_module[0],),
                    )
        _TABLES_READY = True


def _dict_rows(cur) -> list[dict]:
    return [dict(r) for r in (cur.fetchall() or [])]


def has_users() -> bool:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute("SELECT EXISTS(SELECT 1 FROM portal_usuarios) AS ok")
        row = cur.fetchone() or {}
    return bool(row.get('ok'))


def create_initial_admin(username: str, password: str, nombre: str) -> dict:
    ensure_tables()
    username = username.strip().lower()
    nombre = nombre.strip()
    if not username or not password or not nombre:
        raise ValueError('username, password y nombre son obligatorios')
    if len(password) < 6:
        raise ValueError('password debe tener al menos 6 caracteres')
    if has_users():
        raise ValueError('El setup inicial ya fue ejecutado')

    password_hash = generate_password_hash(password)
    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO portal_usuarios(username, password_hash, nombre, activo, es_admin)
                   VALUES (%s, %s, %s, TRUE, TRUE)
                   RETURNING id, username, nombre, activo, es_admin, created_at""",
                (username, password_hash, nombre),
            )
            user = dict(cur.fetchone() or {})
            cur.execute("SELECT id FROM portal_modulos WHERE activo ORDER BY orden, id")
            modules = [r['id'] for r in _dict_rows(cur)]
            if modules:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO portal_usuario_modulo(usuario_id, modulo_id, puede_ver)
                       VALUES %s
                       ON CONFLICT (usuario_id, modulo_id) DO UPDATE SET puede_ver = EXCLUDED.puede_ver""",
                    [(user['id'], module_id, True) for module_id in modules],
                )
    return user


def authenticate(username: str, password: str) -> dict | None:
    ensure_tables()
    username = (username or '').strip().lower()
    password = str(password or '').strip()
    if not username or not password:
        return None
    with pg_cursor() as cur:
        cur.execute(
            """SELECT id, username, password_hash, nombre, activo, es_admin
               FROM portal_usuarios
               WHERE username = %s
               LIMIT 1""",
            (username,),
        )
        row = cur.fetchone()
    if not row:
        return None
    if not bool(row.get('activo')):
        return None
    if not check_password_hash(str(row.get('password_hash') or ''), password):
        return None
    return {
        'id': int(row['id']),
        'username': row['username'],
        'nombre': row['nombre'],
        'activo': bool(row['activo']),
        'es_admin': bool(row['es_admin']),
    }


def get_user_by_id(user_id: int) -> dict | None:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """SELECT id, username, nombre, activo, es_admin, created_at, updated_at
               FROM portal_usuarios
               WHERE id = %s
               LIMIT 1""",
            (user_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def list_modules_for_user(user: dict) -> list[dict]:
    ensure_tables()
    if bool(user.get('es_admin')):
        with pg_cursor() as cur:
            cur.execute(
                """SELECT id, codigo, titulo, descripcion, ruta, image_url, orden, activo
                   FROM portal_modulos
                   WHERE activo
                   ORDER BY orden, id"""
            )
            return _dict_rows(cur)

    with pg_cursor() as cur:
        cur.execute(
            """SELECT m.id, m.codigo, m.titulo, m.descripcion, m.ruta, m.image_url, m.orden, m.activo
               FROM portal_modulos m
               JOIN portal_usuario_modulo um ON um.modulo_id = m.id
               WHERE um.usuario_id = %s
                 AND um.puede_ver
                 AND m.activo
               ORDER BY m.orden, m.id""",
            (user['id'],),
        )
        return _dict_rows(cur)


def list_users() -> list[dict]:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """SELECT id, username, nombre, activo, es_admin, created_at, updated_at
               FROM portal_usuarios
               ORDER BY id"""
        )
        return _dict_rows(cur)


def create_user(data: dict) -> dict:
    ensure_tables()
    username = str(data.get('username') or '').strip().lower()
    nombre = str(data.get('nombre') or '').strip()
    password = str(data.get('password') or '').strip()
    es_admin = bool(data.get('es_admin', False))
    activo = bool(data.get('activo', True))
    if not username or not nombre or not password:
        raise ValueError('username, nombre y password son obligatorios')
    if len(password) < 6:
        raise ValueError('password debe tener al menos 6 caracteres')

    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO portal_usuarios(username, password_hash, nombre, activo, es_admin)
                   VALUES (%s, %s, %s, %s, %s)
                   RETURNING id, username, nombre, activo, es_admin, created_at, updated_at""",
                (username, generate_password_hash(password), nombre, activo, es_admin),
            )
            user = dict(cur.fetchone() or {})
    return user


def update_user(user_id: int, data: dict) -> dict:
    ensure_tables()
    fields = []
    params: list[Any] = []

    if 'username' in data:
        username = str(data.get('username') or '').strip().lower()
        if not username:
            raise ValueError('username no puede ser vacio')
        fields.append("username = %s")
        params.append(username)
    if 'nombre' in data:
        nombre = str(data.get('nombre') or '').strip()
        if not nombre:
            raise ValueError('nombre no puede ser vacio')
        fields.append("nombre = %s")
        params.append(nombre)
    if 'password' in data and str(data.get('password') or '').strip():
        password = str(data.get('password') or '').strip()
        if len(password) < 6:
            raise ValueError('password debe tener al menos 6 caracteres')
        fields.append("password_hash = %s")
        params.append(generate_password_hash(password))
    if 'activo' in data:
        fields.append("activo = %s")
        params.append(bool(data.get('activo')))
    if 'es_admin' in data:
        fields.append("es_admin = %s")
        params.append(bool(data.get('es_admin')))

    if not fields:
        raise ValueError('No se recibieron campos para actualizar')

    params.extend([user_id])
    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"""UPDATE portal_usuarios
                    SET {', '.join(fields)}, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, username, nombre, activo, es_admin, created_at, updated_at""",
                tuple(params),
            )
            row = cur.fetchone()
    if not row:
        raise ValueError('Usuario no encontrado')
    return dict(row)


def list_modules_admin() -> list[dict]:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """SELECT id, codigo, titulo, descripcion, ruta, image_url, orden, activo, created_at, updated_at
               FROM portal_modulos
               ORDER BY orden, id"""
        )
        return _dict_rows(cur)


def create_module(data: dict) -> dict:
    ensure_tables()
    payload = {
        'codigo': str(data.get('codigo') or '').strip().lower(),
        'titulo': str(data.get('titulo') or '').strip(),
        'descripcion': str(data.get('descripcion') or '').strip(),
        'ruta': str(data.get('ruta') or '').strip(),
        'image_url': str(data.get('image_url') or '').strip() or None,
        'orden': int(data.get('orden') or 100),
        'activo': bool(data.get('activo', True)),
    }
    if not payload['codigo'] or not payload['titulo'] or not payload['ruta']:
        raise ValueError('codigo, titulo y ruta son obligatorios')
    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO portal_modulos(codigo, titulo, descripcion, ruta, image_url, orden, activo)
                   VALUES (%(codigo)s, %(titulo)s, %(descripcion)s, %(ruta)s, %(image_url)s, %(orden)s, %(activo)s)
                   RETURNING id, codigo, titulo, descripcion, ruta, image_url, orden, activo, created_at, updated_at""",
                payload,
            )
            row = cur.fetchone()
    return dict(row or {})


def update_module(module_id: int, data: dict) -> dict:
    ensure_tables()
    fields = []
    params: list[Any] = []
    map_fields = ('codigo', 'titulo', 'descripcion', 'ruta', 'image_url', 'orden', 'activo')
    for key in map_fields:
        if key not in data:
            continue
        value = data.get(key)
        if key in {'codigo', 'titulo', 'ruta'}:
            value = str(value or '').strip()
            if key == 'codigo':
                value = value.lower()
            if not value:
                raise ValueError(f'{key} no puede ser vacio')
        if key == 'descripcion':
            value = str(value or '').strip()
        if key == 'image_url':
            value = str(value or '').strip() or None
        if key == 'orden':
            value = int(value or 100)
        if key == 'activo':
            value = bool(value)
        fields.append(f"{key} = %s")
        params.append(value)
    if not fields:
        raise ValueError('No se recibieron campos para actualizar')

    params.append(module_id)
    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"""UPDATE portal_modulos
                    SET {', '.join(fields)}, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, codigo, titulo, descripcion, ruta, image_url, orden, activo, created_at, updated_at""",
                tuple(params),
            )
            row = cur.fetchone()
    if not row:
        raise ValueError('Modulo no encontrado')
    return dict(row)


def delete_module(module_id: int) -> bool:
    ensure_tables()
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM portal_modulos WHERE id = %s", (module_id,))
            return cur.rowcount > 0


def get_user_access_map(user_id: int) -> list[int]:
    ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """SELECT modulo_id
               FROM portal_usuario_modulo
               WHERE usuario_id = %s
                 AND puede_ver""",
            (user_id,),
        )
        return [int(r['modulo_id']) for r in _dict_rows(cur)]


def set_user_access_map(user_id: int, module_ids: list[int]) -> dict:
    ensure_tables()
    user = get_user_by_id(user_id)
    if not user:
        raise ValueError('Usuario no encontrado')

    ids = sorted(set(int(i) for i in (module_ids or [])))
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM portal_usuario_modulo WHERE usuario_id = %s", (user_id,))
            if ids:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO portal_usuario_modulo(usuario_id, modulo_id, puede_ver)
                       VALUES %s
                       ON CONFLICT (usuario_id, modulo_id) DO UPDATE SET puede_ver = EXCLUDED.puede_ver""",
                    [(user_id, module_id, True) for module_id in ids],
                )
    return {'usuario_id': user_id, 'module_ids': ids}
