import pytest
from sqlalchemy import create_engine
from app.config import AppSettings, Config


@pytest.mark.parametrize('scheme', ['postgres', 'postgresql', 'postgresql+psycopg', 'postgresql+psycopg2'])
def test_sqlalchemy_uses_installed_driver_and_pool_keeps_plain_dsn(scheme):
    settings = AppSettings(_env_file=None, RAILWAY_URL=f'{scheme}://test:secret@localhost/example')
    config = Config(settings)
    assert config.RAILWAY_URL == 'postgresql://test:secret@localhost/example'
    assert config.DATABASE_URL == config.RAILWAY_URL
    assert config.SQLALCHEMY_DATABASE_URI == 'postgresql+psycopg2://test:secret@localhost/example'
    engine = create_engine(config.SQLALCHEMY_DATABASE_URI)
    assert engine.dialect.driver == 'psycopg2'
    engine.dispose()
