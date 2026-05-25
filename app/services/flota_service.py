from __future__ import annotations

from datetime import date

from app.repositories import flota_repository as repo


def _validar_periodo(anio: int | None, mes: int | None) -> tuple[int, int]:
    hoy = date.today()
    anio = int(anio or hoy.year)
    mes = int(mes or hoy.month)
    if anio < 2020 or anio > 2100:
        raise ValueError("Anio fuera de rango.")
    if mes < 1 or mes > 12:
        raise ValueError("Mes fuera de rango.")
    return anio, mes


def _to_float(value) -> float:
    return float(value or 0)


def _build_label_map() -> dict[str, str]:
    try:
        from app.services.sucursales_svc import listar
        return {r["id"]: r["nombre"] for r in listar()}
    except Exception:
        return {}


def _sucursal_label(sucursal_id: str, label_map: dict[str, str] | None = None) -> str:
    if label_map is not None:
        return label_map.get(str(sucursal_id), str(sucursal_id))
    return _build_label_map().get(str(sucursal_id), str(sucursal_id))


def _resumen(rows: list[dict], label_map: dict[str, str]) -> dict:
    activos = [r for r in rows if r.get("activo_mes")]
    inactivos = [r for r in rows if not r.get("activo_mes")]
    por_sucursal: dict[str, dict] = {}
    for r in rows:
        suc = str(r.get("sucursal_id") or "")
        item = por_sucursal.setdefault(suc, {
            "sucursal_id": suc,
            "sucursal": _sucursal_label(suc, label_map),
            "total": 0,
            "activos": 0,
            "inactivos": 0,
            "capacidad_up_activa": 0.0,
            "carga_kg_activa": 0.0,
        })
        item["total"] += 1
        if r.get("activo_mes"):
            item["activos"] += 1
            item["capacidad_up_activa"] += _to_float(r.get("capacidad_up"))
            item["carga_kg_activa"] += _to_float(r.get("carga_maxima_kg"))
        else:
            item["inactivos"] += 1
    return {
        "total": len(rows),
        "activos": len(activos),
        "inactivos": len(inactivos),
        "anulados": sum(1 for r in rows if r.get("anulado")),
        "propios": sum(1 for r in rows if r.get("propio")),
        "capacidad_up_activa": round(sum(_to_float(r.get("capacidad_up")) for r in activos), 2),
        "carga_kg_activa": round(sum(_to_float(r.get("carga_maxima_kg")) for r in activos), 2),
        "por_sucursal": list(por_sucursal.values()),
    }


def listar_vehiculos(
    empresa_id: str = "1",
    sucursal_id: str = "TODAS",
    anio: int | None = None,
    mes: int | None = None,
    incluir_anulados: bool = False,
) -> dict:
    anio, mes = _validar_periodo(anio, mes)
    rows = repo.listar_vehiculos(
        empresa_id=str(empresa_id or "1"),
        sucursal_id=str(sucursal_id or "TODAS"),
        anio=anio,
        mes=mes,
        incluir_anulados=incluir_anulados,
    )
    label_map = _build_label_map()
    for r in rows:
        r["sucursal"] = _sucursal_label(str(r.get("sucursal_id") or ""), label_map)
        r["activo_mes"] = bool(r.get("activo_mes"))
        r["activo_base"] = bool(r.get("activo_base"))
        r["anulado"] = bool(r.get("anulado"))
        r["propio"] = bool(r.get("propio"))
    return {
        "anio": anio,
        "mes": mes,
        "resumen": _resumen(rows, label_map),
        "vehiculos": rows,
    }


def guardar_disponibilidad(data: dict) -> dict:
    vehiculo_id = int(data.get("vehiculo_id") or 0)
    if vehiculo_id <= 0:
        raise ValueError("vehiculo_id requerido.")
    anio, mes = _validar_periodo(data.get("anio"), data.get("mes"))
    vehiculo = repo.obtener_vehiculo(vehiculo_id)
    if not vehiculo:
        raise ValueError("Vehiculo no encontrado.")
    payload = {
        "vehiculo_id": vehiculo_id,
        "anio": anio,
        "mes": mes,
        "activo": bool(data.get("activo")),
        "motivo": (data.get("motivo") or "").strip()[:120],
        "observaciones": (data.get("observaciones") or "").strip() or None,
    }
    saved = repo.guardar_disponibilidad(payload)
    return {
        "disponibilidad": saved,
        "flota": listar_vehiculos(
            empresa_id=vehiculo["empresa_id"],
            sucursal_id=vehiculo["sucursal_id"],
            anio=anio,
            mes=mes,
        ),
    }


