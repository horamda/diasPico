from __future__ import annotations

import re
import threading
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin
from typing import Any

import psycopg2.extras
import requests
from flask import current_app

from app.database import pg_conn, pg_cursor
from app.services import sucursales_svc

_TABLES_READY = False
_TABLES_LOCK = threading.Lock()
_CONFIG_CACHE: dict[str, Any] | None = None
_CONFIG_LOCK = threading.Lock()

_GOOD_CLUSTERS = {'Ganador', 'En crecimiento'}
_CLUSTER_BONUS = {
    'Ganador': 30,
    'En crecimiento': 20,
    'Basico': 10,
    'Básico': 10,
    'Ventas bajas': 0,
}


FRESCURA_ARTICULOS_DDL = """
CREATE TABLE IF NOT EXISTS frescura_articulos (
    id BIGSERIAL PRIMARY KEY,
    sucursal_id VARCHAR(50) NOT NULL,
    codigo_articulo VARCHAR(50) NOT NULL,
    descripcion_articulo VARCHAR(255),
    marca VARCHAR(100),
    familia VARCHAR(100),
    categoria VARCHAR(100),
    lote VARCHAR(100) NOT NULL DEFAULT '',
    stock_actual NUMERIC(18,4) NOT NULL DEFAULT 0,
    stock_unidades NUMERIC(18,4),
    stock_bultos NUMERIC(18,4),
    unidad_medida VARCHAR(50),
    fecha_vencimiento DATE,
    dias_frescura_restantes INTEGER,
    estado_frescura VARCHAR(20) NOT NULL DEFAULT 'SIN_FECHA',
    fecha_actualizacion TIMESTAMP NOT NULL DEFAULT NOW(),
    origen_dato VARCHAR(120) NOT NULL DEFAULT 'api',
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_frescura_articulos UNIQUE (sucursal_id, codigo_articulo, lote)
);
"""

FRESCURA_SALES_CACHE_DDL = """
CREATE TABLE IF NOT EXISTS frescura_ventas_cliente_articulo (
    id BIGSERIAL PRIMARY KEY,
    fecha DATE NOT NULL,
    sucursal_id VARCHAR(50) NOT NULL,
    cliente_id VARCHAR(50) NOT NULL,
    codigo_cliente VARCHAR(50),
    razon_social VARCHAR(255),
    codigo_articulo VARCHAR(50) NOT NULL,
    descripcion_articulo VARCHAR(255),
    marca VARCHAR(100),
    categoria VARCHAR(100),
    division VARCHAR(100),
    cantidad NUMERIC(18,4) NOT NULL DEFAULT 0,
    hl NUMERIC(18,4) NOT NULL DEFAULT 0,
    importe NUMERIC(18,4) NOT NULL DEFAULT 0,
    unidades NUMERIC(18,4) NOT NULL DEFAULT 0,
    bultos NUMERIC(18,4) NOT NULL DEFAULT 0,
    pallets NUMERIC(18,4) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_frescura_ventas_cliente_articulo UNIQUE (fecha, sucursal_id, cliente_id, codigo_articulo)
);
"""

FRESCURA_SYNC_LOG_DDL = """
CREATE TABLE IF NOT EXISTS frescura_sync_log (
    id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMP,
    estado VARCHAR(20) NOT NULL DEFAULT 'running',
    source_url TEXT,
    total_items INTEGER NOT NULL DEFAULT 0,
    saved_rows INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
"""

FRESCURA_CONFIG_DDL = """
CREATE TABLE IF NOT EXISTS frescura_config (
    clave VARCHAR(100) PRIMARY KEY,
    valor TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
"""

FRESCURA_PLANES_DDL = """
CREATE TABLE IF NOT EXISTS frescura_planes_accion (
    id BIGSERIAL PRIMARY KEY,
    codigo_articulo VARCHAR(50) NOT NULL,
    sucursal_id VARCHAR(50),
    titulo VARCHAR(180) NOT NULL,
    resumen_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    plan_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    creado_por VARCHAR(120),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
"""


class FrescuraApiError(RuntimeError):
    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


def _ensure_tables() -> None:
    global _TABLES_READY
    if _TABLES_READY:
        return
    with _TABLES_LOCK:
        if _TABLES_READY:
            return
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    {FRESCURA_ARTICULOS_DDL}
                    {FRESCURA_SALES_CACHE_DDL}
                    {FRESCURA_SYNC_LOG_DDL}
                    {FRESCURA_CONFIG_DDL}
                    {FRESCURA_PLANES_DDL}
                    CREATE INDEX IF NOT EXISTS idx_frescura_articulos_lookup
                        ON frescura_articulos(sucursal_id, codigo_articulo, estado_frescura);
                    CREATE INDEX IF NOT EXISTS idx_frescura_articulos_fecha
                        ON frescura_articulos(fecha_vencimiento, dias_frescura_restantes);
                    CREATE INDEX IF NOT EXISTS idx_frescura_sales_lookup
                        ON frescura_ventas_cliente_articulo(codigo_articulo, sucursal_id, cliente_id, fecha);
                    CREATE INDEX IF NOT EXISTS idx_frescura_sales_cliente
                        ON frescura_ventas_cliente_articulo(cliente_id, sucursal_id, codigo_articulo);
                    CREATE INDEX IF NOT EXISTS idx_frescura_planes_lookup
                        ON frescura_planes_accion(codigo_articulo, sucursal_id, created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_frescura_sync_log_estado
                        ON frescura_sync_log(estado, started_at DESC);
                    ALTER TABLE frescura_articulos ADD COLUMN IF NOT EXISTS stock_unidades NUMERIC(18,4);
                    ALTER TABLE frescura_articulos ADD COLUMN IF NOT EXISTS stock_bultos   NUMERIC(18,4);
                    """
                )
        _TABLES_READY = True


def get_config() -> dict[str, Any]:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return dict(_CONFIG_CACHE)
    with _CONFIG_LOCK:
        if _CONFIG_CACHE is not None:
            return dict(_CONFIG_CACHE)
        _ensure_tables()
        with pg_cursor() as cur:
            cur.execute("SELECT clave, valor FROM frescura_config")
            rows = cur.fetchall() or []
        raw = {str(r['clave']): str(r['valor']) for r in rows}
        _CONFIG_CACHE = {
            'dias_cobertura': max(7, min(365, int(raw.get('dias_cobertura') or 90))),
        }
        return dict(_CONFIG_CACHE)


def save_config(data: dict[str, Any]) -> dict[str, Any]:
    global _CONFIG_CACHE
    _ensure_tables()
    dias = max(7, min(365, int(data.get('dias_cobertura') or 90)))
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO frescura_config (clave, valor, updated_at)
                VALUES ('dias_cobertura', %(valor)s, NOW())
                ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor, updated_at = NOW()
                """,
                {'valor': str(dias)},
            )
    with _CONFIG_LOCK:
        _CONFIG_CACHE = None
    return get_config()


def _norm(value: Any) -> str:
    return str(value or '').strip()


def _lower(value: Any) -> str:
    return _norm(value).lower()


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ''):
            return default
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return default
            if ',' in text and '.' not in text:
                text = text.replace(',', '.')
            else:
                text = text.replace(',', '')
            return float(text)
        return float(value)
    except Exception:
        return default


