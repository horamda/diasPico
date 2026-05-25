import os
from pathlib import Path
from flask import Flask, send_from_directory
from flask_cors import CORS
from app.config import configs
from app.extensions import db, migrate


def create_app(env: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)

    # Load config
    env = env or os.getenv('FLASK_ENV', 'development')
    app.config.from_object(configs.get(env, configs['default']))

    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app)

    # Las tablas se crean lazy en el primer uso de cada repository.
    # No bloqueamos el arranque con conexiones a Railway.

    # Register blueprints
    from app.routes import upload, picos, recursos, feriados, parametros, articulos, ausentismo, rechazos, eventos, dropsize, kpi_objetivos, planificacion_picos, catalogo, flota, simulacion_logistica, sync_sheets, segmentacion
    app.register_blueprint(upload.bp)
    app.register_blueprint(picos.bp)
    app.register_blueprint(recursos.bp)
    app.register_blueprint(feriados.bp)
    app.register_blueprint(parametros.bp)
    app.register_blueprint(articulos.bp)
    app.register_blueprint(ausentismo.bp)
    app.register_blueprint(rechazos.bp)
    app.register_blueprint(eventos.bp)
    app.register_blueprint(dropsize.bp)
    app.register_blueprint(kpi_objetivos.bp)
    app.register_blueprint(planificacion_picos.bp)
    app.register_blueprint(catalogo.bp)
    app.register_blueprint(flota.bp)
    app.register_blueprint(simulacion_logistica.bp)
    app.register_blueprint(sync_sheets.bp)
    app.register_blueprint(segmentacion.bp)

    @app.get('/')
    def panel():
        project_root = Path(__file__).resolve().parent.parent
        return send_from_directory(project_root, 'panel_dias_pico_v3.html')

    @app.get('/reporte-picos')
    def reporte_picos():
        project_root = Path(__file__).resolve().parent.parent
        return send_from_directory(project_root, 'reporte_picos.html')

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'env': env}

    return app
