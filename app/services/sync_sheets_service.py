"""
Sincronización de Google Sheets → tabla operacion_camiones.

DOTACION_ENTREGA_URL  → primera salida  (nro_salida=1)
DOTACION_RECARGAS_URL → segunda salida  (nro_salida=2)

Cada URL en la config puede ser varias URLs separadas por ';'.
El sucursal_id se infiere del GID de la URL:
  gid=0 | gid=1883083406  → '1'  (Casa Central)
  gid=249846040 | gid=680588527 → '2' (Dolores)
"""

from __future__ import annotations

from flask import current_app

from app.services.sheets_svc import _fetch_rows, _split_sheet_urls, _get
from app.utils.coerce import norm_fecha
from app.repositories import operacion_camiones_repository as repo


_GID_TO_SUCURSAL: dict[str, str] = {
    "0":          "1",   # datos mda (legacy)
    "1241670089": "1",   # datos mda (reparto cc)
    "1883083406": "1",   # recargas mda
    "249846040":  "2",   # datos dol
    "680588527":  "2",   # recargas dol
}


def _sucursal_from_url(url: str) -> str:
    for gid, suc in _GID_TO_SUCURSAL.items():
        if f"gid={gid}" in url:
            return suc
    return "1"


def _parse_rows(
    raw_rows: list[dict],
    sucursal_id: str,
    nro_salida: int,
    empresa_id: str,
) -> list[dict]:
    result = []
    for r in raw_rows:
        fecha_str = norm_fecha(_get(r, "fecha", "Fecha"))
        if not fecha_str:
            continue
        chofer = _get(r, "chofer / responsable billetera", "chofer", "responsable billetera").strip()
        if not chofer:
            continue
        result.append({
            "empresa_id":  empresa_id,
            "sucursal_id": sucursal_id,
            "fecha":       fecha_str,
            "nro_salida":  nro_salida,
            "chofer":      chofer,
            "ayudante_1":  _get(r, "ayudante1", "ayudante 1").strip() or None,
            "ayudante_2":  _get(r, "ayudante2", "ayudante 2").strip() or None,
        })
    return result


def sync_operacion_camiones(empresa_id: str = "1") -> dict:
    """
    Fetches all 4 sheet tabs and upserts into operacion_camiones.
    Returns {'insertados': N, 'errores': [...], 'detalle': [...]}
    """
    entrega_urls  = _split_sheet_urls(current_app.config.get("DOTACION_ENTREGA_URL",  ""))
    recargas_urls = _split_sheet_urls(current_app.config.get("DOTACION_RECARGAS_URL", ""))

    total_insertados = 0
    errores: list[str] = []
    detalle: list[dict] = []

    tab_configs = (
        [(u, 1) for u in entrega_urls] +
        [(u, 2) for u in recargas_urls]
    )

    for url, nro_salida in tab_configs:
        sucursal_id = _sucursal_from_url(url)
        gid = url.split("gid=")[-1] if "gid=" in url else "?"
        tag = f"gid={gid} sucursal={sucursal_id} nro_salida={nro_salida}"
        try:
            raw = _fetch_rows(url)
            cols = list(raw[0].keys()) if raw else []
            rows = _parse_rows(raw, sucursal_id, nro_salida, empresa_id)
            n = repo.replace_rows(rows, sucursal_id, nro_salida)
            total_insertados += n
            detalle.append({
                "url_tag":       tag,
                "filas_csv":     len(raw),
                "filas_parseadas": len(rows),
                "upsertados":    n,
                "columnas_csv":  cols,
            })
        except Exception as exc:
            errores.append(f"{tag}: {exc}")
            detalle.append({"url_tag": tag, "error": str(exc)})

    return {
        "insertados": total_insertados,
        "errores":    errores,
        "detalle":    detalle,
    }
