-- Dropsize - tablas e indices PostgreSQL
-- Base de calculo: ventas_detalle + articulos.

CREATE TABLE IF NOT EXISTS dropsize_objetivos (
    id BIGSERIAL PRIMARY KEY,
    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50),
    unidad VARCHAR(20) NOT NULL CHECK (unidad IN ('bultos', 'hl', 'pallets')),
    objetivo_minimo NUMERIC(14,4) NOT NULL,
    objetivo_ideal NUMERIC(14,4) NOT NULL,
    fecha_desde DATE NOT NULL,
    fecha_hasta DATE,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dropsize_obj_suc_unidad
    ON dropsize_objetivos(sucursal_id, unidad, activo);

CREATE INDEX IF NOT EXISTS idx_dropsize_obj_fechas
    ON dropsize_objetivos(fecha_desde, fecha_hasta);

CREATE TABLE IF NOT EXISTS dropsize_historico (
    id BIGSERIAL PRIMARY KEY,
    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50) NOT NULL,
    fecha DATE NOT NULL,
    periodo_mes SMALLINT NOT NULL,
    periodo_anio SMALLINT NOT NULL,
    clientes_entregados INTEGER NOT NULL DEFAULT 0,
    total_bultos NUMERIC(18,4) NOT NULL DEFAULT 0,
    total_hl NUMERIC(18,4) NOT NULL DEFAULT 0,
    total_pallets NUMERIC(18,4) NOT NULL DEFAULT 0,
    dropsize_bultos NUMERIC(18,4) NOT NULL DEFAULT 0,
    dropsize_hl NUMERIC(18,4) NOT NULL DEFAULT 0,
    dropsize_pallets NUMERIC(18,4) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, sucursal_id, fecha)
);

CREATE INDEX IF NOT EXISTS idx_dropsize_hist_fecha
    ON dropsize_historico(fecha);

CREATE INDEX IF NOT EXISTS idx_dropsize_hist_suc_fecha
    ON dropsize_historico(sucursal_id, fecha);

CREATE INDEX IF NOT EXISTS idx_dropsize_hist_empresa
    ON dropsize_historico(empresa_id);

CREATE INDEX IF NOT EXISTS idx_ventas_detalle_empresa
    ON ventas_detalle(empresa);

CREATE INDEX IF NOT EXISTS idx_ventas_detalle_cliente
    ON ventas_detalle(cliente);

CREATE INDEX IF NOT EXISTS idx_ventas_detalle_suc_fecha_cliente
    ON ventas_detalle(sucursal, fecha, cliente);

-- Consulta base de calculo diario.
-- Reemplazar :fecha_desde, :fecha_hasta y :sucursal segun el driver SQL usado.
SELECT
    v.fecha::date AS fecha,
    COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') AS sucursal_id,
    COUNT(DISTINCT v.fecha::text || '|' || COALESCE(NULLIF(TRIM(v.cliente), ''), NULLIF(TRIM(v.descripcion_cliente), ''), v.id::text)) AS clientes_entregados,
    COALESCE(SUM(COALESCE(v.bultos, 0)), 0) AS total_bultos,
    COALESCE(SUM(COALESCE(v.unidad_medida, 0)), 0) AS total_hl,
    COALESCE(SUM(CASE WHEN COALESCE(a.bultos_por_pallet, 0) > 0 THEN COALESCE(v.bultos, 0) / a.bultos_por_pallet ELSE 0 END), 0) AS total_pallets
FROM ventas_detalle v
LEFT JOIN articulos a ON v.id_articulo = a.id_articulo
WHERE v.fecha BETWEEN :fecha_desde AND :fecha_hasta
  AND (:sucursal = 'TODAS' OR COALESCE(NULLIF(TRIM(v.sucursal), ''), '1') = :sucursal)
  AND LOWER(TRIM(COALESCE(v.documento, ''))) NOT LIKE 'remit%'
  AND LOWER(TRIM(COALESCE(v.documento, ''))) NOT LIKE 'comod%'
  AND LOWER(TRIM(COALESCE(v.detalle_documento, ''))) NOT LIKE 'remit%'
  AND LOWER(TRIM(COALESCE(v.detalle_documento, ''))) NOT LIKE 'comod%'
  AND LOWER(TRIM(COALESCE(a.tipo_producto, ''))) = 'mercaderia'
GROUP BY v.fecha::date, COALESCE(NULLIF(TRIM(v.sucursal), ''), '1');
