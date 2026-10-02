"""Application-scoped sessions, sharing the portal engine."""
from threading import Lock
from flask import current_app, g
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker

class Base(DeclarativeBase):
    pass

def Session():
    return current_app.extensions['rutas_db']['sessions']()

def init_db(app):
    engine = app.config.get('RUTAS_ENGINE')
    if engine is None:
        url = app.config.get('RUTAS_DATABASE_URL') or app.config['SQLALCHEMY_DATABASE_URI']
        engine = create_engine(url.replace('postgres://', 'postgresql://', 1), pool_pre_ping=True)
    sessions = scoped_session(sessionmaker(bind=engine, expire_on_commit=False), scopefunc=lambda: id(g._get_current_object()))
    app.extensions['rutas_db'] = {'engine': engine, 'sessions': sessions, 'ready': False, 'lock': Lock()}
    @app.teardown_appcontext
    def cleanup(exc=None):
        sessions.remove()

def create_all():
    from . import models
    state = current_app.extensions['rutas_db']
    if state['ready']:
        return
    with state['lock']:
        if not state['ready']:
            with state['engine'].begin() as conn:
                if conn.dialect.name == 'postgresql':
                    from sqlalchemy import text
                    conn.execute(text('SELECT pg_advisory_xact_lock(7319020)'))
                Base.metadata.create_all(conn)
            state['ready'] = True
