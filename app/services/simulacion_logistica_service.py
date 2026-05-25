from __future__ import annotations

import math
import calendar as cal_mod
from datetime import date, timedelta
from decimal import Decimal

from app.repositories import simulacion_logistica_repository as repo
from app.services import planificacion_picos_service as plan_svc

MESES = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
         'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']


# ── Helpers ──────────────────────────────────────────────────────────────────

def _f(value, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _safe_div(numerator, denominator, default: float = 0.0) -> float:
    d = _f(denominator)
    if d == 0:
        return default
    return _f(numerator) / d


def _ceil(value: float) -> int:
    return math.ceil(value)


def _pct_error(real, plan) -> float:
    p = _f(plan)
    if p == 0:
        return 0.0
    return round((_f(real) - p) / p * 100, 2)


def _semaforo(dispersion_pct: float) -> str:
    abs_d = abs(dispersion_pct)
    if abs_d <= 5:
        return "verde"
    if abs_d <= 10:
        return "amarillo"
    return "rojo"


def _validate(data: dict) -> dict:
    anio = int(data.get("anio") or 0)
    mes = int(data.get("mes") or 0)
    if anio < 2000 or anio > 2100:
        raise ValueError("Año inválido")
    if mes < 1 or mes > 12:
        raise ValueError("Mes debe estar entre 1 y 12")

    empresa_id = str(data.get("empresa_id") or "1").strip()
    sucursal_id = str(data.get("sucursal_id") or data.get("sucursal") or "TODAS").strip()
    if not empresa_id:
        raise ValueError("empresa_id requerido")
    if not sucursal_id:
        raise ValueError("sucursal_id requerido")

    crecimiento = float(data.get("crecimiento_esperado") or 0)
    if crecimiento < -50 or crecimiento > 100:
        raise ValueError("Crecimiento esperado debe estar entre -50% y 100%")

    ausentismo = float(data.get("ausentismo_esperado") or 0)
    if ausentismo < 0 or ausentismo >= 100:
        raise ValueError("Ausentismo debe estar entre 0 y 99%")

    camiones_disp = float(data.get("camiones_disponibles") or 0)
    if camiones_disp < 0:
        raise ValueError("Camiones disponibles no puede ser negativo")

    dias_trabajados = int(data.get("dias_trabajados") or 22)
    if dias_trabajados <= 0:
        raise ValueError("Días trabajados debe ser mayor a 0")

    dias_pico_esp = int(data.get("dias_pico_esperados") or 0)
    if dias_pico_esp < 0:
        raise ValueError("Días pico no puede ser negativo")
    if dias_pico_esp > dias_trabajados:
        raise ValueError("Días pico no puede superar días trabajados")

    return {
        "empresa_id": empresa_id,
        "sucursal_id": sucursal_id,
        "anio": anio,
        "mes": mes,
        "crecimiento_esperado": crecimiento,
        "ausentismo_esperado": ausentismo,
        "camiones_disponibles": camiones_disp,
        "dias_trabajados": dias_trabajados,
        "dias_pico_esperados": dias_pico_esp,
    }


# ── Base histórica ────────────────────────────────────────────────────────────

def obtener_base_historica(empresa_id: str, sucursal_id: str, anio: int, mes: int) -> dict:
    """Retorna el mismo mes del año anterior como base. Recalcula si faltan estadísticas."""
    anio_base = anio - 1
    base = repo.get_base_mensual(empresa_id, sucursal_id, anio_base, mes)
    if not base:
        # Intentar recalcular desde ventas_detalle (reutilizar lógica existente)
        try:
            plan_svc.recalcular_estadisticas_diarias(empresa_id, sucursal_id, anio_base, mes)
            base = repo.get_base_mensual(empresa_id, sucursal_id, anio_base, mes)
        except Exception:
            pass
    if not base or _f(base.get("hl")) == 0:
        raise ValueError(
            f"No se encontró información histórica para {sucursal_id} en "
            f"{mes:02d}/{anio_base}. Cargá los datos de ese período primero."
        )
    return base


# ── Productividades ───────────────────────────────────────────────────────────

def calcular_productividades(base: dict) -> dict:
    hl = _f(base.get("hl"))
    bultos = _f(base.get("bultos"))
    pallets = _f(base.get("pallets"))
    camiones = _f(base.get("camiones_promedio"))
    personas = _f(base.get("empleados_normales"))
    salidas = _f(base.get("salidas"))
    pdv = _f(base.get("pdv_unicos"))

    return {
        "hl_por_camion":     _safe_div(hl, camiones),
        "bultos_por_camion": _safe_div(bultos, camiones),
        "pallets_por_camion":_safe_div(pallets, camiones),
        "hl_por_persona":    _safe_div(hl, personas),
        "bultos_por_persona":_safe_div(bultos, personas),
        "pdv_por_salida":    _safe_div(pdv, salidas),
        "hl_por_salida":     _safe_div(hl, salidas),
        "bultos_por_salida": _safe_div(bultos, salidas),
        "dropsize":          _safe_div(bultos, pdv),
    }


# ── Plan de volumen ────────────────────────────────────────────────────────────

def calcular_plan(base: dict, params: dict) -> dict:
    factor = 1 + _f(params.get("crecimiento_esperado")) / 100
    return {
        "hl_plan":     round(_f(base.get("hl")) * factor, 2),
        "bultos_plan": round(_f(base.get("bultos")) * factor, 2),
        "pallets_plan":round(_f(base.get("pallets")) * factor, 2),
        "up_plan":     round(_f(base.get("pdv_unicos")) * factor, 2),  # unidades tratadas ~ PDV
        "pdv_plan":    round(_f(base.get("pdv_unicos")) * factor, 2),
    }


# ── Recursos necesarios ────────────────────────────────────────────────────────

def calcular_recursos(base: dict, plan: dict, prod: dict, params: dict) -> dict:
    hl_plan     = _f(plan.get("hl_plan"))
    bultos_plan = _f(plan.get("bultos_plan"))
    pallets_plan= _f(plan.get("pallets_plan"))
    pdv_plan    = _f(plan.get("pdv_plan"))
    ausentismo  = _f(params.get("ausentismo_esperado"))
    dias_trab   = int(params.get("dias_trabajados") or 22)
    dias_pico_e = int(params.get("dias_pico_esperados") or 0)
    cam_disp    = _f(params.get("camiones_disponibles"))

    # Camiones: mayor entre HL y pallets
    cam_por_hl     = _safe_div(hl_plan,      prod["hl_por_camion"])
    cam_por_pallets= _safe_div(pallets_plan, prod["pallets_por_camion"])
    camiones_nec   = _ceil(max(cam_por_hl, cam_por_pallets, 0))

    # Personas: mayor entre HL y bultos, ajustado por ausentismo
    per_por_hl     = _safe_div(hl_plan,     prod["hl_por_persona"])
    per_por_bultos = _safe_div(bultos_plan, prod["bultos_por_persona"])
    personas_raw   = max(per_por_hl, per_por_bultos, 0)
    if ausentismo > 0:
        personas_nec = _ceil(personas_raw / (1 - ausentismo / 100))
    else:
        personas_nec = _ceil(personas_raw)

    # Salidas: mayor entre PDV y HL
    sal_por_pdv = _safe_div(pdv_plan, prod["pdv_por_salida"])
    sal_por_hl  = _safe_div(hl_plan,  prod["hl_por_salida"])
    salidas_nec = _ceil(max(sal_por_pdv, sal_por_hl, 0))

    # Factor pico: ratio histórico días_pico / días_con_datos, mínimo 10%
    dias_base = int(_f(base.get("dias_con_datos")) or dias_trab)
    dias_pico_base = int(_f(base.get("dias_pico")) or 0)
    factor_pico = _safe_div(dias_pico_base, dias_base, default=0.1)
    if dias_pico_e > 0 and dias_trab > 0:
        factor_pico = max(factor_pico, dias_pico_e / dias_trab)
    factor_pico = max(factor_pico, 0.1)

    # Recursos en días pico
    cam_pico = _ceil(camiones_nec * (1 + factor_pico))
    per_pico = _ceil(personas_nec * (1 + factor_pico))
    sal_pico = _ceil(salidas_nec  * (1 + factor_pico))

    # Camiones adicionales requeridos (para días pico vs disponibles)
    cam_adicionales = max(cam_pico - cam_disp, 0) if cam_disp > 0 else 0

    return {
        "camiones_necesarios":  camiones_nec,
        "personas_necesarias":  personas_nec,
        "salidas_necesarias":   salidas_nec,
        "camiones_dia_pico":    cam_pico,
        "personas_dia_pico":    per_pico,
        "salidas_dia_pico":     sal_pico,
        "camiones_adicionales": cam_adicionales,
        "factor_pico":          round(factor_pico, 4),
        # Productividades calculadas (para mostrar en UI)
        "cam_por_hl":           round(cam_por_hl, 2),
        "cam_por_pallets":      round(cam_por_pallets, 2),
        "per_por_hl":           round(per_por_hl, 2),
        "per_por_bultos":       round(per_por_bultos, 2),
    }


# ── Score de riesgo ─────────────────────────────────────────────────────────

def calcular_riesgo(base: dict, plan: dict, recursos: dict, params: dict) -> dict:
    score = 0
    detalle: list[str] = []

    cam_pico = recursos.get("camiones_dia_pico", 0)
    cam_disp = _f(params.get("camiones_disponibles"))
    if cam_disp > 0 and cam_pico > cam_disp:
        score += 3
        detalle.append(f"Flota insuficiente en días pico ({cam_pico} necesarios vs {int(cam_disp)} disponibles)")

    ausentismo = _f(params.get("ausentismo_esperado"))
    if ausentismo >= 8:
        score += 2
        detalle.append(f"Ausentismo esperado alto ({ausentismo:.1f}%)")

    crecimiento = _f(params.get("crecimiento_esperado"))
    if crecimiento >= 15:
        score += 2
        detalle.append(f"Crecimiento elevado respecto al año anterior ({crecimiento:.1f}%)")

    rechazos = _f(base.get("rechazos_pct"))
    if rechazos >= 3:
        score += 1
        detalle.append(f"Nivel de rechazos histórico alto ({rechazos:.1f}%)")

    dropsize_base = _safe_div(
        _f(base.get("bultos")), _f(base.get("pdv_unicos"))
    )
    if dropsize_base > 0 and dropsize_base < 20:
        score += 1
        detalle.append(f"Dropsize bajo ({dropsize_base:.1f} bultos/PDV) — posible exceso de salidas")

    dias_pico_e = int(params.get("dias_pico_esperados") or 0)
    if dias_pico_e >= 8:
        score += 1
        detalle.append(f"Cantidad de días pico esperados alta ({dias_pico_e} días)")

    if score <= 2:
        nivel = "BAJO"
    elif score <= 4:
        nivel = "MEDIO"
    elif score <= 6:
        nivel = "ALTO"
    else:
        nivel = "CRITICO"

    return {"score": score, "nivel": nivel, "detalle": detalle}


# ── Recomendaciones ──────────────────────────────────────────────────────────

def generar_recomendaciones(
    base: dict, plan: dict, recursos: dict, riesgo: dict, params: dict
) -> list[str]:
    recom: list[str] = []
    cam_adicionales = recursos.get("camiones_adicionales", 0)
    if cam_adicionales > 0:
        recom.append(
            f"Prever {int(cam_adicionales)} camión(es) adicional(es) para días pico "
            f"(flota requerida: {recursos['camiones_dia_pico']})."
        )

    ausentismo = _f(params.get("ausentismo_esperado"))
    if ausentismo >= 5:
        extra = recursos["personas_necesarias"] - _ceil(
            recursos["personas_necesarias"] * (1 - ausentismo / 100)
        )
        recom.append(
            f"El ausentismo esperado ({ausentismo:.0f}%) impacta la dotación. "
            f"Planificar al menos {extra} persona(s) de refuerzo."
        )

    rechazos = _f(base.get("rechazos_pct"))
    if rechazos >= 3:
        recom.append(
            "La sucursal presenta nivel histórico alto de rechazos. "
            "Revisar causas principales antes del inicio del mes."
        )

    dropsize = _safe_div(_f(base.get("bultos")), _f(base.get("pdv_unicos")))
    if 0 < dropsize < 20:
        recom.append(
            "El dropsize bajo puede aumentar la cantidad de salidas necesarias. "
            "Revisar ruteo y consolidación de pedidos."
        )

    if int(params.get("dias_pico_esperados") or 0) >= 5:
        recom.append("Planificar prearmado de picking para días pico.")

    recom.append(
        "Coordinar disponibilidad de flota con mantenimiento antes del inicio del período."
    )

    if _f(params.get("crecimiento_esperado")) >= 10:
        recom.append(
            "Crecimiento elevado respecto al año anterior. "
            "Validar stock de insumos y capacidad de almacén."
        )

    return recom


# ── Aplicar aprendizaje histórico ────────────────────────────────────────────


# ── Avance mensual ────────────────────────────────────────────────────────────

def calcular_avance(simulacion: dict, real: dict) -> dict:
    dias_trab = int(simulacion.get("dias_trabajados") or 22)
    dias_transc = int(real.get("dias_transcurridos") or 0)
    if dias_transc <= 0 or dias_trab <= 0:
        raise ValueError("dias_transcurridos debe ser mayor a 0")
    if dias_transc > dias_trab:
        raise ValueError("dias_transcurridos no puede superar dias_trabajados")

    avance = round(dias_transc / dias_trab, 4)

    def _disp(key_plan, key_real):
        plan_a_fecha = _f(simulacion.get(key_plan)) * avance
        real_val = _f(real.get(key_real))
        if plan_a_fecha == 0:
            return None
        d = round((real_val - plan_a_fecha) / plan_a_fecha * 100, 2)
        return d

    metricas = [
        ("hl_plan",              "hl_real",       "dispersion_hl_pct"),
        ("bultos_plan",          "bultos_real",   "dispersion_bultos_pct"),
        ("pallets_plan",         "pallets_real",  "dispersion_pallets_pct"),
        ("pdv_plan",             "pdv_real",      "dispersion_pdv_pct"),
        ("salidas_necesarias",   "salidas_real",  "dispersion_salidas_pct"),
        ("camiones_necesarios",  "camiones_real", "dispersion_camiones_pct"),
        ("personas_necesarias",  "personas_real", "dispersion_personas_pct"),
    ]

    result: dict = {
        "simulacion_id": simulacion.get("id"),
        "dias_transcurridos": dias_transc,
        "avance_esperado": avance,
    }
    for key_plan, key_real, key_disp in metricas:
        result[key_real]  = _f(real.get(key_real))
        result[key_disp]  = _disp(key_plan, key_real)

    result["rechazos_real"] = _f(real.get("rechazos_real"))
    result["dispersion_rechazos_pct"] = None

    result["semaforos"] = {
        k: _semaforo(_f(result.get(k)))
        for k in [m[2] for m in metricas]
        if result.get(k) is not None
    }
    return result


# ── Cierre mensual ────────────────────────────────────────────────────────────

def cerrar_simulacion(simulacion: dict, real_final: dict) -> dict:
    sim_id = simulacion.get("id")
    if not sim_id:
        raise ValueError("simulacion_id requerido")

    def _err(key_plan, key_real):
        return _pct_error(real_final.get(key_real), simulacion.get(key_plan))

    cierre = {
        "simulacion_id":    sim_id,
        "hl_real":          _f(real_final.get("hl_real")),
        "bultos_real":      _f(real_final.get("bultos_real")),
        "pallets_real":     _f(real_final.get("pallets_real")),
        "up_real":          _f(real_final.get("up_real")),
        "pdv_real":         _f(real_final.get("pdv_real")),
        "salidas_real":     _f(real_final.get("salidas_real")),
        "camiones_real":    _f(real_final.get("camiones_real")),
        "personas_real":    _f(real_final.get("personas_real")),
        "rechazos_real":    _f(real_final.get("rechazos_real")),
        "dias_pico_real":   int(real_final.get("dias_pico_real") or 0),
        "ausentismo_real":  _f(real_final.get("ausentismo_real")),
        "dropsize_real":    _safe_div(real_final.get("bultos_real"), real_final.get("pdv_real")),
        "error_hl_pct":     _err("hl_plan",            "hl_real"),
        "error_bultos_pct": _err("bultos_plan",         "bultos_real"),
        "error_pallets_pct":_err("pallets_plan",        "pallets_real"),
        "error_pdv_pct":    _err("pdv_plan",            "pdv_real"),
        "error_salidas_pct":_err("salidas_necesarias",  "salidas_real"),
        "error_camiones_pct":_err("camiones_necesarios","camiones_real"),
        "error_personas_pct":_err("personas_necesarias","personas_real"),
        "error_rechazos_pct":_err("rechazos_base",      "rechazos_real"),
        "conclusiones":     real_final.get("conclusiones", ""),
    }

    saved_cierre = repo.save_cierre(cierre)
    repo.update_estado(sim_id, "CERRADA")

    # Guardar aprendizaje
    def _factor(key_real, key_plan):
        p = _f(simulacion.get(key_plan))
        r = _f(real_final.get(key_real))
        if p == 0:
            return 1.0
        return round(r / p, 4)

    aprendizaje = {
        "empresa_id":           simulacion["empresa_id"],
        "sucursal_id":          simulacion["sucursal_id"],
        "mes":                  simulacion["mes"],
        "anio":                 simulacion["anio"],
        "simulacion_id":        sim_id,
        "error_hl_pct":         cierre["error_hl_pct"],
        "error_camiones_pct":   cierre["error_camiones_pct"],
        "error_personas_pct":   cierre["error_personas_pct"],
        "error_salidas_pct":    cierre["error_salidas_pct"],
        "factor_ajuste_hl":     _factor("hl_real",       "hl_plan"),
        "factor_ajuste_camiones":_factor("camiones_real", "camiones_necesarios"),
        "factor_ajuste_personas":_factor("personas_real", "personas_necesarias"),
        "factor_ajuste_salidas": _factor("salidas_real",  "salidas_necesarias"),
    }
    repo.save_aprendizaje(aprendizaje)

    return {"cierre": saved_cierre, "aprendizaje": aprendizaje}


# ── Sugerencias automáticas desde el sistema ─────────────────────────────────

def sugerir_parametros(empresa_id: str, sucursal_id: str, anio: int, mes: int) -> dict:
    sugerencias: dict = {}
    fuentes: dict     = {}

    # 1. Días hábiles del mes objetivo (lunes-viernes menos feriados cargados)
    try:
        from app.repositories.planificacion_picos_repository import obtener_feriados
        ini = date(anio, mes, 1)
        fin = date(anio, mes, cal_mod.monthrange(anio, mes)[1])
        feriados_set = obtener_feriados(ini, fin)
        dias_hab = sum(
            1 for n in range((fin - ini).days + 1)
            if (ini + timedelta(n)).weekday() < 5
            and (ini + timedelta(n)) not in feriados_set
        )
        sugerencias['dias_trabajados'] = dias_hab
        fuentes['dias_trabajados'] = (
            f'Días hábiles de {MESES[mes-1]} {anio} '
            f'({fin.day} días del mes, descontando fines de semana y feriados cargados)'
        )
    except Exception:
        pass

    # 2. Días pico esperados (promedio histórico del mismo mes, últimos 3 años)
    pico_vals = []
    for y in range(anio - 1, anio - 4, -1):
        try:
            b = repo.get_base_mensual(empresa_id, sucursal_id, y, mes)
            if b and _f(b.get('dias_pico')) > 0:
                pico_vals.append(int(_f(b.get('dias_pico'))))
        except Exception:
            pass
    if pico_vals:
        sugerencias['dias_pico_esperados'] = round(sum(pico_vals) / len(pico_vals))
        fuentes['dias_pico_esperados'] = (
            f'Promedio histórico de {MESES[mes-1]} '
            f'({len(pico_vals)} año{"s" if len(pico_vals) > 1 else ""}: '
            f'{", ".join(str(v) for v in pico_vals)} días pico)'
        )

    # 3. Crecimiento YoY: mismo mes (anio-1) vs (anio-2)
    try:
        base_n1 = repo.get_base_mensual(empresa_id, sucursal_id, anio - 1, mes)
        base_n2 = repo.get_base_mensual(empresa_id, sucursal_id, anio - 2, mes)
        hl_n1 = _f(base_n1.get('hl')) if base_n1 else 0
        hl_n2 = _f(base_n2.get('hl')) if base_n2 else 0
        if hl_n1 > 0 and hl_n2 > 0:
            crec = (hl_n1 / hl_n2 - 1) * 100
            sugerencias['crecimiento_esperado'] = round(crec, 1)
            fuentes['crecimiento_esperado'] = (
                f'YoY HL: {MESES[mes-1]} {anio-1} ({hl_n1:,.0f}) '
                f'vs {MESES[mes-1]} {anio-2} ({hl_n2:,.0f})'
            )
    except Exception:
        pass

    # 4. Camiones disponibles (flota activa en ese mes)
    try:
        from app.repositories import flota_repository
        vehiculos = flota_repository.listar_vehiculos(empresa_id, sucursal_id, anio, mes)
        cam_activos = sum(1 for v in vehiculos if v.get('activo_mes'))
        if cam_activos > 0:
            sugerencias['camiones_disponibles'] = cam_activos
            fuentes['camiones_disponibles'] = (
                f'{cam_activos} vehículo{"s" if cam_activos > 1 else ""} activo{"s" if cam_activos > 1 else ""} '
                f'en {MESES[mes-1]} {anio} (según flota registrada)'
            )
    except Exception:
        pass

    # 5. Datos reales del año anterior del mismo mes (planilla operativa sincronizada)
    try:
        from app.repositories import operacion_camiones_repository as op_repo
        stats = op_repo.get_estadisticas_periodo(empresa_id, sucursal_id, anio - 1, mes)
        if stats.get('dias_con_datos', 0) > 0:
            cam_prom = stats.get('camiones_dia_promedio', 0)
            if cam_prom > 0 and 'camiones_disponibles' not in sugerencias:
                sugerencias['camiones_disponibles'] = round(cam_prom)
                fuentes['camiones_disponibles'] = (
                    f'Promedio real {MESES[mes-1]} {anio-1}: '
                    f'{cam_prom:.1f} camiones/día '
                    f'({stats["dias_con_datos"]} días con datos de planilla)'
                )
            sugerencias['camiones_reales_anio_anterior'] = cam_prom
            sugerencias['personas_reales_anio_anterior'] = stats.get('personas_unicas', 0)
            fuentes['camiones_reales_anio_anterior'] = (
                f'Planilla operativa {MESES[mes-1]} {anio-1} '
                f'({stats["salidas_total"]} salidas, {stats["personas_unicas"]} personas únicas)'
            )
    except Exception:
        pass

    return {'sugerencias': sugerencias, 'fuentes': fuentes}


# ── Función principal de simulación ─────────────────────────────────────────

def simular(data: dict) -> dict:
    params = _validate(data)
    empresa_id  = params["empresa_id"]
    sucursal_id = params["sucursal_id"]
    anio = params["anio"]
    mes  = params["mes"]

    base = obtener_base_historica(empresa_id, sucursal_id, anio, mes)

    prod     = calcular_productividades(base)
    plan     = calcular_plan(base, params)
    recursos = calcular_recursos(base, plan, prod, params)

    # Aplicar aprendizaje histórico si existe
    apr = repo.get_aprendizaje(empresa_id, sucursal_id, mes)
    if apr and _f(apr.get("registros")) > 0:
        def _aj(v, fk):
            f = _f(apr.get(fk), 1.0)
            return _ceil(v * f) if f not in (0.0, 1.0) else v

        recursos["camiones_necesarios_orig"] = recursos["camiones_necesarios"]
        recursos["personas_necesarias_orig"] = recursos["personas_necesarias"]
        recursos["salidas_necesarias_orig"]  = recursos["salidas_necesarias"]

        recursos["camiones_necesarios"] = _aj(recursos["camiones_necesarios"], "factor_ajuste_camiones")
        recursos["personas_necesarias"] = _aj(recursos["personas_necesarias"], "factor_ajuste_personas")
        recursos["salidas_necesarias"]  = _aj(recursos["salidas_necesarias"],  "factor_ajuste_salidas")

        fp = recursos["factor_pico"]
        recursos["camiones_dia_pico"] = _ceil(recursos["camiones_necesarios"] * (1 + fp))
        recursos["personas_dia_pico"] = _ceil(recursos["personas_necesarias"] * (1 + fp))
        recursos["salidas_dia_pico"]  = _ceil(recursos["salidas_necesarias"]  * (1 + fp))

        cam_disp = _f(params.get("camiones_disponibles"))
        recursos["camiones_adicionales"] = max(recursos["camiones_dia_pico"] - cam_disp, 0) if cam_disp > 0 else 0
        recursos["aprendizaje_aplicado"]  = True
        recursos["aprendizaje_registros"] = int(_f(apr.get("registros")))
        recursos["factor_ajuste_camiones"]= round(_f(apr.get("factor_ajuste_camiones"), 1.0), 4)
        recursos["factor_ajuste_personas"]= round(_f(apr.get("factor_ajuste_personas"), 1.0), 4)
        recursos["factor_ajuste_salidas"] = round(_f(apr.get("factor_ajuste_salidas"),  1.0), 4)

    riesgo  = calcular_riesgo(base, plan, recursos, params)
    recom   = generar_recomendaciones(base, plan, recursos, riesgo, params)

    dropsize_base = _safe_div(_f(base.get("bultos")), _f(base.get("pdv_unicos")))

    return {
        "params": params,
        "base": {
            "anio":            anio - 1,
            "mes":             mes,
            "hl":              round(_f(base.get("hl")), 2),
            "bultos":          round(_f(base.get("bultos")), 2),
            "pallets":         round(_f(base.get("pallets")), 2),
            "pdv_unicos":      round(_f(base.get("pdv_unicos")), 2),
            "salidas":         round(_f(base.get("salidas")), 2),
            "camiones":        round(_f(base.get("camiones_promedio")), 2),
            "personas":        round(_f(base.get("empleados_normales")), 2),
            "rechazos_pct":    round(_f(base.get("rechazos_pct")), 2),
            "dias_pico":       int(_f(base.get("dias_pico"))),
            "dias_trabajados": int(_f(base.get("dias_con_datos"))),
            "dropsize":        round(dropsize_base, 2),
        },
        "productividades": {
            k: round(v, 4) for k, v in prod.items()
        },
        "plan": {
            **plan,
            "salidas_necesarias":  recursos["salidas_necesarias"],
            "camiones_necesarios": recursos["camiones_necesarios"],
            "personas_necesarias": recursos["personas_necesarias"],
            "camiones_dia_pico":   recursos["camiones_dia_pico"],
            "personas_dia_pico":   recursos["personas_dia_pico"],
            "salidas_dia_pico":    recursos["salidas_dia_pico"],
            "camiones_adicionales":recursos["camiones_adicionales"],
        },
        "riesgo": {
            "score":  riesgo["score"],
            "nivel":  riesgo["nivel"],
            "detalle":riesgo["detalle"],
        },
        "recomendaciones": recom,
        "aprendizaje": {
            "aplicado":   recursos.get("aprendizaje_aplicado", False),
            "registros":  recursos.get("aprendizaje_registros", 0),
            "factores": {
                "camiones": recursos.get("factor_ajuste_camiones"),
                "personas": recursos.get("factor_ajuste_personas"),
                "salidas":  recursos.get("factor_ajuste_salidas"),
            },
            "originales": {
                "camiones": recursos.get("camiones_necesarios_orig"),
                "personas": recursos.get("personas_necesarias_orig"),
                "salidas":  recursos.get("salidas_necesarias_orig"),
            },
        },
    }


def guardar(data: dict) -> dict:
    resultado = simular(data)
    plan   = resultado["plan"]
    base_d = resultado["base"]
    params = resultado["params"]
    riesgo = resultado["riesgo"]
    recom  = resultado["recomendaciones"]

    row = {
        "empresa_id":          params["empresa_id"],
        "sucursal_id":         params["sucursal_id"],
        "anio":                params["anio"],
        "mes":                 params["mes"],
        "anio_base":           base_d["anio"],
        "mes_base":            base_d["mes"],
        "crecimiento_esperado":params["crecimiento_esperado"],
        "ausentismo_esperado": params["ausentismo_esperado"],
        "camiones_disponibles":params["camiones_disponibles"],
        "dias_trabajados":     params["dias_trabajados"],
        "dias_pico_esperados": params["dias_pico_esperados"],
        "hl_base":             base_d["hl"],
        "bultos_base":         base_d["bultos"],
        "pallets_base":        base_d["pallets"],
        "up_base":             base_d["pdv_unicos"],
        "pdv_base":            base_d["pdv_unicos"],
        "salidas_base":        base_d["salidas"],
        "camiones_base":       base_d["camiones"],
        "personas_base":       base_d["personas"],
        "rechazos_base":       base_d["rechazos_pct"],
        "dropsize_base":       base_d["dropsize"],
        "dias_trabajados_base":base_d["dias_trabajados"],
        "dias_pico_base":      base_d["dias_pico"],
        "hl_plan":             plan["hl_plan"],
        "bultos_plan":         plan["bultos_plan"],
        "pallets_plan":        plan["pallets_plan"],
        "up_plan":             plan["up_plan"],
        "pdv_plan":            plan["pdv_plan"],
        "salidas_necesarias":  plan["salidas_necesarias"],
        "camiones_necesarios": plan["camiones_necesarios"],
        "personas_necesarias": plan["personas_necesarias"],
        "camiones_dia_pico":   plan["camiones_dia_pico"],
        "personas_dia_pico":   plan["personas_dia_pico"],
        "salidas_dia_pico":    plan["salidas_dia_pico"],
        "camiones_adicionales":plan["camiones_adicionales"],
        "riesgo_score":        riesgo["score"],
        "riesgo_nivel":        riesgo["nivel"],
        "recomendaciones_json":recom,
        "estado":              "ABIERTA",
        "observaciones":       data.get("observaciones"),
    }
    saved = repo.save_simulacion(row)
    resultado["id"] = saved["id"]
    return resultado


def registrar_avance(simulacion_id: int, real: dict) -> dict:
    sim = repo.get_simulacion(simulacion_id)
    if not sim:
        raise ValueError("Simulación no encontrada")
    calculo = calcular_avance(sim, real)
    saved = repo.save_avance(calculo)
    repo.update_estado(simulacion_id, "EN_AVANCE")
    return {"avance": saved, "semaforos": calculo.get("semaforos", {})}


def cerrar(simulacion_id: int, real_final: dict) -> dict:
    sim = repo.get_simulacion(simulacion_id)
    if not sim:
        raise ValueError("Simulación no encontrada")
    return cerrar_simulacion(sim, real_final)


def detalle(simulacion_id: int) -> dict:
    sim = repo.get_simulacion(simulacion_id)
    if not sim:
        raise ValueError("Simulación no encontrada")
    avances = repo.get_avances(simulacion_id)
    cierre  = repo.get_cierre(simulacion_id)
    return {"simulacion": sim, "avances": avances, "cierre": cierre}