def _as_int(value: Any, default: int | None = None) -> int | None:
    try:
        if value in (None, ''):
            return default
        return int(float(value))
    except Exception:
        return default


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_date(value: Any) -> date | None:
    if value in (None, ''):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = _norm(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except Exception:
        for fmt in ('%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d', '%Y/%m/%d'):
            try:
                return datetime.strptime(text[:10], fmt).date()
            except Exception:
                continue
    return None


def _parse_csv_values(value: Any, default: list[str]) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        items = [_norm(item) for item in value if _norm(item)]
        return items or list(default)
    text = _norm(value)
    if not text:
        return list(default)
    items = [part.strip() for part in re.split(r'[,\s;|]+', text) if part.strip()]
    return items or list(default)


def _parse_map_values(value: Any, default: dict[str, str]) -> dict[str, str]:
    if isinstance(value, dict):
        mapping = {
            _norm(key): _norm(val)
            for key, val in value.items()
            if _norm(key) and _norm(val)
        }
        return mapping or dict(default)
    text = _norm(value)
    if not text:
        return dict(default)
    mapping: dict[str, str] = {}
    for chunk in re.split(r'[,\s;|]+', text):
        part = chunk.strip()
        if not part:
            continue
        if ':' in part:
            left, right = part.split(':', 1)
        elif '=' in part:
            left, right = part.split('=', 1)
        else:
            continue
        left = _norm(left)
        right = _norm(right)
        if left and right:
            mapping[left] = right
    return mapping or dict(default)


def _extract_nested_value(payload: Any, keys: tuple[str, ...]) -> str:
    if not isinstance(payload, dict):
        return ''
    for key in keys:
        value = payload.get(key)
        if _norm(value):
            return _norm(value)
    for nested_key in ('data', 'result', 'response', 'payload'):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            value = _extract_nested_value(nested, keys)
            if value:
                return value
    return ''


def _extract_api_errors(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    errors = payload.get('error')
    if not errors:
        return []
    if isinstance(errors, list):
        messages: list[str] = []
        for item in errors:
            if isinstance(item, dict):
                messages.append(_norm(item.get('mensaje') or item.get('message') or item))
            else:
                messages.append(_norm(item))
        return [msg for msg in messages if msg]
    if isinstance(errors, dict):
        message = _norm(errors.get('mensaje') or errors.get('message') or errors.get('detail') or errors)
        return [message] if message else []
    message = _norm(errors)
    return [message] if message else []


def _frescura_api_settings() -> dict[str, Any]:
    base_url = str(
        current_app.config.get('FRESCURA_API_BASE_URL')
        or current_app.config.get('FRESCURA_API_URL')
        or 'https://delpalacio.chesserp.com/AR459/web/api/chess/v1'
    ).strip()
    timeout = int(current_app.config.get('FRESCURA_API_TIMEOUT') or 20)
    user = str(current_app.config.get('FRESCURA_API_USER') or '').strip()
    password = str(current_app.config.get('FRESCURA_API_PASSWORD') or '').strip()
    token = str(current_app.config.get('FRESCURA_API_TOKEN') or '').strip()
    path = str(current_app.config.get('FRESCURA_API_PATH') or '/api/frescura/articulos').strip()
    deposits = _parse_csv_values(current_app.config.get('FRESCURA_API_DEPOSITOS') or '1,4', ['1', '4'])
    deposit_map = _parse_map_values(current_app.config.get('FRESCURA_API_DEPOSIT_MAP'), {'1': '1', '4': '2'})
    return {
        'base_url': base_url.rstrip('/'),
        'timeout': timeout,
        'user': user,
        'password': password,
        'token': token,
        'path': path,
        'deposits': deposits,
        'deposit_map': deposit_map,
    }


def _frescura_login(base_url: str, user: str, password: str, timeout: int) -> str:
    url = urljoin(base_url.rstrip('/') + '/', 'auth/login')
    try:
        response = requests.post(
            url,
            json={'usuario': user, 'password': password},
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise FrescuraApiError(f'No se pudo conectar con la API de frescura: {exc}', 503) from exc

    if response.status_code >= 400:
        detail: Any = response.text
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if payload is not None:
            detail = payload.get('error') or payload.get('message') or payload.get('detalle') or payload
        raise FrescuraApiError(f'API de frescura error {response.status_code}: {detail}', response.status_code)

    try:
        payload = response.json()
    except ValueError as exc:
        raise FrescuraApiError('La API de frescura no devolvio JSON valido al autenticar.', 502) from exc

    session_id = _extract_nested_value(payload, ('sessionId', 'session_id', 'token', 'session'))
    if not session_id:
        raise FrescuraApiError('La API de frescura no devolvio sessionId.', 502)
    return session_id


def _frescura_fetch_stock(base_url: str, session_id: str, deposito_id: str, timeout: int, fecha_stock: date | None = None) -> dict[str, Any]:
    url = urljoin(base_url.rstrip('/') + '/', 'stock/')
    fecha = (fecha_stock or date.today()).strftime('%d-%m-%Y')
    try:
        response = requests.get(
            url,
            headers={
                'Cookie': session_id,
                'Accept': 'application/json',
            },
            params={
                'idDeposito': deposito_id,
                'frescura': 'YES',
                'fechaStock': fecha,
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise FrescuraApiError(f'No se pudo consultar el stock de frescura: {exc}', 503) from exc

    if response.status_code >= 400:
        detail: Any = response.text
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if payload is not None:
            errors = _extract_api_errors(payload)
            if errors:
                detail = '; '.join(errors)
            else:
                detail = payload.get('error') or payload.get('message') or payload
        raise FrescuraApiError(f'API de frescura error {response.status_code}: {detail}', response.status_code)

    try:
        payload = response.json()
    except ValueError as exc:
        raise FrescuraApiError('La API de frescura no devolvio JSON valido.', 502) from exc

    errors = _extract_api_errors(payload)
    if errors:
        raise FrescuraApiError(f"Error de API al consultar stock: {'; '.join(errors)}", 502)
    return payload


def _extract_frescura_stock_items(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    stock = payload.get('dsStockFisicoApi')
    if isinstance(stock, dict):
        stock = stock.get('dsStock')
    if stock is None:
        for key in ('dsStock', 'items', 'data', 'rows', 'results'):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return [dict(item) for item in candidate if isinstance(item, dict)]
            if isinstance(candidate, dict):
                nested = _extract_frescura_stock_items(candidate)
                if nested:
                    return nested
        if any(key in payload for key in ('idDeposito', 'idArticulo', 'dsArticulo', 'fecVtoLote', 'cantBultos', 'cantUnidades')):
            return [dict(payload)]
        return []
    if isinstance(stock, dict):
        return [dict(stock)]
    if isinstance(stock, list):
        return [dict(item) for item in stock if isinstance(item, dict)]
    return []


def _map_frescura_deposito_to_sucursal(deposito_id: Any, deposit_map: dict[str, str]) -> str:
    key = _norm(deposito_id)
    if not key:
        return 'SIN_SUCURSAL'
    return deposit_map.get(key, key)


def _build_frescura_payload_metadata(
    item: dict[str, Any],
    *,
    deposito_id: str,
    sucursal_id: str,
    fecha_stock: str,
    origen_dato: str,
) -> dict[str, Any]:
    payload = dict(item)
    payload.setdefault('idDeposito', deposito_id)
    payload.setdefault('sucursal_id', sucursal_id)
    payload.setdefault('fechaStock', fecha_stock)
    payload.setdefault('origen_dato', origen_dato)
    return payload


def _estado_from_days(days: int | None) -> str:
    if days is None:
        return 'SIN_FECHA'
    if days < 30:
        return 'CRITICO'
    if days <= 60:
        return 'ALERTA'
    return 'OK'


def _priority_label(rank: int) -> str:
    return {
        1: 'Urgente',
        2: 'Alta',
        3: 'Media',
        4: 'Baja',
    }.get(rank, 'Baja')


def _cluster_bonus(cluster: str | None) -> int:
    return _CLUSTER_BONUS.get(_norm(cluster), 0)


def _clean_filters(filters: dict[str, Any]) -> dict[str, Any]:
    default_dias = get_config().get('dias_cobertura', 90)
    raw_dias = filters.get('dias_cobertura')
    dias_cobertura = max(7, min(365, int(raw_dias or default_dias)))
    return {
        'sucursal': _norm(filters.get('sucursal') or filters.get('sucursal_id') or 'TODAS') or 'TODAS',
        'estado': _norm(filters.get('estado') or filters.get('estado_frescura') or ''),
        'articulo': _norm(filters.get('articulo') or filters.get('q') or ''),
        'marca': _norm(filters.get('marca') or ''),
        'categoria': _norm(filters.get('categoria') or ''),
        'cluster': _norm(filters.get('cluster') or filters.get('cluster_cliente') or ''),
        'vendedor': _norm(filters.get('vendedor') or ''),
        'localidad': _norm(filters.get('localidad') or ''),
        'limit': max(1, min(int(filters.get('limit') or 100), 500)),
        'offset': max(0, int(filters.get('offset') or 0)),
        'dias_cobertura': dias_cobertura,
    }


def _sucursal_map() -> dict[str, str]:
    try:
        return {str(r['id']): str(r['nombre']) for r in sucursales_svc.listar()}
    except Exception:
        return {'1': 'Casa Central', '2': 'Dolores'}


def _freshness_where(filters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    conds = ['1=1']
    params: dict[str, Any] = {}
    sucursal = filters.get('sucursal')
    if sucursal and sucursal != 'TODAS':
        conds.append('fa.sucursal_id = %(sucursal)s')
        params['sucursal'] = sucursal
    estado = _norm(filters.get('estado')).upper()
    if estado:
        estados = [e.strip().upper() for e in re.split(r'[,\s;|]+', estado) if e.strip()]
        if len(estados) == 1:
            conds.append('UPPER(COALESCE(fa.estado_frescura, \'SIN_FECHA\')) = %(estado)s')
            params['estado'] = estados[0]
        else:
            conds.append('UPPER(COALESCE(fa.estado_frescura, \'SIN_FECHA\')) = ANY(%(estados)s)')
            params['estados'] = estados
    articulo = _norm(filters.get('articulo'))
    if articulo:
        conds.append('(fa.codigo_articulo ILIKE %(articulo_like)s OR COALESCE(fa.descripcion_articulo, \'\') ILIKE %(articulo_like)s)')
        params['articulo_like'] = f'%{articulo}%'
    marca = _norm(filters.get('marca'))
    if marca:
        conds.append('LOWER(COALESCE(NULLIF(TRIM(fa.marca), \'\'), \'\')) = LOWER(%(marca)s)')
        params['marca'] = marca
    categoria = _norm(filters.get('categoria'))
    if categoria:
        conds.append('LOWER(COALESCE(NULLIF(TRIM(fa.categoria), \'\'), \'\')) = LOWER(%(categoria)s)')
        params['categoria'] = categoria
    return ' AND '.join(conds), params


def _client_where(filters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    conds = ['1=1']
    params: dict[str, Any] = {}
    sucursal = filters.get('sucursal')
    if sucursal and sucursal != 'TODAS':
        conds.append('h.sucursal_id = %(sucursal)s')
        params['sucursal'] = sucursal
    cluster = _norm(filters.get('cluster'))
    if cluster:
        conds.append('LOWER(COALESCE(NULLIF(TRIM(h.cluster_dpo), \'\'), \'\')) = LOWER(%(cluster)s)')
        params['cluster'] = cluster
    localidad = _norm(filters.get('localidad'))
    if localidad:
        conds.append('LOWER(COALESCE(NULLIF(TRIM(h.localidad), \'\'), \'\')) = LOWER(%(localidad)s)')
        params['localidad'] = localidad
    vendedor = _norm(filters.get('vendedor'))
    if vendedor:
        conds.append(
            """
            EXISTS (
                SELECT 1
                FROM ventas_detalle v
                WHERE NULLIF(TRIM(v.cliente), '') = h.cliente
                  AND COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') = h.sucursal_id
                  AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'remit%%'
                  AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'comod%%'
                  AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'remit%%'
                  AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'comod%%'
                  AND LOWER(COALESCE(NULLIF(TRIM(v.descripcion_vendedor), ''), NULLIF(TRIM(v.descripcion_detallada_vendedor), ''), NULLIF(TRIM(v.vendedor), ''), '')) = LOWER(%(vendedor)s)
            )
            """
        )
        params['vendedor'] = vendedor
    return ' AND '.join(conds), params


def _sales_base_where(filters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    conds = [
        "NULLIF(TRIM(v.cliente), '') IS NOT NULL",
        "LOWER(TRIM(COALESCE(a.tipo_producto,''))) = 'mercaderia'",
        "LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'remit%%'",
        "LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'comod%%'",
        "LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'remit%%'",
        "LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'comod%%'",
    ]
    params: dict[str, Any] = {}
    sucursal = filters.get('sucursal')
    if sucursal and sucursal != 'TODAS':
        conds.append("COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') = %(sucursal)s")
        params['sucursal'] = sucursal
    articulo = _norm(filters.get('articulo'))
    if articulo:
        conds.append('(v.id_articulo::text ILIKE %(articulo_like)s OR COALESCE(v.descripcion_articulo, \'\') ILIKE %(articulo_like)s)')
        params['articulo_like'] = f'%{articulo}%'
    return ' AND '.join(conds), params


def _client_rows(filters: dict[str, Any]) -> list[dict[str, Any]]:
    client_where, params = _client_where(filters)
    with pg_cursor() as cur:
        cur.execute(
            f"""
            WITH latest_period AS (
                SELECT periodo_anio, periodo_mes
                FROM seg_cliente_cluster_historico
                ORDER BY periodo_anio DESC, periodo_mes DESC
                LIMIT 1
            )
            SELECT
                h.cliente,
                COALESCE(NULLIF(TRIM(h.descripcion_cliente), ''), h.cliente) AS cliente_nombre,
                h.sucursal_id AS sucursal,
                COALESCE(NULLIF(TRIM(suc.nombre), ''), h.sucursal_id) AS sucursal_nombre,
                COALESCE(NULLIF(TRIM(h.localidad), ''), '') AS localidad,
                COALESCE(NULLIF(TRIM(h.cluster_dpo), ''), 'Sin clasificar') AS cluster_dpo,
                COALESCE(h.score_total, 0) AS score_total,
                COALESCE(h.venta_ytd, 0) AS venta_ytd,
                COALESCE(h.hl_ytd, 0) AS hl_ytd,
                COALESCE(h.bultos_ytd, 0) AS bultos_ytd,
                COALESCE(h.pedidos_ytd, 0) AS pedidos_ytd,
                '' AS vendedor,
                '' AS vendedor_nombre
            FROM seg_cliente_cluster_historico h
            JOIN latest_period lp
              ON lp.periodo_anio = h.periodo_anio
             AND lp.periodo_mes = h.periodo_mes
            LEFT JOIN sucursales suc ON suc.id = h.sucursal_id
            WHERE {client_where}
            ORDER BY h.sucursal_id, COALESCE(h.score_total, 0) DESC NULLS LAST, h.cliente
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall() or []]


def _refresh_sales_cache(codigo_articulos: list[str], sucursal: str | None = None) -> int:
    _ensure_tables()
    if not codigo_articulos:
        return 0
    codes = [str(code).strip() for code in codigo_articulos if str(code).strip()]
    if not codes:
        return 0
    params: dict[str, Any] = {'codes': codes}
    suc_filter = ''
    if sucursal and sucursal != 'TODAS':
        suc_filter = "AND COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') = %(sucursal)s"
        params['sucursal'] = sucursal

    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT COUNT(DISTINCT codigo_articulo) AS cached_codes
                FROM frescura_ventas_cliente_articulo
                WHERE codigo_articulo = ANY(%(codes)s)
                  AND updated_at >= NOW() - INTERVAL '6 hours'
                """
                + ("" if sucursal in (None, '', 'TODAS') else " AND sucursal_id = %(sucursal)s"),
                params,
            )
            cached = cur.fetchone() or {}
            if int(cached.get('cached_codes') or 0) >= len(set(codes)):
                return 0

            cur.execute(
                """
                DELETE FROM frescura_ventas_cliente_articulo
                WHERE codigo_articulo = ANY(%(codes)s)
                """ + ("" if sucursal in (None, '', 'TODAS') else " AND sucursal_id = %(sucursal)s"),
                params,
            )

            cur.execute(
                f"""
                SELECT
                    v.fecha::date AS fecha,
                    COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') AS sucursal_id,
                    NULLIF(TRIM(v.cliente), '') AS cliente_id,
                    COALESCE(NULLIF(TRIM(v.cliente), ''), '') AS codigo_cliente,
                    MAX(COALESCE(NULLIF(TRIM(v.descripcion_cliente), ''), NULLIF(TRIM(cli.razon_social), ''), NULLIF(TRIM(cli.nombre_fantasia), ''), NULLIF(TRIM(v.cliente), ''), '')) AS razon_social,
                    v.id_articulo::text AS codigo_articulo,
                    MAX(COALESCE(NULLIF(TRIM(v.descripcion_articulo), ''), NULLIF(TRIM(a.descripcion), ''), '')) AS descripcion_articulo,
                    MAX(COALESCE(NULLIF(TRIM(a.marca), ''), '')) AS marca,
                    MAX(COALESCE(NULLIF(TRIM(a.familia), ''), NULLIF(TRIM(a.division), ''), '')) AS categoria,
                    MAX(COALESCE(NULLIF(TRIM(a.division), ''), '')) AS division,
                    SUM(COALESCE(v.unidad_medida, 0)) AS cantidad,
                    SUM(COALESCE(v.unidad_medida, 0)) AS hl,
                    SUM(COALESCE(v.importe_neto, 0)) AS importe,
                    SUM(COALESCE(v.unidad_paquete, 0)) AS unidades,
                    SUM(COALESCE(v.bultos, 0)) AS bultos,
                    SUM(CASE WHEN COALESCE(a.bultos_por_pallet, 0) > 0
                             THEN COALESCE(v.bultos, 0) / a.bultos_por_pallet
                             ELSE 0 END) AS pallets
                FROM ventas_detalle v
                JOIN articulos a ON a.id_articulo = v.id_articulo
                LEFT JOIN clientes cli
                       ON cli.cliente = NULLIF(TRIM(v.cliente), '')
                      AND COALESCE(NULLIF(TRIM(cli.sucursal), ''), COALESCE(NULLIF(TRIM(v.sucursal), ''), '1')) = COALESCE(NULLIF(TRIM(v.sucursal), ''), '1')
                WHERE v.id_articulo::text = ANY(%(codes)s)
                  AND NULLIF(TRIM(v.cliente), '') IS NOT NULL
                  AND LOWER(TRIM(COALESCE(a.tipo_producto,''))) = 'mercaderia'
                  AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'remit%%'
                  AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'comod%%'
                  AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'remit%%'
                  AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'comod%%'
                  {suc_filter}
                GROUP BY 1, 2, 3, 6
                ORDER BY 1, 2, 3, 6
                """,
                params,
            )
            rows = cur.fetchall() or []
            if rows:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO frescura_ventas_cliente_articulo (
                        fecha, sucursal_id, cliente_id, codigo_cliente, razon_social,
                        codigo_articulo, descripcion_articulo, marca, categoria, division,
                        cantidad, hl, importe, unidades, bultos, pallets, created_at, updated_at
                    ) VALUES %s
                    ON CONFLICT (fecha, sucursal_id, cliente_id, codigo_articulo) DO UPDATE SET
                        codigo_cliente = EXCLUDED.codigo_cliente,
                        razon_social = EXCLUDED.razon_social,
                        descripcion_articulo = EXCLUDED.descripcion_articulo,
                        marca = EXCLUDED.marca,
                        categoria = EXCLUDED.categoria,
                        division = EXCLUDED.division,
                        cantidad = EXCLUDED.cantidad,
                        hl = EXCLUDED.hl,
                        importe = EXCLUDED.importe,
                        unidades = EXCLUDED.unidades,
                        bultos = EXCLUDED.bultos,
                        pallets = EXCLUDED.pallets,
                        updated_at = NOW()
                    """,
                    [
                        (
                            r['fecha'],
                            r['sucursal_id'],
                            r['cliente_id'],
                            r['codigo_cliente'],
                            r['razon_social'],
                            r['codigo_articulo'],
                            r['descripcion_articulo'],
                            r['marca'],
                            r['categoria'],
                            r['division'],
                            r['cantidad'],
                            r['hl'],
                            r['importe'],
                            r['unidades'],
                            r['bultos'],
                            r['pallets'],
                            _utc_now_naive(),
                            _utc_now_naive(),
                        )
                        for r in rows
                    ],
                )
    return len(rows)


def _freshness_rows(filters: dict[str, Any]) -> list[dict[str, Any]]:
    where_sql, params = _freshness_where(filters)
    with pg_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                fa.sucursal_id,
                COALESCE(NULLIF(TRIM(suc.nombre), ''), fa.sucursal_id) AS sucursal_nombre,
                fa.codigo_articulo,
                MAX(COALESCE(NULLIF(TRIM(fa.descripcion_articulo), ''), NULLIF(TRIM(a.descripcion), ''), fa.codigo_articulo)) AS descripcion_articulo,
                MAX(COALESCE(NULLIF(TRIM(fa.marca), ''), NULLIF(TRIM(a.marca), ''), '')) AS marca,
                MAX(COALESCE(NULLIF(TRIM(fa.familia), ''), NULLIF(TRIM(a.familia), ''), NULLIF(TRIM(a.division), ''), '')) AS familia,
                MAX(COALESCE(NULLIF(TRIM(fa.categoria), ''), NULLIF(TRIM(a.familia), ''), NULLIF(TRIM(a.division), ''), '')) AS categoria,
                MAX(COALESCE(NULLIF(TRIM(fa.lote), ''), '')) AS lote,
                JSONB_AGG(
                    JSONB_BUILD_OBJECT(
                        'lote', COALESCE(NULLIF(TRIM(fa.lote), ''), 'SIN_LOTE'),
                        'stock_actual', COALESCE(fa.stock_actual, 0),
                        'stock_unidades', fa.stock_unidades,
                        'stock_bultos', fa.stock_bultos,
                        'fecha_vencimiento', fa.fecha_vencimiento,
                        'dias_frescura_restantes', fa.dias_frescura_restantes,
                        'estado_frescura', COALESCE(fa.estado_frescura, 'SIN_FECHA')
                    )
                    ORDER BY fa.fecha_vencimiento NULLS LAST, COALESCE(NULLIF(TRIM(fa.lote), ''), 'SIN_LOTE')
                ) AS lotes,
                SUM(COALESCE(fa.stock_actual, 0)) AS stock_actual,
                SUM(COALESCE(fa.stock_unidades, 0)) AS stock_unidades_total,
                SUM(COALESCE(fa.stock_bultos, 0)) AS stock_bultos_total,
                MAX(a.unidades_por_bulto) AS uxb,
                MAX(fa.unidad_medida) AS unidad_medida,
                MIN(fa.fecha_vencimiento) AS fecha_vencimiento,
                MIN(fa.dias_frescura_restantes) AS dias_frescura_restantes,
                CASE
                    WHEN MIN(fa.dias_frescura_restantes) IS NULL THEN 'SIN_FECHA'
                    WHEN MIN(fa.dias_frescura_restantes) < 30 THEN 'CRITICO'
                    WHEN MIN(fa.dias_frescura_restantes) <= 60 THEN 'ALERTA'
                    ELSE 'OK'
                END AS estado_frescura,
                MAX(fa.fecha_actualizacion) AS fecha_actualizacion,
                MAX(fa.origen_dato) AS origen_dato
            FROM frescura_articulos fa
            JOIN articulos a
              ON a.id_articulo::text = fa.codigo_articulo
             AND UPPER(TRIM(COALESCE(a.tipo_producto, ''))) = 'MERCADERIA'
            LEFT JOIN sucursales suc ON suc.id = fa.sucursal_id
            WHERE {where_sql}
              AND fa.stock_actual > 0
            GROUP BY fa.sucursal_id, suc.nombre, fa.codigo_articulo
            ORDER BY
                CASE
                    WHEN MIN(fa.dias_frescura_restantes) IS NULL THEN 4
                    WHEN MIN(fa.dias_frescura_restantes) < 30 THEN 1
                    WHEN MIN(fa.dias_frescura_restantes) <= 60 THEN 2
                    ELSE 3
                END,
                dias_frescura_restantes NULLS LAST,
                fa.sucursal_id,
                stock_actual DESC,
                fa.codigo_articulo
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            {**params, 'limit': filters['limit'], 'offset': filters['offset']},
        )
        return [dict(r) for r in cur.fetchall() or []]


def _article_sales_rows(codigo_articulos: list[str], sucursal: str | None = None) -> list[dict[str, Any]]:
    codes = [str(code).strip() for code in codigo_articulos if str(code).strip()]
    if not codes:
        return []
    params: dict[str, Any] = {'codes': codes}
    suc_filter = ''
    if sucursal and sucursal != 'TODAS':
        suc_filter = 'AND s.sucursal_id = %(sucursal)s'
        params['sucursal'] = sucursal
    with pg_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                s.sucursal_id,
                s.codigo_articulo,
                s.cliente_id,
                MAX(s.razon_social) AS cliente_nombre,
                MAX(s.marca) AS marca,
                MAX(s.categoria) AS categoria,
                MAX(s.division) AS division,
                MAX(s.fecha) AS ultima_venta,
                MIN(s.fecha) AS primera_venta,
                SUM(s.cantidad) AS cantidad,
                SUM(s.hl) AS hl,
                SUM(s.importe) AS importe,
                SUM(s.unidades) AS unidades,
                SUM(s.bultos) AS bultos,
                SUM(s.pallets) AS pallets
            FROM frescura_ventas_cliente_articulo s
            WHERE s.codigo_articulo = ANY(%(codes)s)
            {suc_filter}
            GROUP BY s.sucursal_id, s.codigo_articulo, s.cliente_id
            ORDER BY s.sucursal_id, s.codigo_articulo, ultima_venta DESC NULLS LAST, s.cliente_id
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall() or []]


def _article_sales_summary(codigo_articulos: list[str], filters: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    codes = [str(code).strip() for code in codigo_articulos if str(code).strip()]
    if not codes:
        return {}
    client_where, client_params = _client_where(filters)
    dias_cobertura = max(7, min(365, int(filters.get('dias_cobertura') or 90)))
    params: dict[str, Any] = {
        'codes': sorted(set(codes)),
        'good_clusters': sorted(_GOOD_CLUSTERS),
        'dias_cobertura': dias_cobertura,
        **client_params,
    }
    with pg_cursor() as cur:
        cur.execute(
            f"""
            WITH latest_period AS (
                SELECT periodo_anio, periodo_mes
                FROM seg_cliente_cluster_historico
                ORDER BY periodo_anio DESC, periodo_mes DESC
                LIMIT 1
            ),
            active_clients AS (
                SELECT
                    h.cliente,
                    h.sucursal_id,
                    (
                        COALESCE(h.score_total, 0) >= 65
                        AND COALESCE(NULLIF(TRIM(h.cluster_dpo), ''), '') = ANY(%(good_clusters)s)
                    ) AS is_good
                FROM seg_cliente_cluster_historico h
                JOIN latest_period lp
                  ON lp.periodo_anio = h.periodo_anio
                 AND lp.periodo_mes = h.periodo_mes
                WHERE {client_where}
            ),
            sales_by_client AS (
                SELECT
                    COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') AS sucursal_id,
                    v.id_articulo::text AS codigo_articulo,
                    NULLIF(TRIM(v.cliente), '') AS cliente_id,
                    BOOL_OR(ac.is_good) AS is_good,
                    MAX(v.fecha::date) AS ultima_venta
                FROM ventas_detalle v
                JOIN articulos a ON a.id_articulo = v.id_articulo
                JOIN active_clients ac
                  ON ac.cliente = NULLIF(TRIM(v.cliente), '')
                 AND ac.sucursal_id = COALESCE(NULLIF(TRIM(v.sucursal), ''), '1')
                WHERE v.id_articulo::text = ANY(%(codes)s)
                  AND NULLIF(TRIM(v.cliente), '') IS NOT NULL
                  AND UPPER(TRIM(COALESCE(a.tipo_producto, ''))) = 'MERCADERIA'
                  AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'remit%%'
                  AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'comod%%'
                  AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'remit%%'
                  AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'comod%%'
                GROUP BY 1, 2, 3
            )
            SELECT
                sucursal_id,
                codigo_articulo,
                COUNT(*) AS compradores,
                COUNT(*) FILTER (WHERE ultima_venta >= CURRENT_DATE - INTERVAL '30 days') AS compradores_30,
                COUNT(*) FILTER (WHERE ultima_venta >= CURRENT_DATE - INTERVAL '60 days') AS compradores_60,
                COUNT(*) FILTER (WHERE ultima_venta >= CURRENT_DATE - INTERVAL '90 days') AS compradores_90,
                COUNT(*) FILTER (WHERE ultima_venta >= CURRENT_DATE - %(dias_cobertura)s * INTERVAL '1 day') AS compradores_config,
                COUNT(*) FILTER (WHERE is_good) AS compradores_good
            FROM sales_by_client
            GROUP BY 1, 2
            """,
            params,
        )
        return {
            (str(row.get('sucursal_id') or ''), str(row.get('codigo_articulo') or '')): dict(row)
            for row in cur.fetchall() or []
        }


def _vendor_options(filters: dict[str, Any]) -> list[str]:
    option_filters = {**filters, 'vendedor': ''}
    client_where, client_params = _client_where(option_filters)
    with pg_cursor() as cur:
        cur.execute(
            f"""
            WITH latest_period AS (
                SELECT periodo_anio, periodo_mes
                FROM seg_cliente_cluster_historico
                ORDER BY periodo_anio DESC, periodo_mes DESC
                LIMIT 1
            ),
            active_clients AS (
                SELECT h.cliente, h.sucursal_id
                FROM seg_cliente_cluster_historico h
                JOIN latest_period lp
                  ON lp.periodo_anio = h.periodo_anio
                 AND lp.periodo_mes = h.periodo_mes
                WHERE {client_where}
            )
            SELECT
                COALESCE(
                    NULLIF(TRIM(v.descripcion_vendedor), ''),
                    NULLIF(TRIM(v.descripcion_detallada_vendedor), ''),
                    NULLIF(TRIM(v.vendedor), ''),
                    ''
                ) AS vendedor
            FROM ventas_detalle v
            JOIN active_clients ac
              ON ac.cliente = NULLIF(TRIM(v.cliente), '')
             AND ac.sucursal_id = COALESCE(NULLIF(TRIM(v.sucursal), ''), '1')
            WHERE v.fecha >= date_trunc('year', CURRENT_DATE)
              AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'remit%%'
              AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'comod%%'
              AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'remit%%'
              AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'comod%%'
            GROUP BY 1
            HAVING COALESCE(
                NULLIF(TRIM(v.descripcion_vendedor), ''),
                NULLIF(TRIM(v.descripcion_detallada_vendedor), ''),
                NULLIF(TRIM(v.vendedor), ''),
                ''
            ) <> ''
            ORDER BY 1
            LIMIT 250
            """,
            client_params,
        )
        return [str(row.get('vendedor') or '') for row in cur.fetchall() or [] if _norm(row.get('vendedor'))]


def _active_clients_by_branch(filters: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    clients = _client_rows(filters)
    by_branch: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in clients:
        by_branch[str(row.get('sucursal') or '1')].append(row)
    return by_branch


def _score_opportunity(client: dict[str, Any], fact: dict[str, Any] | None, category_match: bool) -> tuple[int, float, str]:
    cluster = _norm(client.get('cluster_dpo'))
    score_total = _as_float(client.get('score_total'), 0.0)
    score = 0.0
    reasons: list[str] = []
    rank = 4

    if fact:
        ultima = fact.get('ultima_venta')
        dias = (date.today() - ultima).days if isinstance(ultima, date) else None
        if dias is not None and dias <= 30:
            score += 45
            rank = 1
            reasons.append('Compra en 30 dias')
        elif dias is not None and dias <= 60:
            score += 35
            rank = 1
            reasons.append('Compra en 60 dias')
        elif dias is not None and dias <= 90:
            score += 25
            rank = 1
            reasons.append('Compra en 90 dias')
        else:
            score += 10
            rank = 2
            reasons.append('Compra historica')
    else:
        if category_match:
            score += 30
            rank = 3
            reasons.append('Compra categoria o marca')
        else:
            score += 18
            reasons.append('Nunca compro SKU')

    score += _cluster_bonus(cluster)
    if score_total:
        score += min(20.0, score_total * 0.2)
    if cluster in _GOOD_CLUSTERS:
        score += 8
        reasons.append(cluster)
    if category_match:
        score += 10
    if score_total >= 80:
        score += 8
    elif score_total >= 65:
        score += 4
    score = max(0.0, min(100.0, round(score, 2)))
    return rank, score, '; '.join(reasons) if reasons else 'Sin observaciones'


def _client_payload_from_fact(client: dict[str, Any], fact: dict[str, Any] | None, category_match: bool) -> dict[str, Any]:
    rank, score, reason = _score_opportunity(client, fact, category_match)
    ultima = fact.get('ultima_venta') if fact else None
    dias = (date.today() - ultima).days if isinstance(ultima, date) else None
    return {
        'cliente': client.get('cliente'),
        'cliente_nombre': client.get('cliente_nombre'),
        'sucursal': client.get('sucursal'),
        'sucursal_nombre': client.get('sucursal_nombre'),
        'localidad': client.get('localidad'),
        'cluster_dpo': client.get('cluster_dpo'),
        'score_total': _as_float(client.get('score_total'), 0.0),
        'vendedor': client.get('vendedor'),
        'vendedor_nombre': client.get('vendedor_nombre'),
        'ultima_venta': ultima.isoformat() if isinstance(ultima, date) else None,
        'dias_desde_ultima_venta': dias,
        'categoria_o_marca': bool(category_match),
        'prioridad_nivel': rank,
        'prioridad_accion': _priority_label(rank),
        'score_oportunidad': score,
        'motivo': reason,
    }


def _sales_metrics_from_facts(facts: list[dict[str, Any]], stock_bultos: float = 0.0) -> dict[str, Any]:
    first_dates = [f.get('primera_venta') for f in facts if isinstance(f.get('primera_venta'), date)]
    last_dates = [f.get('ultima_venta') for f in facts if isinstance(f.get('ultima_venta'), date)]
    primera = min(first_dates) if first_dates else None
    ultima = max(last_dates) if last_dates else None
    days_span = max(1, (date.today() - primera).days + 1) if primera else 0
    bultos = sum(_as_float(f.get('bultos'), 0.0) for f in facts)
    unidades = sum(_as_float(f.get('unidades'), 0.0) for f in facts)
    hl = sum(_as_float(f.get('hl'), 0.0) for f in facts)
    importe = sum(_as_float(f.get('importe'), 0.0) for f in facts)
    promedio_bultos_dia = (bultos / days_span) if days_span else 0.0
    dias_stock = (stock_bultos / promedio_bultos_dia) if promedio_bultos_dia > 0 and stock_bultos > 0 else None
    return {
        'venta_primera_fecha': primera.isoformat() if primera else None,
        'venta_ultima_fecha': ultima.isoformat() if ultima else None,
        'venta_dias_historia': days_span,
        'venta_clientes_total': len(facts),
        'venta_bultos_total': round(bultos, 2),
        'venta_unidades_total': round(unidades, 2),
        'venta_hl_total': round(hl, 2),
        'venta_importe_total': round(importe, 2),
        'venta_promedio_bultos_dia': round(promedio_bultos_dia, 2),
        'stock_dias_estimados_venta': round(dias_stock, 1) if dias_stock is not None else None,
    }


def _article_lotes_payload(article: dict[str, Any]) -> list[dict[str, Any]]:
    raw_lotes = article.get('lotes') or []
    if not isinstance(raw_lotes, list):
        raw_lotes = []
    lotes: list[dict[str, Any]] = []
    for row in raw_lotes:
        if not isinstance(row, dict):
            continue
        fecha = row.get('fecha_vencimiento')
        su = row.get('stock_unidades')
        sb = row.get('stock_bultos')
        lotes.append({
            'lote': _norm(row.get('lote') or 'SIN_LOTE'),
            'stock_actual': _as_float(row.get('stock_actual'), 0.0),
            'stock_unidades': _as_float(su) if su is not None else None,
            'stock_bultos':   _as_float(sb) if sb is not None else None,
            'fecha_vencimiento': fecha.isoformat() if isinstance(fecha, date) else (_norm(fecha) or None),
            'dias_frescura_restantes': _as_int(row.get('dias_frescura_restantes')),
            'estado_frescura': _norm(row.get('estado_frescura') or 'SIN_FECHA').upper(),
        })
    lotes = sorted(
        lotes,
        key=lambda item: (
            item.get('fecha_vencimiento') or '9999-12-31',
            item.get('lote') or '',
        ),
    )
    if lotes:
        return lotes
    fecha = article.get('fecha_vencimiento')
    _su = article.get('stock_unidades')
    _sb = article.get('stock_bultos')
    return [{
        'lote': _norm(article.get('lote') or 'SIN_LOTE'),
        'stock_actual': _as_float(article.get('stock_actual'), 0.0),
        'stock_unidades': _as_float(_su) if _su is not None else None,
        'stock_bultos':   _as_float(_sb) if _sb is not None else None,
        'fecha_vencimiento': fecha.isoformat() if isinstance(fecha, date) else (_norm(fecha) or None),
        'dias_frescura_restantes': _as_int(article.get('dias_frescura_restantes')),
        'estado_frescura': _norm(article.get('estado_frescura') or 'SIN_FECHA').upper(),
    }]


def _article_context(codigo_articulo: str, sucursal: str | None = None, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    raw_filters = filters or {}
    filters = _clean_filters({'sucursal': sucursal or 'TODAS', 'limit': 1, 'offset': 0, **raw_filters})
    filters['articulo'] = codigo_articulo
    _refresh_sales_cache([codigo_articulo], sucursal=sucursal)
    art_rows = _freshness_rows(filters)
    if not art_rows:
        return {'articulo': None, 'clientes': [], 'fact_rows': [], 'category_match': set()}
    article = art_rows[0]
    client_filters = _clean_filters({'sucursal': sucursal or article.get('sucursal_id', 'TODAS'), **(filters or {})})
    clients = _client_rows(client_filters)
    client_map = {(str(c['cliente']), str(c['sucursal'])): c for c in clients}
    facts = _article_sales_rows([codigo_articulo], sucursal=sucursal or article.get('sucursal_id'))
    fact_map: dict[tuple[str, str], dict[str, Any]] = {}
    for fact in facts:
        key = (str(fact.get('cliente_id') or ''), str(fact.get('sucursal_id') or ''))
        prev = fact_map.get(key)
        if not prev or (fact.get('ultima_venta') and fact['ultima_venta'] > prev.get('ultima_venta')):
            fact_map[key] = fact

    include_category_match = _lower(raw_filters.get('include_categoria') or raw_filters.get('include_category')) in {'1', 'true', 'si', 'yes'}
    brand = _lower(article.get('marca'))
    categoria = _lower(article.get('categoria'))
    cat_match: set[tuple[str, str]] = set()
    if include_category_match and (brand or categoria):
        params: dict[str, Any] = {'codigo_articulo': str(codigo_articulo)}
        suc_filter = ''
        if sucursal and sucursal != 'TODAS':
            suc_filter = "AND COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') = %(sucursal)s"
            params['sucursal'] = sucursal
        with pg_cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') AS sucursal_id,
                    NULLIF(TRIM(v.cliente), '') AS cliente_id,
                    MAX(v.fecha) AS ultima_venta
                FROM ventas_detalle v
                JOIN articulos a ON a.id_articulo = v.id_articulo
                WHERE NULLIF(TRIM(v.cliente), '') IS NOT NULL
                  AND LOWER(TRIM(COALESCE(a.tipo_producto,''))) = 'mercaderia'
                  AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'remit%%'
                  AND LOWER(TRIM(COALESCE(v.documento,''))) NOT LIKE 'comod%%'
                  AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'remit%%'
                  AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'comod%%'
                  AND v.id_articulo::text <> %(codigo_articulo)s
                  AND (
                        LOWER(COALESCE(NULLIF(TRIM(a.marca), ''), '')) = %(brand)s
                     OR LOWER(COALESCE(NULLIF(TRIM(a.familia), ''), NULLIF(TRIM(a.division), ''), '')) = %(categoria)s
                  )
                  {suc_filter}
                GROUP BY 1, 2
                """,
                {**params, 'brand': brand, 'categoria': categoria},
            )
            for row in cur.fetchall() or []:
                cat_match.add((str(row['cliente_id'] or ''), str(row['sucursal_id'] or '')))

    return {
        'articulo': article,
        'clientes': clients,
        'facts': list(fact_map.values()),
        'category_match': cat_match,
        'client_map': client_map,
    }


def _build_article_summary(article: dict[str, Any], clients_by_branch: dict[str, list[dict[str, Any]]], facts: list[dict[str, Any]]) -> dict[str, Any]:
    branch = str(article.get('sucursal_id') or '1')
    client_rows = clients_by_branch.get(branch, [])
    active_total = len(client_rows)
    buyer_map: dict[str, dict[str, Any]] = {}
    for fact in facts:
        if str(fact.get('sucursal_id') or '') != branch:
            continue
        cliente_id = str(fact.get('cliente_id') or '')
        if not cliente_id:
            continue
        prev = buyer_map.get(cliente_id)
        if not prev or (fact.get('ultima_venta') and fact['ultima_venta'] > prev.get('ultima_venta')):
            buyer_map[cliente_id] = fact

    today = date.today()
    buyers = list(buyer_map.values())
    buyers_recent_30 = [f for f in buyers if isinstance(f.get('ultima_venta'), date) and (today - f['ultima_venta']).days <= 30]
    buyers_recent_60 = [f for f in buyers if isinstance(f.get('ultima_venta'), date) and (today - f['ultima_venta']).days <= 60]
    buyers_recent_90 = [f for f in buyers if isinstance(f.get('ultima_venta'), date) and (today - f['ultima_venta']).days <= 90]
    buyers_inactive = [f for f in buyers if not isinstance(f.get('ultima_venta'), date) or (today - f['ultima_venta']).days > 90]
    buyers_set = set(buyer_map)
    good_clients = [c for c in client_rows if _norm(c.get('cluster_dpo')) in _GOOD_CLUSTERS and _as_float(c.get('score_total'), 0.0) >= 65]
    potential = [c for c in good_clients if str(c.get('cliente') or '') not in buyers_set]
    coverage = round((len(buyers) / active_total * 100), 2) if active_total else 0.0
    if _norm(article.get('estado_frescura')) == 'CRITICO':
        rank = 1
    elif _norm(article.get('estado_frescura')) == 'ALERTA':
        rank = 2
    elif coverage < 50:
        rank = 2
    elif coverage < 80:
        rank = 3
    else:
        rank = 4
    action = {
        1: 'Accion urgente con cartera activa',
        2: 'Activar recuperacion y cartera afim',
        3: 'Sostener con foco en clientes potenciales',
        4: 'Monitoreo de rutina',
    }[rank]
    lotes = _article_lotes_payload(article)
    return {
        'sucursal_id': branch,
        'sucursal_nombre': article.get('sucursal_nombre'),
        'codigo_articulo': article.get('codigo_articulo'),
        'descripcion_articulo': article.get('descripcion_articulo'),
        'marca': article.get('marca'),
        'familia': article.get('familia'),
        'categoria': article.get('categoria'),
        'stock_actual': _as_float(article.get('stock_actual'), 0.0),
        'unidad_medida': article.get('unidad_medida'),
        'fecha_vencimiento': article.get('fecha_vencimiento').isoformat() if isinstance(article.get('fecha_vencimiento'), date) else None,
        'proximo_vencimiento': article.get('fecha_vencimiento').isoformat() if isinstance(article.get('fecha_vencimiento'), date) else None,
        'dias_frescura_restantes': _as_int(article.get('dias_frescura_restantes')),
        'estado_frescura': article.get('estado_frescura'),
        'lotes': lotes,
        'lotes_count': len(lotes),
        'clientes_activos_total': active_total,
        'clientes_que_compraron_alguna_vez': len(buyers),
        'clientes_ultimos_30_dias': len(buyers_recent_30),
        'clientes_ultimos_60_dias': len(buyers_recent_60),
        'clientes_ultimos_90_dias': len(buyers_recent_90),
        'clientes_inactivos_para_el_sku': len(buyers_inactive),
        'clientes_que_nunca_compraron': max(0, active_total - len(buyers)),
        'cobertura_comercial_porcentaje': coverage,
        'potencial_clientes': len(potential),
        'prioridad_nivel': rank,
        'prioridad_accion': _priority_label(rank),
        'accion_sugerida': action,
        'fecha_actualizacion': article.get('fecha_actualizacion').isoformat() if isinstance(article.get('fecha_actualizacion'), datetime) else None,
    }


def _build_article_stock_summary(article: dict[str, Any]) -> dict[str, Any]:
    branch = str(article.get('sucursal_id') or '1')
    estado = _norm(article.get('estado_frescura')).upper() or 'SIN_FECHA'
    if estado == 'CRITICO':
        rank = 1
        action = 'Accion urgente por frescura critica'
    elif estado == 'ALERTA':
        rank = 2
        action = 'Priorizar rotacion antes del vencimiento'
    elif estado == 'SIN_FECHA':
        rank = 3
        action = 'Completar fecha de vencimiento'
    else:
        rank = 4
        action = 'Monitoreo de rutina'
    lotes = _article_lotes_payload(article)
    return {
        'sucursal_id': branch,
        'sucursal_nombre': article.get('sucursal_nombre'),
        'codigo_articulo': article.get('codigo_articulo'),
        'descripcion_articulo': article.get('descripcion_articulo'),
        'marca': article.get('marca'),
        'familia': article.get('familia'),
        'categoria': article.get('categoria'),
        'stock_actual': _as_float(article.get('stock_actual'), 0.0),
        'unidad_medida': article.get('unidad_medida'),
        'fecha_vencimiento': article.get('fecha_vencimiento').isoformat() if isinstance(article.get('fecha_vencimiento'), date) else None,
        'proximo_vencimiento': article.get('fecha_vencimiento').isoformat() if isinstance(article.get('fecha_vencimiento'), date) else None,
        'dias_frescura_restantes': _as_int(article.get('dias_frescura_restantes')),
        'estado_frescura': estado,
        'lotes': lotes,
        'lotes_count': len(lotes),
        'clientes_activos_total': 0,
        'clientes_que_compraron_alguna_vez': 0,
        'clientes_ultimos_30_dias': 0,
        'clientes_ultimos_60_dias': 0,
        'clientes_ultimos_90_dias': 0,
        'clientes_inactivos_para_el_sku': 0,
        'clientes_que_nunca_compraron': 0,
        'cobertura_comercial_porcentaje': 0.0,
        'potencial_clientes': 0,
        'prioridad_nivel': rank,
        'prioridad_accion': _priority_label(rank),
        'accion_sugerida': action,
        'fecha_actualizacion': article.get('fecha_actualizacion').isoformat() if isinstance(article.get('fecha_actualizacion'), datetime) else None,
    }


def _filter_payload_items(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ('articulos', 'data', 'items', 'results', 'rows'):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = _filter_payload_items(value)
                if nested:
                    return nested
        if any(k in payload for k in ('codigo_articulo', 'id_articulo', 'lote', 'stock_actual')):
            return [dict(payload)]
    return []


def _normalize_api_row(
    item: dict[str, Any],
    *,
    sucursal_id: str | None = None,
    deposito_id: str | None = None,
    fecha_stock: str | None = None,
    origen_dato: str = 'erp_chess_stock',
) -> dict[str, Any]:
    lote = _norm(
        item.get('lote')
        or item.get('batch')
        or item.get('numero_lote')
        or item.get('codigo_lote')
        or item.get('idLote')
        or item.get('id_lote')
        or ''
    )
    fecha_vencimiento = _parse_date(
        item.get('fecha_vencimiento')
        or item.get('vencimiento')
        or item.get('expiry_date')
        or item.get('fecha_expiracion')
        or item.get('fecVtoLote')
        or item.get('fec_vto_lote')
    )
    if not lote:
        lote_parts = [
            _norm(item.get('idAlmacen') or item.get('id_almacen') or item.get('almacen') or item.get('warehouse') or ''),
            _norm(item.get('idArticulo') or item.get('id_articulo') or item.get('codigo_articulo') or item.get('codigo') or item.get('sku') or ''),
            fecha_vencimiento.isoformat() if fecha_vencimiento else _norm(item.get('fecVtoLote') or item.get('fecha_vencimiento') or ''),
        ]
        lote = '|'.join(part for part in lote_parts if part) or _norm(item.get('idArticulo') or item.get('codigo') or 'SIN_LOTE')
    dias = _as_int(
        item.get('dias_frescura_restantes')
        or item.get('dias_restantes')
        or item.get('days_remaining')
        or item.get('dias')
    )
    if dias is None and fecha_vencimiento is not None:
        dias = (fecha_vencimiento - date.today()).days
    estado = _norm(item.get('estado_frescura') or item.get('estado') or '').upper()
    if not estado:
        estado = _estado_from_days(dias)
    elif estado not in {'CRITICO', 'ALERTA', 'OK', 'SIN_FECHA'}:
        estado = _estado_from_days(dias)
    sucursal = _norm(
        sucursal_id
        or item.get('sucursal_id')
        or item.get('sucursal')
        or item.get('branch')
        or item.get('deposito')
        or item.get('planta')
        or 'SIN_SUCURSAL'
    )
    codigo = _norm(item.get('codigo_articulo') or item.get('idArticulo') or item.get('id_articulo') or item.get('codigo') or item.get('sku'))
    descripcion = _norm(item.get('descripcion_articulo') or item.get('dsArticulo') or item.get('descripcion') or item.get('nombre_articulo'))
    marca = _norm(item.get('marca') or item.get('brand'))
    familia = _norm(item.get('familia') or item.get('family'))
    categoria = _norm(item.get('categoria') or item.get('division') or item.get('category'))
    unidad_medida = _norm(item.get('unidad_medida') or item.get('uom') or item.get('unidad') or item.get('dsUnidad'))
    _raw_unidades = (
        item.get('cantUnidades') or item.get('cant_unidades')
        or item.get('cantidad_unidades') or item.get('stock_unidades')
    )
    _raw_bultos = (
        item.get('cantBultos') or item.get('cant_bultos') or item.get('stock_bultos')
    )
    stock_unidades_val = _as_float(_raw_unidades) if _raw_unidades not in (None, '') else None
    stock_bultos_val   = _as_float(_raw_bultos)   if _raw_bultos   not in (None, '') else None
    stock_actual = (
        stock_unidades_val if stock_unidades_val is not None
        else stock_bultos_val if stock_bultos_val is not None
        else _as_float(item.get('stock_actual') or item.get('stock') or item.get('existencia') or 0)
    )
    origen = _norm(item.get('origen_dato') or item.get('source') or origen_dato or 'erp_chess_stock')
    payload = _build_frescura_payload_metadata(
        item,
        deposito_id=deposito_id or _norm(item.get('idDeposito') or item.get('deposito') or ''),
        sucursal_id=sucursal,
        fecha_stock=fecha_stock or _norm(item.get('fechaStock') or item.get('fecha') or ''),
        origen_dato=origen,
    )
    return {
        'sucursal_id': sucursal or 'SIN_SUCURSAL',
        'codigo_articulo': codigo,
        'descripcion_articulo': descripcion or None,
        'marca': marca or None,
        'familia': familia or None,
        'categoria': categoria or None,
        'lote': lote,
        'stock_actual': stock_actual,
        'stock_unidades': stock_unidades_val,
        'stock_bultos': stock_bultos_val,
        'unidad_medida': unidad_medida or None,
        'fecha_vencimiento': fecha_vencimiento,
        'dias_frescura_restantes': dias,
        'estado_frescura': estado,
        'origen_dato': origen,
        'payload_json': payload,
    }


def _fetch_frescura_payload_legacy(settings: dict[str, Any]) -> dict[str, Any]:
    base_url = settings['base_url']
    token = settings['token']
    timeout = settings['timeout']
    path = settings['path']
    if not token:
        raise FrescuraApiError('FRESCURA_API_TOKEN no configurada para el modo legacy.', 503)
    url = urljoin(base_url.rstrip('/') + '/', path.lstrip('/'))
    try:
        response = requests.get(
            url,
            headers={
                'Authorization': f'Bearer {token}',
                'X-API-Key': token,
                'Accept': 'application/json',
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise FrescuraApiError(f'No se pudo conectar con la API de frescura: {exc}', 503) from exc

    if response.status_code == 401:
        raise FrescuraApiError('API de frescura rechazo la autenticacion.', 401)
    if response.status_code >= 400:
        try:
            detail = response.json().get('error') or response.text
        except Exception:
            detail = response.text
        raise FrescuraApiError(f'API de frescura error {response.status_code}: {detail}', response.status_code)

    try:
        return response.json()
    except ValueError as exc:
        raise FrescuraApiError('La API de frescura no devolvio JSON valido.', 502) from exc


def get_last_sync() -> dict[str, Any] | None:
    _ensure_tables()
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT id, started_at, finished_at, estado, source_url, total_items, saved_rows, error_message
            FROM frescura_sync_log
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        return dict(row) if row else None


def sync_frescura_from_api() -> dict[str, Any]:
    _ensure_tables()
    settings = _frescura_api_settings()
    base_url = settings['base_url']
    timeout = settings['timeout']
    user = settings['user']
    password = settings['password']
    token = settings['token']
    deposits = [str(value) for value in settings['deposits'] if _norm(value)]
    deposit_map = {str(k): str(v) for k, v in settings['deposit_map'].items() if _norm(k) and _norm(v)}
    mode = 'erp' if user and password else 'legacy' if token else None
    if mode is None:
        raise FrescuraApiError(
            'Configura FRESCURA_API_USER y FRESCURA_API_PASSWORD para el ERP o FRESCURA_API_TOKEN para el modo legacy.',
            503,
        )

    source_url = urljoin(base_url.rstrip('/') + '/', 'stock/' if mode == 'erp' else settings['path'].lstrip('/'))
    log_id: int | None = None
    items: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    try:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO frescura_sync_log (estado, source_url, payload_json)
                    VALUES ('running', %(source_url)s, %(payload_json)s)
                    RETURNING id
                    """,
                    {
                        'source_url': source_url,
                        'payload_json': psycopg2.extras.Json({
                            'mode': mode,
                            'source_url': source_url,
                            'deposits': deposits,
                        }),
                    },
                )
                row = cur.fetchone()
                log_id = int(row[0]) if row else None

        if mode == 'erp':
            session_id = _frescura_login(base_url, user, password, timeout)
            fecha_stock = date.today()
            for deposito in deposits:
                raw_payload = _frescura_fetch_stock(base_url, session_id, deposito, timeout, fecha_stock=fecha_stock)
                for item in _extract_frescura_stock_items(raw_payload):
                    items.append(
                        _build_frescura_payload_metadata(
                            item,
                            deposito_id=deposito,
                            sucursal_id=_map_frescura_deposito_to_sucursal(deposito, deposit_map),
                            fecha_stock=fecha_stock.strftime('%d-%m-%Y'),
                            origen_dato='erp_chess_stock',
                        )
                    )
        else:
            payload = _fetch_frescura_payload_legacy(settings)
            raw_items = _filter_payload_items(payload)
            flattened: list[dict[str, Any]] = []
            for item in raw_items:
                if isinstance(item.get('lotes'), list):
                    for lote in item['lotes']:
                        if isinstance(lote, dict):
                            merged = {**item, **lote}
                            flattened.append(merged)
                else:
                    flattened.append(item)
            items = flattened or raw_items

        normalized = [
            row
            for row in (
                _normalize_api_row(
                    item,
                    sucursal_id=item.get('sucursal_id'),
                    deposito_id=_norm(item.get('idDeposito') or item.get('deposito') or ''),
                    fecha_stock=_norm(item.get('fechaStock') or ''),
                    origen_dato=_norm(item.get('origen_dato') or ('erp_chess_stock' if mode == 'erp' else 'api')),
                )
                for item in items
            )
            if row['codigo_articulo']
        ]

        cleanup_ids = sorted(
            {str(dep) for dep in deposits}
            | {_map_frescura_deposito_to_sucursal(dep, deposit_map) for dep in deposits}
        )

        with pg_conn() as conn:
            with conn.cursor() as cur:
                if mode == 'erp' and cleanup_ids:
                    cur.execute(
                        """
                        DELETE FROM frescura_articulos
                         WHERE sucursal_id = ANY(%(sucursales)s)
                        """,
                        {'sucursales': cleanup_ids},
                    )
                if normalized:
                    psycopg2.extras.execute_values(
                        cur,
                        """
                        INSERT INTO frescura_articulos (
                            sucursal_id, codigo_articulo, descripcion_articulo, marca, familia, categoria,
                            lote, stock_actual, unidad_medida,
                            fecha_vencimiento, dias_frescura_restantes,
                            estado_frescura, fecha_actualizacion, origen_dato, payload_json,
                            stock_unidades, stock_bultos, created_at, updated_at
                        ) VALUES %s
                        ON CONFLICT (sucursal_id, codigo_articulo, lote) DO UPDATE SET
                            descripcion_articulo = EXCLUDED.descripcion_articulo,
                            marca = EXCLUDED.marca,
                            familia = EXCLUDED.familia,
                            categoria = EXCLUDED.categoria,
                            stock_actual = EXCLUDED.stock_actual,
                            stock_unidades = EXCLUDED.stock_unidades,
                            stock_bultos = EXCLUDED.stock_bultos,
                            unidad_medida = EXCLUDED.unidad_medida,
                            fecha_vencimiento = EXCLUDED.fecha_vencimiento,
                            dias_frescura_restantes = EXCLUDED.dias_frescura_restantes,
                            estado_frescura = EXCLUDED.estado_frescura,
                            fecha_actualizacion = EXCLUDED.fecha_actualizacion,
                            origen_dato = EXCLUDED.origen_dato,
                            payload_json = EXCLUDED.payload_json,
                            updated_at = NOW()
                        """,
                        [
                            (
                                row['sucursal_id'],
                                row['codigo_articulo'],
                                row['descripcion_articulo'],
                                row['marca'],
                                row['familia'],
                                row['categoria'],
                                row['lote'],
                                row['stock_actual'],
                                row['unidad_medida'],
                                row['fecha_vencimiento'],
                                row['dias_frescura_restantes'],
                                row['estado_frescura'],
                                _utc_now_naive(),
                                row['origen_dato'],
                                psycopg2.extras.Json(row['payload_json']),
                                row.get('stock_unidades'),
                                row.get('stock_bultos'),
                                _utc_now_naive(),
                                _utc_now_naive(),
                            )
                            for row in normalized
                        ],
                    )
                saved_rows = len(normalized)
                cur.execute(
                    """
                    UPDATE frescura_sync_log
                       SET finished_at = NOW(),
                           estado = 'ok',
                           total_items = %(total_items)s,
                           saved_rows = %(saved_rows)s,
                           payload_json = %(payload_json)s,
                           error_message = NULL
                     WHERE id = %(id)s
                    """,
                    {
                        'id': log_id,
                        'total_items': len(items),
                        'saved_rows': saved_rows,
                        'payload_json': psycopg2.extras.Json({
                            'source_url': source_url,
                            'items': len(items),
                            'saved_rows': saved_rows,
                            'mode': mode,
                            'deposits': deposits,
                            'branch_ids': cleanup_ids,
                        }),
                    },
                )

        return {
            'ok': True,
            'source_url': source_url,
            'total_items': len(items),
            'saved_rows': len(normalized),
            'mode': mode,
            'deposits': deposits,
            'log_id': log_id,
            'last_sync': get_last_sync(),
        }
    except FrescuraApiError as exc:
        if log_id is not None:
            with pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE frescura_sync_log
                           SET finished_at = NOW(),
                               estado = 'error',
                               error_message = %(err)s,
                               payload_json = %(payload_json)s
                         WHERE id = %(id)s
                        """,
                        {
                            'id': log_id,
                            'err': str(exc),
                            'payload_json': psycopg2.extras.Json({'source_url': source_url, 'error': str(exc), 'mode': mode}),
                        },
                    )
        raise
    except Exception as exc:
        if log_id is not None:
            with pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE frescura_sync_log
                           SET finished_at = NOW(),
                               estado = 'error',
                               error_message = %(err)s,
                               payload_json = %(payload_json)s
                         WHERE id = %(id)s
                        """,
                        {
                            'id': log_id,
                            'err': str(exc),
                            'payload_json': psycopg2.extras.Json({'source_url': source_url, 'error': str(exc), 'mode': mode}),
                        },
                    )
        raise


def list_articulos(**filters: Any) -> dict[str, Any]:
    _ensure_tables()
    normalized = _clean_filters(filters)
    clients = _client_rows(normalized)
    commercial_filter_active = any(normalized.get(key) for key in ('cluster', 'vendedor', 'localidad'))
    if commercial_filter_active and not clients:
        return {
            'items': [],
            'resumen': {
                'articulos': 0,
                'criticos': 0,
                'alertas': 0,
                'ok': 0,
                'sin_fecha': 0,
                'stock_total': 0,
                'cobertura_promedio': 0.0,
                'potencial_total': 0,
            },
            'filtros_disponibles': {
                'sucursales': [],
                'estados': [],
                'marcas': [],
                'categorias': [],
                'clusters': [],
                'vendedores': _vendor_options(normalized),
                'localidades': [],
            },
            'last_sync': get_last_sync(),
        }
    row_filters = dict(normalized)
    if commercial_filter_active and normalized.get('sucursal') == 'TODAS':
        filtered_branches = sorted({str(client.get('sucursal') or '') for client in clients if _norm(client.get('sucursal'))})
        if len(filtered_branches) == 1:
            row_filters['sucursal'] = filtered_branches[0]

    rows = _freshness_rows(row_filters)
    if not rows:
        return {
            'items': [],
            'resumen': {
                'articulos': 0,
                'criticos': 0,
                'alertas': 0,
                'ok': 0,
                'stock_total': 0,
                'cobertura_promedio': 0.0,
                'potencial_total': 0,
            },
            'filtros_disponibles': {
                'sucursales': [],
                'estados': [],
                'marcas': [],
                'categorias': [],
                'clusters': [],
                'vendedores': [],
                'localidades': [],
            },
            'last_sync': get_last_sync(),
    }

    items = [_build_article_stock_summary(article) for article in rows]
    codes = [str(item.get('codigo_articulo') or '').strip() for item in items if _norm(item.get('codigo_articulo'))]
    active_by_branch: dict[str, int] = defaultdict(int)
    good_by_branch: dict[str, int] = defaultdict(int)
    for client in clients:
        branch = str(client.get('sucursal') or '1')
        active_by_branch[branch] += 1
        if _norm(client.get('cluster_dpo')) in _GOOD_CLUSTERS and _as_float(client.get('score_total'), 0.0) >= 65:
            good_by_branch[branch] += 1
    sales_summary = _article_sales_summary(codes, normalized)
    for item in items:
        branch = str(item.get('sucursal_id') or '1')
        code = str(item.get('codigo_articulo') or '')
        summary = sales_summary.get((branch, code), {})
        active_total = active_by_branch.get(branch, 0)
        buyers = int(summary.get('compradores') or 0)
        buyers_30 = int(summary.get('compradores_30') or 0)
        buyers_60 = int(summary.get('compradores_60') or 0)
        buyers_90 = int(summary.get('compradores_90') or 0)
        buyers_config = int(summary.get('compradores_config') or 0)
        good_buyers = int(summary.get('compradores_good') or 0)
        coverage = round((buyers_config / active_total * 100), 2) if active_total else 0.0
        potential = max(0, good_by_branch.get(branch, 0) - good_buyers)
        item.update({
            'clientes_activos_total': active_total,
            'clientes_que_compraron_alguna_vez': buyers,
            'clientes_ultimos_30_dias': buyers_30,
            'clientes_ultimos_60_dias': buyers_60,
            'clientes_ultimos_90_dias': buyers_90,
            'clientes_ultimos_config_dias': buyers_config,
            'clientes_inactivos_para_el_sku': max(0, buyers - buyers_config),
            'clientes_que_nunca_compraron': max(0, active_total - buyers),
            'cobertura_comercial_porcentaje': coverage,
            'potencial_clientes': potential,
            'dias_cobertura': normalized.get('dias_cobertura', 90),
        })
        if _norm(item.get('estado_frescura')) not in {'CRITICO', 'ALERTA'}:
            if active_total and coverage < 50:
                item['prioridad_nivel'] = min(int(item.get('prioridad_nivel') or 4), 2)
                item['prioridad_accion'] = _priority_label(int(item['prioridad_nivel']))
                item['accion_sugerida'] = 'Activar cobertura comercial'
            elif active_total and coverage < 80:
                item['prioridad_nivel'] = min(int(item.get('prioridad_nivel') or 4), 3)
                item['prioridad_accion'] = _priority_label(int(item['prioridad_nivel']))
                item['accion_sugerida'] = 'Sostener rotacion con cartera activa'

    if normalized['articulo']:
        q = _lower(normalized['articulo'])
        items = [
            item for item in items
            if q in _lower(item.get('codigo_articulo')) or q in _lower(item.get('descripcion_articulo'))
        ]

    if normalized['estado']:
        wanted = {e.strip().upper() for e in re.split(r'[,\s;|]+', normalized['estado']) if e.strip()}
        items = [item for item in items if _norm(item.get('estado_frescura')).upper() in wanted]

    items = sorted(
        items,
        key=lambda r: (
            r.get('prioridad_nivel', 4),
            _as_float(r.get('dias_frescura_restantes'), 9999),
            _as_float(r.get('stock_actual'), 0),
            str(r.get('codigo_articulo') or ''),
        ),
    )

    stock_total = round(sum(_as_float(item.get('stock_actual'), 0.0) for item in items), 2)
    cobertura_values = [float(item.get('cobertura_comercial_porcentaje') or 0) for item in items if item.get('clientes_activos_total')]
    resumen = {
        'articulos': len(items),
        'criticos': sum(1 for item in items if _norm(item.get('estado_frescura')) == 'CRITICO'),
        'alertas': sum(1 for item in items if _norm(item.get('estado_frescura')) == 'ALERTA'),
        'ok': sum(1 for item in items if _norm(item.get('estado_frescura')) == 'OK'),
        'sin_fecha': sum(1 for item in items if _norm(item.get('estado_frescura')) == 'SIN_FECHA'),
        'stock_total': stock_total,
        'cobertura_promedio': round(sum(cobertura_values) / len(cobertura_values), 2) if cobertura_values else 0.0,
        'potencial_total': sum(int(item.get('potencial_clientes') or 0) for item in items),
    }

    filter_options = {
        'sucursales': sorted(
            {
                (str(item.get('sucursal_id') or ''), str(item.get('sucursal_nombre') or item.get('sucursal_id') or ''))
                for item in items
            },
            key=lambda x: x[1],
        ),
        'estados': sorted({str(item.get('estado_frescura') or 'SIN_FECHA') for item in items}),
        'marcas': sorted({str(item.get('marca') or '') for item in items if _norm(item.get('marca'))}),
        'categorias': sorted({str(item.get('categoria') or '') for item in items if _norm(item.get('categoria'))}),
        'clusters': sorted({str(item.get('cluster_dpo') or '') for item in clients if _norm(item.get('cluster_dpo'))}),
        'vendedores': _vendor_options(normalized),
        'localidades': sorted({str(item.get('localidad') or '') for item in clients if _norm(item.get('localidad'))}),
    }

    return {
        'items': items,
        'resumen': resumen,
        'filtros_disponibles': filter_options,
        'last_sync': get_last_sync(),
    }


def get_articulo_resumen(codigo_articulo: str, sucursal: str | None = None, **filters: Any) -> dict[str, Any]:
    payload = get_articulo_clientes(codigo_articulo, sucursal=sucursal, **filters)
    if not payload.get('articulo'):
        return {'articulo': None, 'resumen': None, 'clientes': {}, 'oportunidades': []}
    return {
        'articulo': payload['articulo'],
        'resumen': payload['resumen'],
        'clientes': payload['clientes'],
        'oportunidades': payload['oportunidades'][:80],
        'last_sync': payload.get('last_sync'),
    }


def get_articulo_clientes(codigo_articulo: str, sucursal: str | None = None, **filters: Any) -> dict[str, Any]:
    _ensure_tables()
    dias_cobertura = max(7, min(365, int(filters.get('dias_cobertura') or get_config().get('dias_cobertura', 90))))
    context = _article_context(codigo_articulo, sucursal=sucursal, filters=filters)
    article = context['articulo']
    if not article:
        return {
            'articulo': None,
            'resumen': None,
            'clientes': {
                'compradores_recientes': [],
                'compradores_inactivos': [],
                'compradores_categoria_no_sku': [],
                'nunca_compraron': [],
                'recomendados': [],
            },
            'oportunidades': [],
        }

    active_clients = context['clientes']
    facts = context['facts']
    cat_match = context['category_match']
    active_keys = {(str(c.get('cliente') or ''), str(c.get('sucursal') or '')) for c in active_clients}
    stock_bultos = _as_float(article.get('stock_bultos_total'), 0.0) or _as_float(article.get('stock_bultos'), 0.0) or _as_float(article.get('stock_actual'), 0.0)

    fact_map: dict[tuple[str, str], dict[str, Any]] = {}
    for fact in facts:
        key = (str(fact.get('cliente_id') or ''), str(fact.get('sucursal_id') or ''))
        if key not in active_keys:
            continue
        prev = fact_map.get(key)
        if not prev or (fact.get('ultima_venta') and fact['ultima_venta'] > prev.get('ultima_venta')):
            fact_map[key] = fact

    recent: list[dict[str, Any]] = []
    inactive: list[dict[str, Any]] = []
    category_no_sku: list[dict[str, Any]] = []
    never: list[dict[str, Any]] = []
    recommended: list[dict[str, Any]] = []
    opportunities: list[dict[str, Any]] = []
    summary = {
        'clientes_activos_total': len(active_clients),
        'clientes_que_compraron_alguna_vez': len(fact_map),
        'clientes_ultimos_30_dias': 0,
        'clientes_ultimos_60_dias': 0,
        'clientes_ultimos_90_dias': 0,
        'clientes_ultimos_config_dias': 0,
        'dias_cobertura': dias_cobertura,
        'clientes_inactivos_para_el_sku': 0,
        'clientes_que_nunca_compraron': 0,
        'clientes_categoria_marca_sin_sku': 0,
        'cobertura_comercial_porcentaje': 0.0,
        'potencial_clientes': 0,
    }

    today = date.today()
    buyers = set(fact_map)
    for client in active_clients:
        key = (str(client.get('cliente') or ''), str(client.get('sucursal') or ''))
        fact = fact_map.get(key)
        category = key in cat_match and not fact
        payload = _client_payload_from_fact(client, fact, category)
        opportunities.append(payload)
        if fact:
            dias = payload['dias_desde_ultima_venta']
            if dias is not None and dias <= 30:
                summary['clientes_ultimos_30_dias'] += 1
            if dias is not None and dias <= 60:
                summary['clientes_ultimos_60_dias'] += 1
            if dias is not None and dias <= 90:
                summary['clientes_ultimos_90_dias'] += 1
            if dias is not None and dias <= dias_cobertura:
                summary['clientes_ultimos_config_dias'] += 1
                recent.append(payload)
            else:
                inactive.append(payload)
        else:
            never.append(payload)
            if category:
                category_no_sku.append(payload)
        if payload['prioridad_nivel'] <= 3 and payload['score_oportunidad'] >= 45:
            recommended.append(payload)

    summary['clientes_inactivos_para_el_sku'] = len(inactive)
    summary['clientes_que_nunca_compraron'] = len(never)
    summary['clientes_categoria_marca_sin_sku'] = len(category_no_sku)
    summary['cobertura_comercial_porcentaje'] = round((summary['clientes_ultimos_config_dias'] / len(active_clients) * 100), 2) if active_clients else 0.0
    summary['potencial_clientes'] = len([c for c in active_clients if _norm(c.get('cluster_dpo')) in _GOOD_CLUSTERS and _as_float(c.get('score_total'), 0.0) >= 65 and (str(c.get('cliente') or ''), str(c.get('sucursal') or '')) not in buyers])
    summary.update(_sales_metrics_from_facts(list(fact_map.values()), stock_bultos))

    opportunities = sorted(
        opportunities,
        key=lambda x: (
            x['prioridad_nivel'],
            -float(x['score_oportunidad']),
            x['dias_desde_ultima_venta'] if x['dias_desde_ultima_venta'] is not None else 99999,
            str(x['cliente'] or ''),
        ),
    )
    recommended = sorted(
        recommended,
        key=lambda x: (
            x['prioridad_nivel'],
            -float(x['score_oportunidad']),
            x['dias_desde_ultima_venta'] if x['dias_desde_ultima_venta'] is not None else 99999,
            str(x['cliente'] or ''),
        ),
    )[:50]

    never_sorted = sorted(never, key=lambda x: -float(x.get('score_oportunidad') or 0))
    return {
        'articulo': _build_article_stock_summary(article),
        'resumen': summary,
        'clientes': {
            'compradores_recientes': recent,
            'compradores_inactivos': inactive,
            'compradores_categoria_no_sku': category_no_sku,
            'nunca_compraron': never_sorted[:100],
            'nunca_compraron_total': len(never),
            'recomendados': recommended,
        },
        'oportunidades': opportunities[:150],
        'last_sync': get_last_sync(),
    }


def get_articulo_oportunidades(codigo_articulo: str, sucursal: str | None = None, limit: int = 50, **filters: Any) -> list[dict[str, Any]]:
    payload = get_articulo_clientes(codigo_articulo, sucursal=sucursal, **filters)
    return payload.get('oportunidades', [])[: max(1, min(int(limit or 50), 250))]


def guardar_plan_accion(codigo_articulo: str, sucursal: str | None = None, data: dict[str, Any] | None = None) -> dict[str, Any]:
    _ensure_tables()
    data = data or {}
    resumen = get_articulo_resumen(codigo_articulo, sucursal=sucursal)
    oportunidades = get_articulo_oportunidades(codigo_articulo, sucursal=sucursal, limit=20)
    titulo = _norm(data.get('titulo') or f'Plan de accion {codigo_articulo}')[:180]
    created_by = _norm(data.get('creado_por') or data.get('usuario') or '')
    plan_json = {
        'codigo_articulo': codigo_articulo,
        'sucursal_id': sucursal,
        'resumen': resumen,
        'oportunidades_top': oportunidades,
        'objetivo': _norm(data.get('objetivo') or ''),
        'notas': _norm(data.get('notas') or ''),
        'prioridad': _norm(data.get('prioridad') or ''),
        'responsable': _norm(data.get('responsable') or ''),
        'plazo_dias': _as_int(data.get('plazo_dias')),
    }
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO frescura_planes_accion (
                    codigo_articulo, sucursal_id, titulo, resumen_json, plan_json, creado_por, created_at, updated_at
                )
                VALUES (%(codigo_articulo)s, %(sucursal_id)s, %(titulo)s, %(resumen_json)s, %(plan_json)s, %(creado_por)s, NOW(), NOW())
                RETURNING id, created_at
                """,
                {
                    'codigo_articulo': codigo_articulo,
                    'sucursal_id': sucursal,
                    'titulo': titulo,
                    'resumen_json': psycopg2.extras.Json(resumen),
                    'plan_json': psycopg2.extras.Json(plan_json),
                    'creado_por': created_by or None,
                },
            )
            row = cur.fetchone() or {}
    return {
        'id': row.get('id'),
        'codigo_articulo': codigo_articulo,
        'sucursal_id': sucursal,
        'titulo': titulo,
        'created_at': row.get('created_at').isoformat() if isinstance(row.get('created_at'), datetime) else None,
        'resumen': resumen,
        'oportunidades_top': oportunidades,
        'plan': plan_json,
    }


def list_errores_stock(sucursal: str | None = None) -> dict[str, Any]:
    _ensure_tables()
    params: dict[str, Any] = {}
    suc_filter = ''
    if sucursal and sucursal != 'TODAS':
        suc_filter = 'AND fa.sucursal_id = %(sucursal)s'
        params['sucursal'] = sucursal
    with pg_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                fa.sucursal_id,
                COALESCE(NULLIF(TRIM(suc.nombre), ''), fa.sucursal_id) AS sucursal_nombre,
                fa.codigo_articulo,
                COALESCE(NULLIF(TRIM(fa.descripcion_articulo), ''), fa.codigo_articulo) AS descripcion_articulo,
                COALESCE(NULLIF(TRIM(fa.marca), ''), '') AS marca,
                COALESCE(NULLIF(TRIM(fa.categoria), ''), '') AS categoria,
                COALESCE(NULLIF(TRIM(fa.lote), ''), 'SIN_LOTE') AS lote,
                fa.stock_actual,
                fa.unidad_medida,
                fa.fecha_vencimiento,
                fa.dias_frescura_restantes,
                COALESCE(fa.estado_frescura, 'SIN_FECHA') AS estado_frescura,
                fa.fecha_actualizacion
            FROM frescura_articulos fa
            LEFT JOIN sucursales suc ON suc.id = fa.sucursal_id
            WHERE fa.stock_actual < 0
              {suc_filter}
            ORDER BY fa.stock_actual ASC, fa.sucursal_id, fa.codigo_articulo, fa.lote
            """,
            params,
        )
        rows = [dict(r) for r in cur.fetchall() or []]
    for row in rows:
        fv = row.get('fecha_vencimiento')
        if isinstance(fv, date) and not isinstance(fv, datetime):
            row['fecha_vencimiento'] = fv.isoformat()
        fa = row.get('fecha_actualizacion')
        if isinstance(fa, datetime):
            row['fecha_actualizacion'] = fa.isoformat()
    sucursales = sorted({str(r.get('sucursal_id') or '') for r in rows if _norm(r.get('sucursal_id'))})
    return {
        'items': rows,
        'total': len(rows),
        'sucursales': sucursales,
        'last_sync': get_last_sync(),
    }


def list_sucursales_disponibles() -> list[dict[str, str]]:
    labels = _sucursal_map()
    return [{'value': key, 'label': value} for key, value in sorted(labels.items(), key=lambda x: x[1])]
