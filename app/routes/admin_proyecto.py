from __future__ import annotations

from flask import Blueprint, jsonify

from app.services import db_admin_svc


bp = Blueprint('admin_proyecto', __name__, url_prefix='/api/admin-proyecto')


def _ok(data):
    return jsonify({'ok': True, 'data': data})


def _err(error: Exception, code: int = 500):
    return jsonify({'ok': False, 'error': str(error)}), code


@bp.get('/resumen')
def resumen():
    try:
        return _ok(db_admin_svc.overview())
    except Exception as exc:
        return _err(exc)


@bp.get('/dashboard')
def dashboard():
    try:
        return _ok(db_admin_svc.dashboard_summary())
    except Exception as exc:
        return _err(exc)


@bp.get('/tablas')
def tablas():
    try:
        return _ok(db_admin_svc.list_tables())
    except Exception as exc:
        return _err(exc)


@bp.get('/indices')
def indices():
    try:
        return _ok(db_admin_svc.list_indexes())
    except Exception as exc:
        return _err(exc)


@bp.get('/candidatas-limpieza')
def candidatas_limpieza():
    try:
        return _ok(db_admin_svc.cleanup_candidates())
    except Exception as exc:
        return _err(exc)
