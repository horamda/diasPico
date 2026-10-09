from datetime import date
from pathlib import Path

from app.services import control_stock_svc as svc


class _Cursor:
    def __init__(self, results):
        self._results = list(results)
        self._current = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *_args, **_kwargs):
        self._current = self._results.pop(0)

    def fetchall(self):
        return self._current


def _conteo(suc, fecha, persona, articulos, minutos, dispersion=0, correcciones=0):
    return {"sucursal": suc, "fecha": fecha, "persona": persona, "articulos": articulos, "bultos": articulos * 10,
            "con_dispersion": dispersion, "correcciones": correcciones, "minutos": minutos}


def test_month_shift_cruza_anios():
    assert svc._month_shift("2026-01", -1) == "2025-12"
    assert svc._month_shift("2026-11", 3) == "2027-02"


def test_desempeno_agrega_por_persona_y_sucursal(monkeypatch):
    responsables = [{"persona": "ROCHA NICOLAS", "sucursal": "2"}, {"persona": "RODRIGUEZ ANGEL", "sucursal": "1"}]
    conteos = [
        _conteo("1", date(2026, 8, 3), "RODRIGUEZ ANGEL", 20, 30, dispersion=5),
        _conteo("1", date(2026, 9, 1), "RODRIGUEZ ANGEL", 24, 30, dispersion=12),
        _conteo("1", date(2026, 9, 2), "RODRIGUEZ ANGEL", 20, None),
        _conteo("2", date(2026, 9, 1), "ROCHA NICOLAS", 30, 20, correcciones=2),
        _conteo("1", date(2026, 9, 3), "ADMIN", 23, 10),
    ]
    monkeypatch.setattr(svc, "ensure_control_stock_tables", lambda: None)
    monkeypatch.setattr(svc, "pg_cursor", lambda *a, **k: _Cursor([responsables, conteos]))

    data = svc.get_dashboard_desempeno("2026-09", meses=4)

    angel = next(p for p in data["personas"] if p["persona"] == "Rodriguez Angel")
    assert angel["controles"] == 2 and angel["articulos"] == 44
    # La productividad solo usa el control que tiene horario: 24 artículos en 30 minutos.
    assert angel["articulos_por_hora"] == 48.0
    assert angel["dispersion_pct"] == round(12 / 44 * 100, 1)
    rocha = next(p for p in data["personas"] if p["persona"] == "Rocha Nicolas")
    assert rocha["correcciones"] == 2 and rocha["participacion_pct"] == 100.0
    assert data["excluidos"] == [{"responsable": "ADMIN", "controles": 1}]
    assert [s["articulos"] for s in data["sucursales"]] == [44, 30]
    # Junio y julio no tienen controles: la tendencia arranca en agosto.
    assert data["desde"] == "2026-08"
    assert sorted({t["mes"] for t in data["tendencia"]}) == ["2026-08", "2026-09"]
    assert {d["fecha"] for d in data["diario"]} == {"2026-09-01", "2026-09-02"}


def test_dashboard_template_carga_modulo_de_desempeno():
    html = Path("app/templates/control_stock.html").read_text(encoding="utf-8")

    assert 'id="perfRoot"' in html
    assert "control_stock_dashboard.js" in html
    assert "window.perfDashboard?.load(selectedMes,sucursalResumen.value);" in html
    assert "window.perfDashboard?.setAbc(sucursalResumen.value,selectedMes,kpis);" in html
