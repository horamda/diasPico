"""Comandos `flask rutas ...` (los usa el cron de Railway)."""
import json
import os
from datetime import date, timedelta

import click
from flask.cli import AppGroup

cli = AppGroup("rutas", help="Rutas de entrega: tablas y ventas de ChessERP.")


def sucursales_default():
    return [int(x) for x in os.environ.get("CHESS_SUCURSALES", "2").split(",") if x.strip().isdigit()]


@cli.command("init-db")
def init_db_cmd():
    """Crea las tablas rt_* (si no existen)."""
    from .db import create_all
    create_all()
    click.echo("Tablas rt_* listas.")


@cli.command("sync-ventas")
@click.option("--dias", default=7, show_default=True, help="Días hacia atrás desde hoy (incluye hoy)")
@click.option("--desde", type=click.DateTime(["%Y-%m-%d"]), help="Fecha inicial; pisa --dias")
@click.option("--hasta", type=click.DateTime(["%Y-%m-%d"]), help="Fecha final (default: hoy)")
@click.option("--detalle", is_flag=True, help="Trae una fila por artículo (bultos y HL). Pesa ~7 MB por día")
@click.option("--sucursal", "sucursales", multiple=True, type=int, help="Repetible. Default: CHESS_SUCURSALES o 2")
def sync_ventas_cmd(dias, desde, hasta, detalle, sucursales):
    """Carga comprobantes de venta desde ChessERP."""
    from .db import create_all
    from .ventas import sincronizar
    create_all()
    hasta = hasta.date() if hasta else date.today()
    desde = desde.date() if desde else hasta - timedelta(days=dias - 1)
    res = sincronizar(desde, hasta, list(sucursales) or sucursales_default(), detalle=detalle)
    click.echo(json.dumps(res, indent=1))


@cli.command("import-ventas")
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--sucursal", "sucursales", multiple=True, type=int, help="Repetible. Sin indicar: todas")
def import_ventas_cmd(paths, sucursales):
    """Importa uno o más JSON guardados de la API de ventas."""
    from .db import create_all
    from .ventas import importar_json
    create_all()
    click.echo(json.dumps(importar_json(paths, list(sucursales) or None), indent=1))
