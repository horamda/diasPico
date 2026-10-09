"""Dashboard KPIs for the portal home page."""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from app.database import pg_cursor


SUC_CASA_CENTRAL = "1"
SUC_DOLORES = "2"


def _day_from_row(row: dict) -> int:
    try:
        return int(str(row.get("fecha") or "0000-00-00")[-2:])
    except Exception:
        return 0


_METRICAS_COMPARATIVO = (
    ("hl", "HL", "hectolitros"),
    ("bultos", "Bultos", "bultos"),
    ("pedidos", "Pedidos", "pedidos"),
    ("salidas", "Salidas", "camiones_salidos"),
)


def _delta_pct(actual: float | None, previo: float | None) -> float | None:
    if actual is None or not previo:
        return None
    return round((actual - previo) / previo * 100, 1)


def _con_datos(row: dict) -> bool:
    return float(row.get("hectolitros") or 0) > 0 or float(row.get("bultos") or 0) > 0


def _ultimo_dia_con_datos(dias: list[dict], hasta: date) -> date | None:
    fechas = [
        date.fromisoformat(str(d["fecha"])[:10])
        for d in dias
        if d.get("fecha") and _con_datos(d) and str(d["fecha"])[:10] <= hasta.isoformat()
    ]
    return max(fechas) if fechas else None


def _comparar(dias: list[dict], dias_prev: list[dict], dias_prev_dia: list[dict],
              corte: date | None, corte_prev: date | None, dia_prev: date | None) -> dict:
    """Mes a la fecha, último día y mes completo contra el año anterior."""
    def _suma(rows, campo, hasta=None):
        return sum(float(r.get(campo) or 0) for r in rows
                   if hasta is None or str(r.get("fecha") or "")[:10] <= hasta.isoformat())

    def _del_dia(rows, fecha, campo):
        if fecha is None:
            return None
        return sum(float(r.get(campo) or 0) for r in rows if str(r.get("fecha") or "")[:10] == fecha.isoformat())

    metricas = []
    for key, label, campo in _METRICAS_COMPARATIVO:
        mtd = _suma(dias, campo, corte) if corte else None
        mtd_prev = _suma(dias_prev, campo, corte_prev) if corte_prev else None
        mes_prev = _suma(dias_prev, campo)
        dia = _del_dia(dias, corte, campo)
        dia_ant = _del_dia(dias_prev_dia, dia_prev, campo)
        metricas.append({
            "key": key,
            "label": label,
            "mtd": round(mtd, 1) if mtd is not None else None,
            "mtd_prev": round(mtd_prev, 1) if mtd_prev is not None else None,
            "mtd_delta_pct": _delta_pct(mtd, mtd_prev),
            "dia": round(dia, 1) if dia is not None else None,
            "dia_prev": round(dia_ant, 1) if dia_ant is not None else None,
            "dia_delta_pct": _delta_pct(dia, dia_ant),
            "mes_prev_total": round(mes_prev, 1),
            "avance_vs_mes_prev_pct": round(mtd / mes_prev * 100, 1) if mtd is not None and mes_prev else None,
        })
    return {
        "metricas": metricas,
        "dias_reparto": sum(1 for r in dias if _con_datos(r) and corte and str(r["fecha"])[:10] <= corte.isoformat()),
        "dias_reparto_prev": sum(1 for r in dias_prev if _con_datos(r) and corte_prev and str(r["fecha"])[:10] <= corte_prev.isoformat()),
    }


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
    prev_dias = _cal(sucursal_id, prev_anio_mes_str)

    # El corte es el último día con datos cargados, no hoy: si la carga viene
    # atrasada, comparar contra más días del año anterior inventa una caída.
    corte = _ultimo_dia_con_datos(dias_data, hoy)
    corte_prev = None
    dia_prev = None
    if corte:
        corte_prev = date(anio - 1, mes, min(corte.day, calendar.monthrange(anio - 1, mes)[1]))
        # "Mismo día" del año anterior = mismo día de la semana (364 días antes).
        dia_prev = corte - timedelta(days=364)
    corte_dia_prev = corte_prev.day if corte_prev else corte_dia_prev

    def _dias_mes_de(fecha: date | None, suc: str, ya_cargados: list[dict]) -> list[dict]:
        if fecha is None or fecha.strftime("%Y-%m") == prev_anio_mes_str:
            return ya_cargados
        return _cal(suc, fecha.strftime("%Y-%m"))

    comparativo = _comparar(dias_data, prev_dias, _dias_mes_de(dia_prev, sucursal_id, prev_dias), corte, corte_prev, dia_prev)
    def _acumulado(rows: list[dict], hasta: date | None) -> dict[int, float]:
        por_dia: dict[int, float] = {}
        for r in rows:
            if hasta is not None and str(r.get("fecha") or "")[:10] > hasta.isoformat():
                continue
            por_dia[_day_from_row(r)] = por_dia.get(_day_from_row(r), 0.0) + float(r.get("hectolitros") or 0)
        return por_dia

    actual_dia = _acumulado(dias_data, corte) if corte else {}
    previo_dia = _acumulado(prev_dias, None)
    acumulado = []
    acc_actual = acc_previo = 0.0
    for dia in range(1, calendar.monthrange(anio, mes)[1] + 1):
        acc_actual += actual_dia.get(dia, 0.0)
        acc_previo += previo_dia.get(dia, 0.0)
        acumulado.append({
            "dia": dia,
            "actual": round(acc_actual, 1) if corte and dia <= corte.day else None,
            "previo": round(acc_previo, 1) if dia <= calendar.monthrange(anio - 1, mes)[1] else None,
        })
    comparativo.update({
        "acumulado_hl": acumulado,
        "corte": corte.isoformat() if corte else None,
        "corte_prev": corte_prev.isoformat() if corte_prev else None,
        "dia_prev": dia_prev.isoformat() if dia_prev else None,
        "mes_prev": prev_anio_mes_str,
        "por_sucursal": [],
    })
    if sucursal_id == "TODAS" and corte:
        for suc, nombre in ((SUC_CASA_CENTRAL, "Casa Central"), (SUC_DOLORES, "Dolores")):
            suc_prev = _cal(suc, prev_anio_mes_str)
            item = _comparar(_cal(suc, mes_str), suc_prev, _dias_mes_de(dia_prev, suc, suc_prev), corte, corte_prev, dia_prev)
            item.update({"sucursal": suc, "nombre": nombre})
            comparativo["por_sucursal"].append(item)

    hl_cmp = comparativo["metricas"][0]
    hl_mtd = hl_cmp["mtd"] or 0.0
    hl_prev_mtd = hl_cmp["mtd_prev"] or 0.0
    delta_hl = hl_cmp["mtd_delta_pct"]

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
        "hl_corte_dia": corte.day if corte else None,
        "hl_corte_dia_prev": corte_dia_prev,
        "comparativo": comparativo,
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
