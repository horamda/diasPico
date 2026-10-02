"""Cliente mínimo de la API de ChessERP para traer clientes.

IMPORTANTE: el login de ChessERP es por sesión y en tu MCP ya está resuelto.
Las rutas de login/clientes de acá son configurables por variables de entorno;
si tu MCP usa otras, ajustá CHESS_LOGIN_PATH / CHESS_CLIENTES_PATH o reemplazá
`ChessClient.login()` por la función de tu MCP. El parseo de clientes sí está
validado contra una respuesta real (estructura Clientes.eClientes[] con eClifuerza[]).
"""
import os
import requests

from . import dias as D

VIGENTE = "9999-12-31"


class ChessClient:
    def __init__(self, base_url=None, user=None, password=None, timeout=60):
        self.base = (base_url or os.environ.get("CHESS_BASE_URL", "")).rstrip("/")
        self.user = user or os.environ.get("CHESS_USER", "")
        self.password = password or os.environ.get("CHESS_PASSWORD", "")
        self.login_path = os.environ.get("CHESS_LOGIN_PATH", "/auth/login")
        self.clientes_path = os.environ.get("CHESS_CLIENTES_PATH", "/clientes/")
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update({"Accept": "application/json"})

    def login(self):
        r = self.s.post(self.base + self.login_path,
                        json={"usuario": self.user, "password": self.password}, timeout=self.timeout)
        r.raise_for_status()
        # Si la API devuelve un token en el cuerpo en vez de cookie, lo pasamos como header.
        try:
            body = r.json()
        except ValueError:
            body = {}
        token = body.get("sessionId") or body.get("token") if isinstance(body, dict) else None
        if token:
            self.s.headers["Authorization"] = token
        return True

    def clientes_lote(self, sucursal: int, nro_lote: int):
        r = self.s.get(self.base + self.clientes_path,
                       params={"sucursal": sucursal, "nroLote": nro_lote}, timeout=self.timeout)
        if r.status_code == 401:
            self.login()
            r = self.s.get(self.base + self.clientes_path,
                           params={"sucursal": sucursal, "nroLote": nro_lote}, timeout=self.timeout)
        r.raise_for_status()
        return extraer_clientes(r.json())

    def todos_los_clientes(self, sucursal: int, max_lotes=200):
        lote = 1
        while lote <= max_lotes:
            items = self.clientes_lote(sucursal, lote)
            if not items:
                break
            yield from items
            lote += 1


def extraer_clientes(payload):
    """Busca la lista eClientes donde esté (tolera envoltorios distintos)."""
    if isinstance(payload, dict):
        if "eClientes" in payload and isinstance(payload["eClientes"], list):
            return payload["eClientes"]
        for v in payload.values():
            res = extraer_clientes(v)
            if res:
                return res
    elif isinstance(payload, list):
        for v in payload:
            res = extraer_clientes(v)
            if res:
                return res
    return []


def _float(v):
    try:
        f = float(v)
        return f if f != 0 else None
    except (TypeError, ValueError):
        return None


def fuerza_vigente(c: dict, id_fuerza=1):
    """La fila de eClifuerza vigente (fechaFinFuerza 9999-12-31, no anulada) de la fuerza de venta dada."""
    filas = [f for f in c.get("eClifuerza") or [] if f.get("idFuerzaVentas") == id_fuerza and not f.get("anulado")]
    vig = [f for f in filas if str(f.get("fechaFinFuerza", "")).startswith(VIGENTE)]
    if vig:
        return vig[-1]
    return sorted(filas, key=lambda f: str(f.get("fechaInicioFuerza", "")))[-1] if filas else {}


def alias_vigente(c: dict):
    al = c.get("eClialias") or []
    want = c.get("idAliasVigente")
    for a in al:
        if a.get("idAlias") == want:
            return a
    return al[-1] if al else {}


def mapear_cliente(c: dict) -> dict:
    """Pasa un cliente crudo de Chess al dict de columnas de rt_cliente."""
    f = fuerza_vigente(c)
    a = alias_vigente(c)
    lat = _float(c.get("latitudGeoEntrega")) or _float(c.get("latitudGeo"))
    lng = _float(c.get("longitudGeoEntrega")) or _float(c.get("longitudGeo"))
    calle = (c.get("calleEntrega") or c.get("calle") or "").strip()
    altura = c.get("alturaEntrega") or c.get("altura") or ""
    loc = (c.get("desLocalidadEntrega") or c.get("desLocalidad") or "").strip().upper()
    return {
        "id_cliente": int(c["idCliente"]),
        "id_sucursal_erp": c.get("idSucursal"),
        "razon_social": a.get("razonSocial"),
        "fantasia": a.get("fantasiaSocial"),
        "domicilio": f"{calle} {altura}".strip() if calle else None,
        "localidad_erp": loc or None,
        "lat": lat, "lng": lng,
        "dias_erp": D.desde_chess(f.get("diasEntrega", "")),
        "ruta_venta": str(f.get("idRuta")) if f.get("idRuta") else None,
        "horario": c.get("horarioEntrega") or None,
        "canal": c.get("desSubcanalMkt") or None,
        "anulado": bool(c.get("anulado")),
    }
