"""Dashboard KPIs for the portal home page."""
from __future__ import annotations
from datetime import date


def get_dashboard_kpis(empresa_id: str, sucursal_id: str) -> dict:
    from app.services import pico_svc

    hoy  = date.today()
    anio = hoy.year
    mes  = hoy.month

    mes_str = hoy.strftime('%Y-%m')
    if mes > 1:
        prev_mes_str = f"{anio}-{mes-1:02d}"
    else:
        prev_mes_str = f"{anio-1}-12"

    def _kpis(m: str) -> dict:
        try:
            return pico_svc.get_kpis(sucursal_id, m)
        except Exception:
            return {}

    kpis      = _kpis(mes_str)
    prev_kpis = _kpis(prev_mes_str)

    # Días pico + NDS del mes actual
    dias_pico = 0
    nds       = None
    try:
        cal       = pico_svc.get_calendario(sucursal_id, mes_str, None, None)
        dias_pico = cal.get('picos_count', 0)
        dias_data = cal.get('dias', [])
        p_tot = sum(d.get('pedidos', 0) for d in dias_data)
        p_rec = sum(d.get('rechazo_pedidos', 0) for d in dias_data)
        nds   = round((p_tot - p_rec) / p_tot * 100, 1) if p_tot else 100.0
    except Exception:
        pass

    # Periodos críticos definidos este año
    n_periodos = 0
    try:
        periodos   = pico_svc.get_periodos_criticos(empresa_id, sucursal_id, anio)
        n_periodos = len(periodos)
    except Exception:
        pass

    # Ausentismo del mes (siempre busca 'TODAS')
    pct_aus = None
    try:
        aus_list = pico_svc.get_ausentismo_mensual(empresa_id, 'TODAS', anio)
        row = next((r for r in aus_list if r['mes'] == mes), {})
        pct_aus = row.get('pct_ausentismo')
    except Exception:
        pass

    hl      = float(kpis.get('hectolitros') or 0)
    hl_prev = float(prev_kpis.get('hectolitros') or 0)
    delta_hl = round((hl - hl_prev) / hl_prev * 100, 1) if hl_prev else None

    bultos  = float(kpis.get('bultos') or 0)
    salidas = int(kpis.get('camiones') or 0)

    return {
        'mes':              mes_str,
        'dia_hoy':          hoy.isoformat(),
        'hl':               round(hl, 1),
        'hl_delta_pct':     delta_hl,
        'bultos':           round(bultos, 0),
        'salidas':          salidas,
        'nds':              nds,
        'pct_rec_pdv':      float(kpis.get('pct_rechazo_pedidos') or 0),
        'pct_rec_hl':       float(kpis.get('pct_rechazo_hl') or 0),
        'dias_pico':        dias_pico,
        'periodos_criticos':n_periodos,
        'periodos_objetivo':3,
        'pct_ausentismo':   float(pct_aus) if pct_aus is not None else None,
        'sucursal':         sucursal_id,
    }
