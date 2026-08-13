"""Dashboard KPIs for the portal home page."""
from __future__ import annotations

import calendar
from datetime import date

from app.database import pg_cursor


SUC_CASA_CENTRAL = "1"
SUC_DOLORES = "2"


def _day_from_row(row: dict) -> int:
    try:
        return int(str(row.get("fecha") or "0000-00-00")[-2:])
    except Exception:
        return 0


def get_dashboard_kpis(empresa_id: str, sucursal_id: str) -> dict:
    from app.services import pico_svc

    hoy = date.today()
    anio = hoy.year
    mes = hoy.month
    mes_str = hoy.strftime("%Y-%m")
    prev_anio_mes_str = f"{anio - 1}-{mes:02d}"
    corte_dia_prev = min(hoy.day, calendar.monthrange(anio - 1, mes)[1])

    def _kpis(suc: str, ym: str) -> dict:
        try:
            return pico_svc.get_kpis(suc, ym)
        except Exception:
            return {}

    def _bultos_salidas_por_sucursal() -> list[dict]:
        if sucursal_id != "TODAS":
            nombre = "Casa Central" if sucursal_id == SUC_CASA_CENTRAL else "Dolores"
            return [{
                "sucursal": sucursal_id,
                "nombre": nombre,
                "bultos": round(float(kpis.get("bultos") or 0), 0),
                "salidas": int(kpis.get("camiones") or 0),
            }]

        detalle = []
        for suc, nombre in ((SUC_CASA_CENTRAL, "Casa Central"), (SUC_DOLORES, "Dolores")):
            row = _kpis(suc, mes_str)
            detalle.append({
                "sucursal": suc,
                "nombre": nombre,
                "bultos": round(float(row.get("bultos") or 0), 0),
                "salidas": int(row.get("camiones") or 0),
            })
        return detalle

    def _cal(suc: str, ym: str) -> list[dict]:
        try:
            return pico_svc.get_calendario(suc, ym, None, None).get("dias", [])
        except Exception:
            return []

    def _serie_peso_sucursales(year: int) -> list[dict]:
        pico_svc.ensure_ventas_detalle_table()
        ini = date(year, 1, 1)
        fin = date(year, 12, 31)
        with pg_cursor() as cur:
            cur.execute(f"""
                SELECT
                    v.sucursal::text AS sucursal,
                    EXTRACT(MONTH FROM v.fecha)::int AS mes,
                    SUM(COALESCE(v.unidad_medida, 0)) AS hectolitros
                FROM ventas_detalle v
                LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
                WHERE v.fecha BETWEEN %(ini)s AND %(fin)s
                  AND v.sucursal IN (%(casa)s, %(dolores)s)
                  AND {pico_svc.IS_MERCADERIA}
                  AND {pico_svc.V_NOT_REMITO}
                GROUP BY v.sucursal, EXTRACT(MONTH FROM v.fecha)
            """, {"ini": ini, "fin": fin, "casa": SUC_CASA_CENTRAL, "dolores": SUC_DOLORES})
            rows = cur.fetchall()

        by_key = {(str(r["sucursal"]), int(r["mes"])): float(r["hectolitros"] or 0) for r in rows}
        serie = []
        acc_casa = 0.0
        acc_dolores = 0.0
        for month in range(1, 13):
            casa_hl = by_key.get((SUC_CASA_CENTRAL, month), 0.0)
            dolores_hl = by_key.get((SUC_DOLORES, month), 0.0)
            acc_casa += casa_hl
            acc_dolores += dolores_hl
            mensual_total = casa_hl + dolores_hl
            acum_total = acc_casa + acc_dolores
            serie.append({
                "mes": f"{year}-{month:02d}",
                "casa_central_hl": round(casa_hl, 1),
                "dolores_hl": round(dolores_hl, 1),
                "peso_mensual_casa_central": round(casa_hl / mensual_total * 100, 1) if mensual_total else None,
                "peso_mensual_dolores": round(dolores_hl / mensual_total * 100, 1) if mensual_total else None,
                "peso_acum_casa_central": round(acc_casa / acum_total * 100, 1) if acum_total else None,
                "peso_acum_dolores": round(acc_dolores / acum_total * 100, 1) if acum_total else None,
            })
        return serie

    def _ultima_fecha_ventas() -> str | None:
        pico_svc.ensure_ventas_detalle_table()
        where_suc = "" if sucursal_id == "TODAS" else "WHERE sucursal = %(sucursal)s"
        with pg_cursor() as cur:
            cur.execute(
                f"SELECT MAX(fecha)::date AS ultima_fecha FROM ventas_detalle {where_suc}",
                {"sucursal": sucursal_id},
            )
            row = cur.fetchone()
        ultima = row["ultima_fecha"] if row else None
        return ultima.isoformat() if ultima else None

    kpis = _kpis(sucursal_id, mes_str)
    dias_data = _cal(sucursal_id, mes_str)

    dias_pico = 0
    nds = None
    try:
        dias_pico = sum(1 for d in dias_data if d.get("es_pico"))
        p_tot = sum(d.get("pedidos", 0) for d in dias_data)
        p_rec = sum(d.get("rechazo_pedidos", 0) for d in dias_data)
        nds = round((p_tot - p_rec) / p_tot * 100, 1) if p_tot else 100.0
    except Exception:
        pass

    n_periodos = 0
    try:
        periodos = pico_svc.get_periodos_criticos(empresa_id, sucursal_id, anio)
        n_periodos = len(periodos)
    except Exception:
        pass

    pct_aus = None
    try:
        aus_list = pico_svc.get_ausentismo_mensual(empresa_id, "TODAS", anio)
        row = next((r for r in aus_list if r["mes"] == mes), {})
        pct_aus = row.get("pct_ausentismo")
    except Exception:
        pass

    hl = float(kpis.get("hectolitros") or 0)
    hl_mtd = sum(float(d.get("hectolitros") or 0) for d in dias_data if _day_from_row(d) <= hoy.day)
    prev_dias = _cal(sucursal_id, prev_anio_mes_str)
    hl_prev_mtd = sum(float(d.get("hectolitros") or 0) for d in prev_dias if _day_from_row(d) <= corte_dia_prev)
    delta_hl = round((hl_mtd - hl_prev_mtd) / hl_prev_mtd * 100, 1) if hl_prev_mtd else None

    bultos = float(kpis.get("bultos") or 0)
    salidas = int(kpis.get("camiones") or 0)
    bultos_por_sucursal = _bultos_salidas_por_sucursal()

    serie_suc = _serie_peso_sucursales(anio)
    ultima_fecha_datos = _ultima_fecha_ventas()

    return {
        "mes": mes_str,
        "dia_hoy": hoy.isoformat(),
        "ultima_fecha_datos": ultima_fecha_datos,
        "hl": round(hl, 1),
        "hl_mtd": round(hl_mtd, 1),
        "hl_prev_mtd": round(hl_prev_mtd, 1),
        "hl_prev_mes": prev_anio_mes_str,
        "hl_corte_dia": hoy.day,
        "hl_delta_pct": delta_hl,
        "bultos": round(bultos, 0),
        "salidas": salidas,
        "bultos_por_sucursal": bultos_por_sucursal,
        "nds": nds,
        "pct_rec_pdv": float(kpis.get("pct_rechazo_pedidos") or 0),
        "pct_rec_hl": float(kpis.get("pct_rechazo_hl") or 0),
        "dias_pico": dias_pico,
        "periodos_criticos": n_periodos,
        "periodos_objetivo": 3,
        "pct_ausentismo": float(pct_aus) if pct_aus is not None else None,
        "sucursal": sucursal_id,
        "peso_sucursales": serie_suc,
    }
