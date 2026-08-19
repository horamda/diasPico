from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from app.services import frescura_svc


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def main() -> int:
    env = os.getenv("FLASK_ENV") or ("production" if os.getenv("RAILWAY_ENVIRONMENT") else "development")
    app = create_app(env)
    with app.app_context():
        result = frescura_svc.sync_frescura_from_api()
    print(json.dumps(result, ensure_ascii=True, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
