from __future__ import annotations

from functools import wraps

from flask import Blueprint, g, jsonify, redirect, render_template, request, session, url_for

from app.services import portal_svc

bp = Blueprint('portal', __name__)


def _json_error(msg: str, code: int = 400):
    return jsonify({'ok': False, 'error': msg}), code


@bp.before_app_request
def _load_user():
    user_id = session.get('portal_user_id')
    try:
        g.portal_user = portal_svc.get_user_by_id(int(user_id)) if user_id else None
    except Exception:
        g.portal_user = None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.portal_user:
            if request.path.startswith('/api/'):
                return _json_error('No autenticado', 401)
            return redirect(url_for('portal.login', next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.portal_user:
            if request.path.startswith('/api/'):
                return _json_error('No autenticado', 401)
            return redirect(url_for('portal.login', next=request.path))
        if not bool(g.portal_user.get('es_admin')):
            if request.path.startswith('/api/'):
                return _json_error('No autorizado', 403)
            return redirect(url_for('portal.portal_home'))
        return view(*args, **kwargs)

    return wrapped


@bp.get('/login')
def login():
    try:
        has_users = portal_svc.has_users()
    except Exception:
        return render_template('portal_login.html', error='Base no disponible. Reintentar en unos segundos.'), 503
    if not has_users:
        return redirect(url_for('portal.setup_inicial'))
    if g.portal_user:
        return redirect(url_for('portal.portal_home'))
    return render_template('portal_login.html')


@bp.post('/login')
def login_submit():
    data = request.get_json(silent=True) or request.form or {}
    username = str(data.get('username') or '')
    password = str(data.get('password') or '')
    user = portal_svc.authenticate(username, password)
    if not user:
        if request.is_json:
            return _json_error('Credenciales invalidas', 401)
        return render_template('portal_login.html', error='Credenciales invalidas'), 401

    session['portal_user_id'] = int(user['id'])
    target = request.args.get('next') or url_for('portal.portal_home')
    if request.is_json:
        return jsonify({'ok': True, 'data': {'redirect': target}})
    return redirect(target)


@bp.get('/logout')
def logout():
    session.pop('portal_user_id', None)
    return redirect(url_for('portal.login'))


@bp.route('/setup-inicial', methods=['GET', 'POST'])
def setup_inicial():
    try:
        has_users = portal_svc.has_users()
    except Exception:
        return render_template('portal_setup.html', error='Base no disponible. Reintentar en unos segundos.'), 503
    if has_users:
        return redirect(url_for('portal.login'))
    if request.method == 'GET':
        return render_template('portal_setup.html')

    data = request.get_json(silent=True) or request.form or {}
    try:
        user = portal_svc.create_initial_admin(
            username=str(data.get('username') or ''),
            password=str(data.get('password') or ''),
            nombre=str(data.get('nombre') or ''),
        )
        session['portal_user_id'] = int(user['id'])
        if request.is_json:
            return jsonify({'ok': True, 'data': user})
        return redirect(url_for('portal.portal_home'))
    except ValueError as exc:
        if request.is_json:
            return _json_error(str(exc))
        return render_template('portal_setup.html', error=str(exc)), 400


@bp.get('/portal')
@login_required
def portal_home():
    modules = portal_svc.list_modules_for_user(g.portal_user)
    return render_template('portal_home.html', user=g.portal_user, modules=modules)


@bp.get('/portal/admin')
@admin_required
def portal_admin():
    return render_template('portal_admin.html', user=g.portal_user)


@bp.get('/api/portal/dashboard-kpis')
@login_required
def dashboard_kpis():
    sucursal_id = request.args.get('sucursal', 'TODAS')
    empresa_id  = request.args.get('empresa_id', '1')
    try:
        from app.services import portal_dashboard_svc, cache_svc
        data = cache_svc.get_or_set(
            f'portal:dashboard_kpis:{empresa_id}:{sucursal_id}',
            lambda: portal_dashboard_svc.get_dashboard_kpis(empresa_id, sucursal_id),
            ttl_seconds=300,
        )
        return jsonify({'ok': True, 'data': data})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.get('/api/portal/me')
@login_required
def me():
    return jsonify({'ok': True, 'data': g.portal_user})


@bp.get('/api/portal/modulos')
@login_required
def my_modules():
    return jsonify({'ok': True, 'data': portal_svc.list_modules_for_user(g.portal_user)})


@bp.get('/api/portal/admin/usuarios')
@admin_required
def admin_users():
    return jsonify({'ok': True, 'data': portal_svc.list_users()})


@bp.post('/api/portal/admin/usuarios')
@admin_required
def admin_users_create():
    data = request.get_json(force=True) or {}
    try:
        user = portal_svc.create_user(data)
        return jsonify({'ok': True, 'data': user})
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.put('/api/portal/admin/usuarios/<int:user_id>')
@admin_required
def admin_users_update(user_id: int):
    data = request.get_json(force=True) or {}
    try:
        user = portal_svc.update_user(user_id, data)
        return jsonify({'ok': True, 'data': user})
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get('/api/portal/admin/usuarios/<int:user_id>/accesos')
@admin_required
def admin_user_accesses(user_id: int):
    try:
        ids = portal_svc.get_user_access_map(user_id)
        return jsonify({'ok': True, 'data': {'usuario_id': user_id, 'module_ids': ids}})
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.put('/api/portal/admin/usuarios/<int:user_id>/accesos')
@admin_required
def admin_user_accesses_update(user_id: int):
    data = request.get_json(force=True) or {}
    ids = data.get('module_ids') or []
    if not isinstance(ids, list):
        return _json_error('module_ids debe ser una lista')
    try:
        result = portal_svc.set_user_access_map(user_id, [int(i) for i in ids])
        return jsonify({'ok': True, 'data': result})
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get('/api/portal/admin/modulos')
@admin_required
def admin_modules():
    return jsonify({'ok': True, 'data': portal_svc.list_modules_admin()})


@bp.post('/api/portal/admin/modulos')
@admin_required
def admin_modules_create():
    data = request.get_json(force=True) or {}
    try:
        item = portal_svc.create_module(data)
        return jsonify({'ok': True, 'data': item})
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.put('/api/portal/admin/modulos/<int:module_id>')
@admin_required
def admin_modules_update(module_id: int):
    data = request.get_json(force=True) or {}
    try:
        item = portal_svc.update_module(module_id, data)
        return jsonify({'ok': True, 'data': item})
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.delete('/api/portal/admin/modulos/<int:module_id>')
@admin_required
def admin_modules_delete(module_id: int):
    try:
        ok = portal_svc.delete_module(module_id)
        if not ok:
            return _json_error('Modulo no encontrado', 404)
        return jsonify({'ok': True, 'data': {'deleted': True}})
    except Exception as exc:
        return _json_error(str(exc), 500)
