from flask_sqlalchemy import SQLAlchemy
try:
    from flask_migrate import Migrate
except ImportError:  # pragma: no cover - optional during tests/local runs
    class Migrate:  # type: ignore[override]
        def init_app(self, *args, **kwargs):
            return None

db = SQLAlchemy()
migrate = Migrate()
