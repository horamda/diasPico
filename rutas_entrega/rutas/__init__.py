"""Módulo Rutas de Entrega (Blueprint Flask).

Uso en otra app:
    from rutas import init_rutas
    init_rutas(app)                  # monta en /rutas
    init_rutas(app, url_prefix="/logistica/rutas")

Config opcional (app.config):
    RUTAS_DATABASE_URL      base distinta a la de la app (por defecto usa SQLALCHEMY_DATABASE_URI / DATABASE_URL)
    RUTAS_LOGIN_REQUIRED    decorador de login de tu app (ej. flask_login.login_required)
    RUTAS_USUARIO           función sin args que devuelve el nombre del usuario actual (para el historial)
    RUTAS_SYNC_TOKEN        token para POST /rutas/api/sync desde un cron
    RUTAS_CREATE_TABLES     True (default) crea las tablas rt_* al iniciar
"""
from flask import Blueprint

from .db import create_all, init_db

bp = Blueprint("rutas", __name__, template_folder="templates", static_folder="static",
               static_url_path="/rutas-static")


def init_rutas(app, url_prefix="/rutas"):
    init_db(app)
    if app.config.get("RUTAS_CREATE_TABLES", True):
        create_all()
    from . import routes  # noqa: F401  (registra las vistas en bp)
    from .cli import cli
    app.register_blueprint(bp, url_prefix=url_prefix)
    app.cli.add_command(cli)
    return bp
