"""Conexión a la base del módulo.

El módulo maneja su propio engine/sesión para no depender de cómo la app
anfitriona configuró SQLAlchemy. Usa, en este orden:
  app.config["RUTAS_DATABASE_URL"] -> app.config["SQLALCHEMY_DATABASE_URI"] -> env DATABASE_URL
Todas las tablas llevan prefijo rt_ para no chocar con las de la app anfitriona.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker


class Base(DeclarativeBase):
    pass


Session = scoped_session(sessionmaker(expire_on_commit=False))
_engine = None


def _normalize(url: str) -> str:
    # Railway entrega postgres://, SQLAlchemy 2 necesita postgresql://
    if url and url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def init_db(app):
    global _engine
    url = (app.config.get("RUTAS_DATABASE_URL")
           or app.config.get("SQLALCHEMY_DATABASE_URI")
           or os.environ.get("DATABASE_URL"))
    if not url:
        raise RuntimeError("rutas: falta DATABASE_URL / SQLALCHEMY_DATABASE_URI / RUTAS_DATABASE_URL")
    _engine = create_engine(_normalize(url), pool_pre_ping=True, future=True)
    Session.configure(bind=_engine)

    @app.teardown_appcontext
    def _remove_session(exc=None):
        Session.remove()

    return _engine


def create_all():
    from . import models  # noqa: F401  (registra las tablas)
    Base.metadata.create_all(_engine)
