from __future__ import annotations

import unicodedata
from urllib.parse import urljoin

import requests
from flask import current_app


class ExternalCatalogError(RuntimeError):
    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


def _settings() -> tuple[str, str, int]:
    base_url = str(current_app.config.get("EXTERNAL_API_BASE_URL") or "").strip()
    api_key = str(current_app.config.get("EXTERNAL_API_KEY") or "").strip()
    timeout = int(current_app.config.get("EXTERNAL_API_TIMEOUT") or 20)
    if not base_url:
        raise ExternalCatalogError("EXTERNAL_API_BASE_URL no configurada.", 503)
    if not api_key:
        raise ExternalCatalogError("EXTERNAL_API_KEY no configurada.", 503)
    return base_url.rstrip("/") + "/", api_key, timeout


def _get(path: str, params: dict | None = None) -> dict:
    base_url, api_key, timeout = _settings()
    url = urljoin(base_url, "api/v1/external/" + path.lstrip("/"))
    try:
        response = requests.get(
            url,
            headers={"X-API-Key": api_key},
            params={k: v for k, v in (params or {}).items() if v not in (None, "")},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise ExternalCatalogError(f"No se pudo conectar con API externa: {exc}", 503) from exc

    if response.status_code == 401:
        raise ExternalCatalogError("API key externa invalida o ausente.", 401)
    if response.status_code == 503:
        raise ExternalCatalogError("API externa no configurada.", 503)
    if response.status_code >= 400:
        try:
            detail = response.json().get("error") or response.text
        except ValueError:
            detail = response.text
        raise ExternalCatalogError(f"API externa error {response.status_code}: {detail}", response.status_code)
    return response.json()


def get_empresas(activa: str | int | None = "1") -> dict:
    return _get("empresas", {"activa": activa})


def get_sucursales(empresa_id: str | int | None = None, activa: str | int | None = "1") -> dict:
    return _get("sucursales", {"empresa_id": empresa_id, "activa": activa})


def get_empleados(params: dict | None = None) -> dict:
    return _get("empleados", params or {})


def get_catalogo(params: dict | None = None) -> dict:
    return _get("catalogo", params or {})


def _puestos_empleado(empleado: dict) -> list[str]:
    puestos = []
    if empleado.get("puesto_nombre"):
        puestos.append(str(empleado["puesto_nombre"]))
    puestos.extend(str(x) for x in (empleado.get("puestos_adicionales_nombres") or []))
    return [_norm(p) for p in puestos if p and str(p).strip()]


def _norm(value: str) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _has_any(texts: list[str], needles: tuple[str, ...]) -> bool:
    return any(any(needle in text for needle in needles) for text in texts)


def get_dotacion_operativa(params: dict | None = None) -> dict:
    query = {
        "estado": "activo",
        "per_page": 500,
        **(params or {}),
    }
    if not query.get("tipo_empleado") and not query.get("tipo") and not query.get("puesto"):
        query["tipo_empleado"] = "choferes,ayudantes,acompanantes,operarios"
    data = get_empleados(query)
    empleados = data.get("data") or []
    resumen = {
        "total_empleados": len(empleados),
        "choferes": 0,
        "ayudantes": 0,
        "acompanantes": 0,
        "operarios": 0,
        "otros": 0,
    }
    por_sucursal: dict[str, dict] = {}
    for empleado in empleados:
        puestos = _puestos_empleado(empleado)
        suc_id = str(empleado.get("sucursal_id") or "SIN_SUCURSAL")
        suc_nombre = empleado.get("sucursal_nombre") or suc_id
        item = por_sucursal.setdefault(suc_id, {
            "sucursal_id": suc_id,
            "sucursal_nombre": suc_nombre,
            "total_empleados": 0,
            "choferes": 0,
            "ayudantes": 0,
            "acompanantes": 0,
            "operarios": 0,
            "otros": 0,
        })
        item["total_empleados"] += 1

        matched = False
        if _has_any(puestos, ("chofer",)):
            resumen["choferes"] += 1
            item["choferes"] += 1
            matched = True
        if _has_any(puestos, ("ayudante",)):
            resumen["ayudantes"] += 1
            item["ayudantes"] += 1
            matched = True
        if _has_any(puestos, ("acompanante",)):
            resumen["acompanantes"] += 1
            item["acompanantes"] += 1
            matched = True
        if _has_any(puestos, ("operario", "almacen")):
            resumen["operarios"] += 1
            item["operarios"] += 1
            matched = True
        if not matched:
            resumen["otros"] += 1
            item["otros"] += 1

    return {
        "resumen": resumen,
        "por_sucursal": sorted(por_sucursal.values(), key=lambda x: x["sucursal_nombre"]),
        "empleados": empleados,
        "pagination": data.get("pagination"),
        "fuente": "external_api_contract_v1",
    }
