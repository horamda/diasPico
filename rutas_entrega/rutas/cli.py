import json

import click
from flask.cli import AppGroup

cli = AppGroup("rutas", help="Rutas de entrega: base, semilla, importación y sync con ChessERP.")


@cli.command("init-db")
def init_db_cmd():
    """Crea las tablas rt_* (si no existen)."""
    from .db import create_all
    create_all()
    click.echo("Tablas rt_* listas.")


@cli.command("seed")
@click.option("--archivo", default=None, help="JSON de semilla (por defecto rutas/data/seed.json)")
def seed_cmd(archivo):
    """Carga depósitos, localidades→sucursal, vehículos y plan de la hoja INFORME."""
    from .sync import cargar_semilla
    cargar_semilla(archivo)
    click.echo("Semilla cargada.")


@cli.command("import-excel")
@click.argument("path", type=click.Path(exists=True))
@click.option("--sucursal", default=2, show_default=True, help="Sucursal del ERP a importar de la hoja CLIENTES")
@click.option("--pisar-dias", is_flag=True, help="Reemplaza días ya editados en la app por los de la planilla")
def import_excel_cmd(path, sucursal, pisar_dias):
    """Importa ARMADO DE DIAS DE ENTREGA (.xlsx/.xlsm)."""
    from .sync import importar_excel
    click.echo(json.dumps(importar_excel(path, sucursal_erp=sucursal, pisar_dias=pisar_dias), indent=1))


@cli.command("sync-chess")
@click.option("--sucursal", "sucursales", multiple=True, type=int, help="Repetible. Default: CHESS_SUCURSALES")
@click.option("--dias-desde-erp", is_flag=True, help="A los clientes nuevos les pone los días que tienen en el ERP")
def sync_cmd(sucursales, dias_desde_erp):
    """Sincroniza clientes desde ChessERP."""
    from .sync import sincronizar_chess
    click.echo(json.dumps(sincronizar_chess(list(sucursales) or None, inicializar_dias_desde_erp=dias_desde_erp), indent=1))
