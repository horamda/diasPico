from __future__ import annotations

import os
import time
from contextlib import contextmanager
import threading

import psycopg2
import psycopg2.extras
import psycopg2.pool
from flask import current_app

# Ajustar según workers de Gunicorn: total conexiones = workers × POOL_MAX.
# Railway hobby plan: 25 conexiones máx. Con 2 workers: 2×10=20 (seguro).
_POOL_MIN = 1
_POOL_MAX = int(os.environ.get('PG_POOL_MAX', '10'))

# Si el pool está agotado, esperar hasta este tiempo antes de fallar.
_POOL_WAIT_TIMEOUT = 8.0    # segundos
_POOL_WAIT_INTERVAL = 0.05  # poll cada 50 ms

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:
            return _pool
        dsn = current_app.config.get('RAILWAY_URL') or current_app.config.get('DATABASE_URL')
        if not dsn:
            raise RuntimeError('DATABASE_URL or RAILWAY_URL is required for PostgreSQL.')
        _pool = psycopg2.pool.ThreadedConnectionPool(
            _POOL_MIN,
            _POOL_MAX,
            dsn=dsn,
            connect_timeout=10,
        )
        return _pool


@contextmanager
def pg_conn():
    """
    Yields a PostgreSQL connection from the shared pool.
    Si el pool está agotado espera hasta _POOL_WAIT_TIMEOUT antes de fallar.
    Commits on clean exit, rolls back on exception.
    Descarta la conexión del pool si aparece rota.
    """
    pool = _get_pool()
    conn = None
    deadline = time.monotonic() + _POOL_WAIT_TIMEOUT
    while True:
        try:
            conn = pool.getconn()
            break
        except psycopg2.pool.PoolError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(_POOL_WAIT_INTERVAL)

    discard = False
    try:
        yield conn
        conn.commit()
    except psycopg2.OperationalError:
        # Conexión stale (ej. Railway reinició): remover del pool.
        discard = True
        raise
    except Exception:
        try:
            conn.rollback()
        except Exception:
            discard = True
        raise
    finally:
        pool.putconn(conn, close=discard)


@contextmanager
def pg_cursor(dict_cursor: bool = True):
    """Yields a RealDictCursor (o cursor plano) dentro de una conexión del pool."""
    factory = psycopg2.extras.RealDictCursor if dict_cursor else None
    with pg_conn() as conn:
        with conn.cursor(cursor_factory=factory) as cur:
            yield cur
