from __future__ import annotations

from app.database import pg_cursor
PROTECTED_TABLES = {
    'ventas_detalle',
    'articulos',
    'rechazos',
    'feriados',
    'eventos_especiales',
    'sucursales',
    'parametros',
    'seg_parametros',
    'seg_clientes_atributos',
    'seg_cliente_metricas_servicio_historico',
    'seg_periodos_calculo',
    'seg_score_pesos',
    'seg_cliente_cluster_historico',
    'seg_auditoria',
    'seg_schema_version',
    'cliente_geografia',
    'cliente_autoelevador',
    'dropsize_objetivos',
    'dropsize_historico',
}


MODULES = [
    {
        'id': 'admin',
        'nombre': 'Portal_Logistica',
        'url': '/dashboard',
        'api': '/api/admin-proyecto/dashboard',
        'health_api': '/api/admin-proyecto/dashboard',
        'estado': 'activo',
    },
    {
        'id': 'picos',
        'nombre': 'Dias pico',
        'url': '/dias-pico',
        'api': '/api/picos/kpis',
        'health_api': '/api/picos/kpis?mes={YYYY-MM}&sucursal=TODAS',
        'estado': 'activo',
    },
    {
        'id': 'segmentacion',
        'nombre': 'Segmentacion DPO',
        'url': '/segmentacion-clientes',
        'api': '/api/segmentacion/plan-servicio',
        'health_api': '/api/segmentacion/cache',
        'estado': 'activo',
    },
    {
        'id': 'dropsize',
        'nombre': 'Drop Size',
        'url': '/admin/dropsize',
        'api': '/api/dropsize/resumen',
        'health_api': '/api/dropsize/resumen',
        'estado': 'activo',
    },
    {
        'id': 'planificacion',
        'nombre': 'Planeamiento picos',
        'url': '/admin/planificacion_picos',
        'api': '/api/planificacion_picos/resumen',
        'health_api': '/api/planificacion_picos/variables',
        'estado': 'activo',
    },
    {
        'id': 'reporte',
        'nombre': 'Reporte picos',
        'url': '/reporte-picos',
        'api': '/api/picos/historico',
        'health_api': '/api/picos/historico?sucursal=TODAS&meses=6',
        'estado': 'activo',
    },
    {
        'id': 'articulos',
        'nombre': 'Articulos',
        'url': '/dias-pico',
        'api': '/api/articulos/count',
        'health_api': '/api/articulos/count',
        'estado': 'activo',
    },
    {
        'id': 'rechazos',
        'nombre': 'Rechazos',
        'url': '/dias-pico',
        'api': '/api/rechazos',
        'health_api': '/api/rechazos',
        'estado': 'activo',
    },
    {
        'id': 'parametros',
        'nombre': 'Parametros',
        'url': '/dias-pico',
        'api': '/api/parametros',
        'health_api': '/api/sucursales',
        'estado': 'activo',
    },
    {
        'id': 'feriados_eventos',
        'nombre': 'Feriados y eventos',
        'url': '/dias-pico',
        'api': '/api/feriados',
        'health_api': '/api/feriados',
        'estado': 'activo',
    },
    {
        'id': 'flota',
        'nombre': 'Flota',
        'url': '/dias-pico',
        'api': '/api/flota/vehiculos',
        'health_api': '/api/flota/vehiculos',
        'estado': 'activo',
    },
    {
        'id': 'catalogo',
        'nombre': 'Catalogo externo',
        'url': '/dias-pico',
        'api': '/api/catalogo/status',
        'health_api': '/api/catalogo/status',
        'estado': 'activo',
    },
    {
        'id': 'simulaciones',
        'nombre': 'Simulaciones',
        'url': '/dias-pico',
        'api': '/api/simulaciones',
        'health_api': '/api/simulaciones',
        'estado': 'activo',
    },
    {
        'id': 'sync',
        'nombre': 'Sync operativo',
        'url': '/dias-pico',
        'api': '/api/sync/operacion-camiones/anios',
        'health_api': '/api/sync/operacion-camiones/anios',
        'estado': 'activo',
    },
]


