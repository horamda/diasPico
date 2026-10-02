"""Delivery planning integrated into the logistics portal."""
from functools import wraps
from flask import Blueprint, g, jsonify, redirect, request, url_for
from .db import init_db, create_all

bp = Blueprint('rutas', __name__, template_folder='templates', static_folder='static', static_url_path='/rutas-static')

import_bp = Blueprint('rutas_importaciones', __name__)

def portal_access(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        from app.services.portal_svc import list_modules_for_user
        user = getattr(g, 'portal_user', None)
        if not user:
            if '/api/' in request.path:
                return jsonify(error='Sesión vencida. Ingresá nuevamente al portal.'), 401
            return redirect(url_for('portal.login', next=request.path))
        module = 'importaciones_datos' if request.blueprint == 'rutas_importaciones' else 'rutas_entrega'
        if not any(m['codigo'] == module for m in list_modules_for_user(user)):
            return jsonify(error='No tenés acceso a este módulo.'), 403
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            from urllib.parse import urlsplit
            origin = request.headers.get('Origin')
            if origin and urlsplit(origin).netloc != request.host:
                return jsonify(error='Origen no permitido'), 403
        if '/api/' in request.path:
            create_all()
        return view(*args, **kwargs)
    return wrapped

def init_rutas(app, url_prefix='/rutas'):
    init_db(app)
    app.config['RUTAS_LOGIN_REQUIRED'] = portal_access
    app.config['RUTAS_USUARIO'] = lambda: str(g.portal_user.get('username') or g.portal_user['id'])
    from . import routes
    app.register_blueprint(bp, url_prefix=url_prefix)
    app.register_blueprint(import_bp, url_prefix='/importaciones/rutas')
    return bp
