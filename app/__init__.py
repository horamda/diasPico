import importlib
import os
from flask import Flask, redirect, render_template, request, session, url_for
from flask_cors import CORS
from app.extensions import db, migrate


BLUEPRINT_MODULES = (
    'app.routes.portal',
    'app.routes.upload',
    'app.routes.picos',
    'app.routes.recursos',
    'app.routes.feriados',
    'app.routes.parametros',
    'app.routes.articulos',
    'app.routes.rechazos',
    'app.routes.eventos',
    'app.routes.dropsize',
    'app.routes.kpi_objetivos',
    'app.routes.planificacion_picos',
    'app.routes.catalogo',
    'app.routes.flota',
    'app.routes.simulacion_logistica',
    'app.routes.sync_sheets',
    'app.routes.frescura',
    'app.routes.segmentacion',
    'app.routes.admin_proyecto',
)


def register_blueprints(app: Flask) -> None:
    for module_name in BLUEPRINT_MODULES:
        module = importlib.import_module(module_name)
        app.register_blueprint(module.bp)


def create_app(env: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)

    # Load config
    from app.config import configs
    env = env or os.getenv('FLASK_ENV') or ('production' if os.getenv('RAILWAY_ENVIRONMENT') else 'development')
    app.config.from_object(configs.get(env, configs['default']))

    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app)

    # Las tablas se crean lazy en el primer uso de cada repository.
    # No bloqueamos el arranque con conexiones a Railway.

    register_blueprints(app)

    def _guard():
        if session.get('portal_user_id'):
            return None
        return redirect(url_for('portal.login', next=request.path))

    @app.get('/')
    def panel():
        if not session.get('portal_user_id'):
            return redirect(url_for('portal.login'))
        return redirect(url_for('portal.portal_home'))

    @app.get('/dias-pico')
    def dias_pico():
        guarded = _guard()
        if guarded:
            return guarded
        return render_template('panel_dias_pico_v3.html')

    @app.get('/reporte-picos')
    def reporte_picos():
        guarded = _guard()
        if guarded:
            return guarded
        return render_template('reporte_picos.html')

    @app.get('/segmentacion-clientes')
    @app.get('/admin/segmentacion')
    def segmentacion_clientes():
        guarded = _guard()
        if guarded:
            return guarded
        return render_template('segmentacion_clientes.html')

    @app.get('/frescura-oportunidades')
    def frescura_oportunidades():
        guarded = _guard()
        if guarded:
            return guarded
        return render_template('frescura_oportunidades.html')

    @app.get('/importaciones-datos')
    def importaciones_datos():
        guarded = _guard()
        if guarded:
            return guarded
        return render_template('importaciones_datos.html')

    @app.get('/admin')
    @app.get('/admin/proyecto')
    @app.get('/dashboard')
    def admin_proyecto():
        guarded = _guard()
        if guarded:
            return guarded
        return render_template('admin_proyecto.html')

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'env': env}

    return app
