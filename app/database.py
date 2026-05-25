from contextlib import contextmanager
import psycopg2
import psycopg2.extras
import pymysql
import pymysql.cursors
from flask import current_app


@contextmanager
def pg_conn():
    """PostgreSQL connection (Railway). Auto-commits and closes."""
    conn = psycopg2.connect(current_app.config['RAILWAY_URL'], connect_timeout=5)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def pg_cursor(dict_cursor=True):
    """Yields a psycopg2 cursor within a managed connection."""
    factory = psycopg2.extras.RealDictCursor if dict_cursor else None
    with pg_conn() as conn:
        with conn.cursor(cursor_factory=factory) as cur:
            yield cur


@contextmanager
def mysql_conn():
    """MySQL connection (ausentismo). Read-only use."""
    cfg = current_app.config
    conn = pymysql.connect(
        host=cfg['MYSQL_HOST'],
        user=cfg['MYSQL_USER'],
        password=cfg['MYSQL_PASSWORD'],
        db=cfg['MYSQL_DB'],
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5
    )
    try:
        yield conn
    finally:
        conn.close()
