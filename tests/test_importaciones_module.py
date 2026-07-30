from pathlib import Path

from app import create_app
from app.services import portal_svc


TEMPLATE = Path("app/templates/importaciones_datos.html")


def test_importaciones_route_requires_login():
    app = create_app("testing")
    response = app.test_client().get("/importaciones-datos")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_importaciones_route_renders_for_authenticated_session():
    app = create_app("testing")
    client = app.test_client()
    with client.session_transaction() as session:
        session["portal_user_id"] = 1
    response = client.get("/importaciones-datos")
    assert response.status_code == 200
    assert "Importaciones de datos" in response.get_data(as_text=True)


def test_default_module_points_to_central_import_page():
    module = next(m for m in portal_svc._DEFAULT_MODULES if m["codigo"] == "importaciones_datos")
    assert module["ruta"] == "/importaciones-datos"
    assert module["orden"] < 10


def test_central_page_covers_all_import_groups():
    html = TEMPLATE.read_text(encoding="utf-8")
    expected = (
        "/api/upload/", "/api/segmentacion/", "/api/picos/ausentismo-mensual/import",
        "/api/feriados/sync", "/api/recursos/sync-capacidad", "/api/sync/sheets-operativo",
        "/api/flota/sync-transportes", "/api/rechazos/sync", "/api/frescura/sync",
    )
    for endpoint in expected:
        assert endpoint in html


def test_central_page_preserves_original_configuration_and_filters():
    html = TEMPLATE.read_text(encoding="utf-8")
    expected = (
        'id="sucursal"',
        "monthlyImports",
        "/api/articulos/count",
        "/api/articulos/sin-clasificar",
        'id="source-autoelevador"',
        'id="recalc-autoelevador"',
        "/api/segmentacion/plantillas/servicio/rmd/vigente",
        "/api/segmentacion/score-pesos",
        "/api/segmentacion/parametros",
        "/api/parametros",
        "/api/sucursales",
        "/api/rechazos",
        'id="ausentismo-text"',
        "localStorage.setItem('pico_cfg'",
    )
    for marker in expected:
        assert marker in html


def test_original_upload_tabs_coexist_with_central_page():
    panel = Path("app/templates/panel_dias_pico_v3.html").read_text(encoding="utf-8")
    segmentacion = Path("app/templates/segmentacion_clientes.html").read_text(encoding="utf-8")
    assert "switchTab('upload'" in panel
    assert "switchTab('config'" in panel
    assert 'data-tab="data"' in segmentacion
    assert 'data-tab="settings"' in segmentacion
    assert TEMPLATE.exists()