def capacidad_flota_mes(
    empresa_id: str = "1",
    sucursal_id: str = "TODAS",
    anio: int | None = None,
    mes: int | None = None,
) -> dict:
    """Devuelve la capacidad de flota activa para un mes dado.

    Cruza flota_vehiculos con flota_disponibilidad_mensual para saber
    cuántos camiones están activos, inactivos y anulados ese mes.
    """
    anio, mes = _validar_periodo(anio, mes)
    rows = repo.listar_vehiculos(
        empresa_id=str(empresa_id or "1"),
        sucursal_id=str(sucursal_id or "TODAS"),
        anio=anio,
        mes=mes,
        incluir_anulados=True,
    )
    label_map = _build_label_map()
    for r in rows:
        r["sucursal"] = _sucursal_label(str(r.get("sucursal_id") or ""), label_map)
        r["activo_mes"] = bool(r.get("activo_mes"))
        r["activo_base"] = bool(r.get("activo_base"))
        r["anulado"] = bool(r.get("anulado"))
        r["propio"] = bool(r.get("propio"))
    activos = [r for r in rows if r.get("activo_mes") and not r.get("anulado")]
    inactivos = [r for r in rows if not r.get("activo_mes") and not r.get("anulado")]
    por_sucursal: dict[str, dict] = {}
    for r in rows:
        if r.get("anulado"):
            continue
        suc = str(r.get("sucursal_id") or "")
        item = por_sucursal.setdefault(suc, {
            "sucursal_id": suc,
            "sucursal": _sucursal_label(suc),
            "activos": 0,
            "inactivos": 0,
        })
        if r.get("activo_mes"):
            item["activos"] += 1
        else:
            item["inactivos"] += 1
    return {
        "anio": anio,
        "mes": mes,
        "empresa_id": empresa_id,
        "sucursal_id": sucursal_id,
        "total_activos": len(activos),
        "total_inactivos": len(inactivos),
        "total_anulados": sum(1 for r in rows if r.get("anulado")),
        "por_sucursal": list(por_sucursal.values()),
        "vehiculos_activos": [
            {
                "id": r["id"],
                "codigo": r["codigo"],
                "descripcion": r["descripcion"],
                "placa": r.get("placa"),
                "sucursal_id": r.get("sucursal_id"),
                "sucursal": r.get("sucursal"),
                "motivo_inactivo": r.get("motivo_mes"),
            }
            for r in activos
        ],
        "vehiculos_inactivos": [
            {
                "id": r["id"],
                "codigo": r["codigo"],
                "descripcion": r["descripcion"],
                "placa": r.get("placa"),
                "sucursal_id": r.get("sucursal_id"),
                "sucursal": r.get("sucursal"),
                "motivo_inactivo": r.get("motivo_mes"),
            }
            for r in inactivos
        ],
    }


def eliminar_vehiculo(vehiculo_id: int) -> dict:
    if vehiculo_id <= 0:
        raise ValueError("vehiculo_id invalido.")
    ok = repo.eliminar_vehiculo(vehiculo_id)
    if not ok:
        raise ValueError("Vehiculo no encontrado.")
    return {"ok": True, "id": vehiculo_id}


def sync_desde_transportes(empresa_id: str = "1") -> dict:
    return repo.sync_desde_transportes(str(empresa_id or "1"))


def guardar_vehiculo(data: dict) -> dict:
    codigo = str(data.get("codigo") or "").strip()
    descripcion = str(data.get("descripcion") or "").strip()
    sucursal_id = str(data.get("sucursal_id") or "").strip()
    if not codigo:
        raise ValueError("Codigo requerido.")
    if not descripcion:
        raise ValueError("Descripcion requerida.")
    if not sucursal_id:
        raise ValueError("Sucursal requerida.")
    payload = {
        "empresa_id": str(data.get("empresa_id") or "1"),
        "sucursal_id": sucursal_id,
        "codigo": codigo,
        "descripcion": descripcion,
        "marca": (data.get("marca") or "").strip() or None,
        "modelo": (data.get("modelo") or "").strip() or None,
        "placa": (data.get("placa") or "").strip() or None,
        "carga_maxima_kg": data.get("carga_maxima_kg") or None,
        "capacidad_up": data.get("capacidad_up") or None,
        "propio": bool(data.get("propio", True)),
        "deposito_default_id": (data.get("deposito_default_id") or "").strip() or None,
        "deposito_default_nombre": (data.get("deposito_default_nombre") or "").strip() or None,
        "anulado": bool(data.get("anulado", False)),
        "activo_base": bool(data.get("activo_base", True)),
        "fuente": (data.get("fuente") or "MANUAL").strip()[:50],
        "observaciones": (data.get("observaciones") or "").strip() or None,
    }
    return repo.guardar_vehiculo(payload)