def _table_status(row: dict) -> str:
    table = row['table_name']
    rows = int(row.get('estimated_rows') or 0)
    total_bytes = int(row.get('total_bytes') or 0)
    scans = int(row.get('seq_scan') or 0) + int(row.get('idx_scan') or 0)
    dead = int(row.get('dead_rows') or 0)

    if table in PROTECTED_TABLES:
        return 'protegida'
    if rows == 0 and total_bytes < 1024 * 1024:
        return 'vacia'
    if scans == 0 and total_bytes < 10 * 1024 * 1024:
        return 'sin_uso_estadistico'
    if rows and dead / max(rows, 1) > 0.20:
        return 'requiere_mantenimiento'
    return 'activa'


_SQL_LIST_TABLES = """
    SELECT st.relname AS table_name,
           COALESCE(st.n_live_tup, 0)::BIGINT AS estimated_rows,
           COALESCE(st.n_dead_tup, 0)::BIGINT AS dead_rows,
           COALESCE(st.seq_scan, 0)::BIGINT AS seq_scan,
           COALESCE(st.idx_scan, 0)::BIGINT AS idx_scan,
           st.last_vacuum,
           st.last_autovacuum,
           st.last_analyze,
           st.last_autoanalyze,
           pg_total_relation_size(c.oid)::BIGINT AS total_bytes,
           pg_relation_size(c.oid)::BIGINT AS table_bytes,
           pg_indexes_size(c.oid)::BIGINT AS index_bytes,
           pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
           pg_size_pretty(pg_relation_size(c.oid)) AS table_size,
           pg_size_pretty(pg_indexes_size(c.oid)) AS index_size
    FROM pg_stat_user_tables st
    JOIN pg_class c ON c.oid = st.relid
    ORDER BY pg_total_relation_size(c.oid) DESC, st.relname
"""

_SQL_LIST_INDEXES = """
    SELECT s.relname AS table_name,
           s.indexrelname AS index_name,
           COALESCE(s.idx_scan, 0)::BIGINT AS idx_scan,
           COALESCE(s.idx_tup_read, 0)::BIGINT AS idx_tup_read,
           COALESCE(s.idx_tup_fetch, 0)::BIGINT AS idx_tup_fetch,
           pg_relation_size(s.indexrelid)::BIGINT AS index_bytes,
           pg_size_pretty(pg_relation_size(s.indexrelid)) AS index_size,
           ix.indisprimary AS is_primary,
           ix.indisunique AS is_unique,
           pi.indexdef
    FROM pg_stat_user_indexes s
    JOIN pg_index ix ON ix.indexrelid = s.indexrelid
    JOIN pg_class i ON i.oid = s.indexrelid
    JOIN pg_indexes pi ON pi.schemaname = s.schemaname
                    AND pi.tablename = s.relname
                    AND pi.indexname = s.indexrelname
    ORDER BY pg_relation_size(s.indexrelid) DESC, s.relname, s.indexrelname
"""

_SQL_DB_INFO = """
    SELECT current_database() AS database_name,
           pg_size_pretty(pg_database_size(current_database())) AS database_size,
           pg_database_size(current_database())::BIGINT AS database_bytes,
           version() AS postgres_version
"""


def _list_tables_from_cursor(cur) -> list[dict]:
    cur.execute(_SQL_LIST_TABLES)
    return _decorate_table_rows([dict(r) for r in cur.fetchall()])


def _list_indexes_from_cursor(cur) -> list[dict]:
    cur.execute(_SQL_LIST_INDEXES)
    rows = [dict(r) for r in cur.fetchall()]
    for row in rows:
        row['status'] = (
            'primario' if row['is_primary']
            else 'sin_uso_estadistico' if int(row['idx_scan'] or 0) == 0
            else 'activo'
        )
    return rows


def list_tables() -> list[dict]:
    with pg_cursor() as cur:
        return _list_tables_from_cursor(cur)


def _decorate_table_rows(rows: list[dict]) -> list[dict]:
    for row in rows:
        row['status'] = _table_status(row)
        row['protected'] = row['table_name'] in PROTECTED_TABLES
    return rows


def list_indexes() -> list[dict]:
    with pg_cursor() as cur:
        return _list_indexes_from_cursor(cur)


def cleanup_candidates() -> list[dict]:
    return _cleanup_candidates_from_tables(list_tables())


def _cleanup_candidates_from_tables(tables: list[dict]) -> list[dict]:
    candidates = []
    for row in tables:
        if row['protected'] or row['status'] == 'activa':
            continue
        table = row['table_name']
        candidates.append({
            **row,
            'review_sql': f'-- revisar dependencias antes\nDROP TABLE IF EXISTS {table};',
        })
    return candidates


