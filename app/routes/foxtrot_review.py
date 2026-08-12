from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.routes.portal import login_required
from app.services import foxtrot_review_svc as svc


bp = Blueprint("foxtrot_review", __name__, url_prefix="/api/foxtrot")


@bp.get("/datasets")
@login_required
def datasets():
    try:
        return jsonify(svc.list_datasets())
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/<dataset>/rows")
@login_required
def rows(dataset: str):
    try:
        return jsonify(svc.list_rows(
            dataset,
            desde=request.args.get("desde") or None,
            hasta=request.args.get("hasta") or None,
            sucursal=request.args.get("sucursal") or None,
            limit=request.args.get("limit", type=int) or 200,
        ))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.patch("/<dataset>/rows/<int:row_id>")
@login_required
def update_row(dataset: str, row_id: int):
    try:
        return jsonify(svc.update_row(dataset, row_id, (request.get_json(force=True) or {}).get("values") or {}))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
