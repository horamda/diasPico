from __future__ import annotations

from flask import Blueprint, jsonify, request

from flask import current_app
from app.services import cache_svc
from app.services import sync_sheets_service as svc
from app.services.sheets_svc import _fetch_rows, _split_sheet_urls
from app.repositories import operacion_camiones_repository as op_repo

bp = Blueprint("sync_sheets", __name__, url_prefix="/api/sync")


def _json_call(fn, ok_status: int = 200):
    try:
        return jsonify(fn()), ok_status
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.post("/sheets-operativo")
def sync_sheets_operativo():
    data = request.get_json(force=True) or {}
    empresa_id = str(data.get("empresa_id") or "1")
    def _run():
        result = svc.sync_operacion_camiones(empresa_id)
        cache_svc.clear("picos:")
        cache_svc.clear("portal:")
        cache_svc.clear("planificacion_picos:")
        return result
    return _json_call(_run)


@bp.get("/debug-sheets")
def debug_sheets():
    """
    Muestra las columnas reales y las primeras 3 filas de cada tab.
    Usá esto para verificar que los headers coincidan con lo esperado.
    GET /api/sync/debug-sheets
    """
    entrega_urls  = _split_sheet_urls(current_app.config.get("DOTACION_ENTREGA_URL",  ""))
    recargas_urls = _split_sheet_urls(current_app.config.get("DOTACION_RECARGAS_URL", ""))
    result = []
    tab_names = ["datos_mda (CC s1)", "datos_dol (DOL s1)", "recargas_mda (CC s2)", "recargas_dol (DOL s2)"]
    tab_configs = list(zip(tab_names, [(u, 1) for u in entrega_urls] + [(u, 2) for u in recargas_urls]))

    for tab_name, (url, nro_salida) in tab_configs:
        try:
            rows = _fetch_rows(url)
            info = {
                "tab": tab_name,
                "nro_salida": nro_salida,
                "url_gid": url.split("gid=")[-1] if "gid=" in url else "?",
                "total_filas": len(rows),
                "columnas": list(rows[0].keys()) if rows else [],
                "primeras_3": rows[:3],
            }
        except Exception as exc:
            info = {"tab": tab_name, "error": str(exc)}
        result.append(info)

    return jsonify(result)


@bp.get("/operacion-camiones/anios")
def operacion_anios():
    """Devuelve los años y meses disponibles en la tabla operacion_camiones."""
    empresa_id = request.args.get("empresa_id", "1")
    return _json_call(lambda: op_repo.get_anios_disponibles(empresa_id))


@bp.get("/operacion-camiones/mensual")
def operacion_mensual():
    empresa_id  = request.args.get("empresa_id", "1")
    sucursal_id = request.args.get("sucursal_id", request.args.get("sucursal", "TODAS"))
    anio = request.args.get("anio", type=int)
    mes  = request.args.get("mes",  type=int)
    if not anio or not mes:
        return jsonify({"error": "anio y mes requeridos"}), 400
    return _json_call(lambda: {
        "filas": op_repo.get_detalle_mensual(empresa_id, sucursal_id, anio, mes)
    })
