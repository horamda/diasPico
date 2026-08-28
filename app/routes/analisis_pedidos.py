from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from app.routes.portal import login_required
from app.services import analisis_pedidos_svc as svc


bp = Blueprint("analisis_pedidos", __name__, url_prefix="/api/analisis-pedidos")


def _leer_params() -> tuple[float, float, bool, str | None]:
    dias_min = request.form.get("dias_min_retail", type=float)
    umbral = request.form.get("umbral_frescura_dias", type=float)
    usar_frescura = request.form.get("usar_frescura", "true").lower() not in ("false", "0", "no")
    sucursal_id = request.form.get("sucursal_id") or None
    return (
        svc.DIAS_MIN_RETAIL_DEFAULT if dias_min is None else dias_min,
        svc.UMBRAL_FRESCURA_DIAS_DEFAULT if umbral is None else umbral,
        usar_frescura,
        sucursal_id,
    )


@bp.post("/analizar")
@login_required
def analizar():
    pedido = request.files.get("pedido")
    punto_pedido = request.files.get("punto_pedido")
    if pedido is None or punto_pedido is None:
        return jsonify({
            "ok": False,
            "error": "Se requieren ambos archivos: 'pedido' (del supermercado) y 'punto_pedido'.",
        }), 400

    dias_min, umbral, usar_frescura, sucursal_id = _leer_params()
    try:
        data = svc.analizar(
            pedido.read(),
            punto_pedido.read(),
            dias_min_retail=dias_min,
            umbral_frescura_dias=umbral,
            usar_frescura=usar_frescura,
            sucursal_id=sucursal_id,
        )
        return jsonify(data)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        return jsonify({"ok": False, "error": f"No se pudo analizar: {exc}"}), 500


@bp.post("/exportar")
@login_required
def exportar():
    pedido = request.files.get("pedido")
    punto_pedido = request.files.get("punto_pedido")
    if pedido is None or punto_pedido is None:
        return jsonify({"ok": False, "error": "Se requieren ambos archivos para exportar."}), 400

    dias_min, umbral, usar_frescura, sucursal_id = _leer_params()
    try:
        data = svc.analizar(
            pedido.read(),
            punto_pedido.read(),
            dias_min_retail=dias_min,
            umbral_frescura_dias=umbral,
            usar_frescura=usar_frescura,
            sucursal_id=sucursal_id,
        )
        xlsx = svc.exportar_xlsx(data)
        return Response(
            xlsx,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=analisis_pedido.xlsx"},
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        return jsonify({"ok": False, "error": f"No se pudo exportar: {exc}"}), 500
