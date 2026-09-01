import os
import subprocess
import sys
from pathlib import Path


def _rerun_with_local_venv() -> None:
    root = Path(__file__).resolve().parent
    venv_python = root / 'venv' / 'Scripts' / 'python.exe'
    if not venv_python.exists():
        return
    try:
        current = Path(sys.executable).resolve()
        target = venv_python.resolve()
    except OSError:
        returngit
    if current == target:
        return
    print(f"Usando entorno virtual local: {target}", flush=True)
    raise SystemExit(subprocess.call([str(target), str(Path(__file__).resolve()), *sys.argv[1:]]))


_rerun_with_local_venv()

from app import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.getenv('PORT', '5001'))
    app.run(host='0.0.0.0', port=port, debug=app.config['DEBUG'])