def _segmentacion_cache_status_readonly() -> dict:
    with pg_cursor() as cur:
        return _segmentacion_cache_status_from_cursor(cur)


def _segmentacion_cache_status_from_cursor(cur) -> dict:
    cur.execute("""
        SELECT to_regclass('public.seg_cliente_dpo_cache') AS cache_regclass
    """)
    exists = bool((cur.fetchone() or {}).get('cache_regclass'))
    if not exists:
        return {'cache': 'seg_cliente_dpo_cache', 'populated': False, 'rows': 0, 'total_size': '0 bytes'}
    cur.execute("""
        SELECT COALESCE(c.reltuples, 0)::BIGINT AS estimated_rows,
               pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = 'seg_cliente_dpo_cache'
    """)
    cache = dict(cur.fetchone() or {})
    cur.execute("SELECT COUNT(*) AS rows FROM seg_cliente_dpo_cache")
    cache['rows'] = int((cur.fetchone() or {}).get('rows') or 0)
    cache['populated'] = cache['rows'] > 0
    cache['cache'] = 'seg_cliente_dpo_cache'
    cur.execute("""
        SELECT version, applied_at
        FROM seg_schema_version
        WHERE component = 'segmentacion_cache'
    """)
    meta = cur.fetchone()
    cache['last_refresh_at'] = meta['applied_at'] if meta else None
    cache['cache_version'] = meta['version'] if meta else None
    return cache


def overview() -> dict:
    with pg_cursor() as cur:
        tables = _list_tables_from_cursor(cur)
        indexes = _list_indexes_from_cursor(cur)
        cur.execute(_SQL_DB_INFO)
        db = dict(cur.fetchone() or {})
        cache = _segmentacion_cache_status_from_cursor(cur)

    candidates = _cleanup_candidates_from_tables(tables)
    total_rows = sum(int(t.get('estimated_rows') or 0) for t in tables)
    total_bytes = sum(int(t.get('total_bytes') or 0) for t in tables)
    dead_rows = sum(int(t.get('dead_rows') or 0) for t in tables)
    index_bytes = sum(int(t.get('index_bytes') or 0) for t in tables)

    return {
        'database': db,
        'totales': {
            'tablas': len(tables),
            'indices': len(indexes),
            'filas_estimadas': total_rows,
            'filas_muertas': dead_rows,
            'bytes_tablas': total_bytes,
            'bytes_indices': index_bytes,
            'candidatas_limpieza': len(candidates),
        },
        'modulos': MODULES,
        'tablas_top': tables[:12],
        'indices_top': indexes[:12],
        'candidatas_limpieza': candidates,
        'segmentacion_cache': cache,
    }


_SQL_DB_INFO_WITH_INDEX_COUNT = """
    SELECT current_database() AS database_name,
           pg_size_pretty(pg_database_size(current_database())) AS database_size,
           pg_database_size(current_database())::BIGINT AS database_bytes,
           version() AS postgres_version,
           (SELECT COUNT(*) FROM pg_stat_user_indexes)::INT AS index_count
"""


def dashboard_summary() -> dict:
    with pg_cursor() as cur:
        tables = _list_tables_from_cursor(cur)
        cur.execute(_SQL_DB_INFO_WITH_INDEX_COUNT)
        db = dict(cur.fetchone() or {})
        cache = _segmentacion_cache_status_from_cursor(cur)

    candidates = _cleanup_candidates_from_tables(tables)
    total_rows = sum(int(t.get('estimated_rows') or 0) for t in tables)
    total_bytes = sum(int(t.get('total_bytes') or 0) for t in tables)
    dead_rows = sum(int(t.get('dead_rows') or 0) for t in tables)
    index_bytes = sum(int(t.get('index_bytes') or 0) for t in tables)

    return {
        'database': db,
        'totales': {
            'tablas': len(tables),
            'indices': db.get('index_count', 0),
            'filas_estimadas': total_rows,
            'filas_muertas': dead_rows,
            'bytes_tablas': total_bytes,
            'bytes_indices': index_bytes,
            'candidatas_limpieza': len(candidates),
        },
        'modulos': MODULES,
        'tablas_top': tables[:8],
        'candidatas_limpieza': candidates[:8],
        'segmentacion_cache': cache,
    }
