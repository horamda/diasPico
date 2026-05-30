-- =============================================================
-- segmentacion_operaciones_costeo.sql
-- Frente: Operaciones y Costeo (autoelevador + costo operativo)
-- Requiere: vw_cliente_metricas, vw_cliente_cluster_dpo, vw_cliente_score
-- =============================================================

BEGIN;

-- -------------------------------------------------------------
-- 1) Tabla de clientes con autoelevador
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cliente_autoelevador (
    id BIGSERIAL PRIMARY KEY,
    is_cliente VARCHAR(100) NOT NULL,
    autoelevador BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_importacion TIMESTAMP NOT NULL DEFAULT NOW(),
    fuente VARCHAR(100) NOT NULL DEFAULT 'manual',
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_cliente_autoelevador_cliente UNIQUE (is_cliente),
    CONSTRAINT chk_cliente_autoelevador_cliente
        CHECK (NULLIF(BTRIM(is_cliente), '') IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_cliente_autoelevador_flag
    ON cliente_autoelevador(autoelevador);
CREATE INDEX IF NOT EXISTS idx_cliente_autoelevador_fecha
    ON cliente_autoelevador(fecha_importacion DESC);

-- -------------------------------------------------------------
-- 2) Importacion masiva robusta (COPY + UPSERT)
-- Uso en psql:
--   CREATE TEMP TABLE stg_cliente_autoelevador(is_cliente VARCHAR(100));
--   \copy stg_cliente_autoelevador(is_cliente)
--      FROM '/ruta/clientes_autoelevador.csv' WITH (FORMAT csv, HEADER true);
--   -- luego ejecutar el bloque INSERT ... ON CONFLICT de abajo.
-- -------------------------------------------------------------
CREATE TEMP TABLE IF NOT EXISTS stg_cliente_autoelevador (
    is_cliente VARCHAR(100)
) ON COMMIT DROP;

-- UPSERT desde staging
INSERT INTO cliente_autoelevador (
    is_cliente,
    autoelevador,
    fecha_importacion,
    fuente,
    updated_at
)
SELECT DISTINCT
    BTRIM(s.is_cliente) AS is_cliente,
    TRUE AS autoelevador,
    NOW() AS fecha_importacion,
    'csv' AS fuente,
    NOW() AS updated_at
FROM stg_cliente_autoelevador s
WHERE NULLIF(BTRIM(s.is_cliente), '') IS NOT NULL
ON CONFLICT (is_cliente) DO UPDATE
SET autoelevador = EXCLUDED.autoelevador,
    fecha_importacion = NOW(),
    fuente = EXCLUDED.fuente,
    updated_at = NOW();

-- -------------------------------------------------------------
-- 3) Vista unificada de autoelevador por cliente
-- Prioridad de fuente:
--   1) cliente_autoelevador (importacion externa)
--   2) seg_clientes_atributos.autoelevador
-- -------------------------------------------------------------
DROP VIEW IF EXISTS vw_cliente_autoelevador CASCADE;
CREATE VIEW vw_cliente_autoelevador AS
SELECT
    m.cliente AS cliente_id,
    m.descripcion_cliente AS cliente_nombre,
    m.sucursal,
    m.localidad,
    m.venta_ytd AS venta,
    m.hl_ytd AS hl,
    m.pallets_ytd AS pallets,
    m.bultos_ytd AS bultos,
    m.pedidos_ytd AS pedidos,
    COALESCE(ca.autoelevador, sa.autoelevador, FALSE) AS tiene_autoelevador,
    CASE
        WHEN COALESCE(ca.autoelevador, sa.autoelevador, FALSE) THEN 1
        ELSE 3
    END AS factor_operativo,
    CASE
        WHEN ca.is_cliente IS NOT NULL THEN 'importacion_externa'
        WHEN sa.cliente IS NOT NULL THEN 'atributo_segmentacion'
        ELSE 'sin_dato'
    END AS fuente_autoelevador
FROM vw_cliente_metricas m
LEFT JOIN cliente_autoelevador ca
    ON ca.is_cliente = m.cliente
LEFT JOIN seg_clientes_atributos sa
    ON sa.cliente = m.cliente
WHERE m.venta_ytd > 0 OR m.venta_anio_base > 0;

-- -------------------------------------------------------------
-- 4) Costo operativo diferencial + score operativo ajustado
-- Regla:
--   autoelevador = TRUE  -> factor_operativo = 1
--   autoelevador = FALSE -> factor_operativo = 3
--
-- costo_servir_ajustado:
--   hl * costo_entrega_hl * factor_operativo
--
-- score:
--   bonus +15 para autoelevador en productividad/total
-- -------------------------------------------------------------
DROP VIEW IF EXISTS vw_cliente_costo_operativo CASCADE;
CREATE VIEW vw_cliente_costo_operativo AS
SELECT
    m.cliente AS cliente_id,
    m.descripcion_cliente AS cliente_nombre,
    m.sucursal,
    m.localidad,
    a.tiene_autoelevador,
    a.factor_operativo,
    m.venta_ytd AS venta,
    m.hl_ytd AS hl,
    m.pedidos_ytd AS pedidos,
    m.costo_entrega,
    m.costo_almacen,
    ROUND((m.costo_entrega * a.factor_operativo)::NUMERIC, 2) AS costo_servir_ajustado,
    ROUND((m.costo_entrega * a.factor_operativo + m.costo_almacen)::NUMERIC, 2) AS costo_logistico_ajustado_total,
    ROUND((m.venta_ytd - (m.costo_entrega * a.factor_operativo + m.costo_almacen))::NUMERIC, 2) AS margen_logistico_ajustado,
    CASE
        WHEN COALESCE(m.venta_ytd, 0) > 0 THEN
            ROUND((((m.costo_entrega * a.factor_operativo + m.costo_almacen) / m.venta_ytd) * 100)::NUMERIC, 2)
        ELSE 0
    END AS ratio_costo_logistico_ajustado_pct,
    ROUND((m.costo_entrega * 3)::NUMERIC, 2) AS costo_servir_sin_autoelevador_escenario,
    ROUND((m.costo_entrega * 1)::NUMERIC, 2) AS costo_servir_con_autoelevador_escenario,
    CASE
        WHEN a.tiene_autoelevador THEN ROUND((m.costo_entrega * 2)::NUMERIC, 2)
        ELSE 0
    END AS ahorro_actual_vs_sin_autoelevador,
    CASE
        WHEN NOT a.tiene_autoelevador THEN ROUND((m.costo_entrega * 2)::NUMERIC, 2)
        ELSE 0
    END AS sobrecosto_actual_vs_con_autoelevador,
    COALESCE(s.score_total, 0) AS score_total_base,
    CASE WHEN a.tiene_autoelevador THEN 15 ELSE 0 END AS score_bonus_autoelevador,
    LEAST(100, ROUND((COALESCE(s.score_total, 0) + CASE WHEN a.tiene_autoelevador THEN 15 ELSE 0 END)::NUMERIC, 2))
        AS score_total_operativo,
    LEAST(35, ROUND((COALESCE(s.dim_productividad, 0) + CASE WHEN a.tiene_autoelevador THEN 15 ELSE 0 END)::NUMERIC, 2))
        AS dim_productividad_operativa
FROM vw_cliente_metricas m
JOIN vw_cliente_autoelevador a
    ON a.cliente_id = m.cliente
   AND a.sucursal = m.sucursal
LEFT JOIN vw_cliente_score s
    ON s.cliente = m.cliente
   AND s.sucursal = m.sucursal
WHERE m.venta_ytd > 0 OR m.venta_anio_base > 0;

-- -------------------------------------------------------------
-- 5) Eficiencia operativa (chofer + acompanantes)
-- Supuesto:
--   camiones_estimados = pedidos_ytd
--   choferes = pedidos_ytd
--   acompanantes = 0 con autoelevador, 2*pedidos_ytd sin autoelevador
-- indice_eficiencia_operativa:
--   HL / (choferes + acompanantes) = HL / (pedidos_ytd * factor_operativo)
-- -------------------------------------------------------------
DROP VIEW IF EXISTS vw_cliente_eficiencia_operativa CASCADE;
CREATE VIEW vw_cliente_eficiencia_operativa AS
SELECT
    c.cliente_id,
    c.cliente_nombre,
    c.sucursal,
    c.localidad,
    c.tiene_autoelevador,
    c.factor_operativo,
    c.hl,
    c.pedidos,
    GREATEST(COALESCE(c.pedidos, 0), 0) AS camiones_estimados,
    GREATEST(COALESCE(c.pedidos, 0), 0) AS choferes_equivalentes,
    CASE
        WHEN c.tiene_autoelevador THEN 0
        ELSE GREATEST(COALESCE(c.pedidos, 0), 0) * 2
    END AS acompanantes_equivalentes,
    (GREATEST(COALESCE(c.pedidos, 0), 0) * c.factor_operativo) AS dotacion_operativa_total,
    CASE
        WHEN (GREATEST(COALESCE(c.pedidos, 0), 0) * c.factor_operativo) > 0 THEN
            ROUND((c.hl / NULLIF((GREATEST(COALESCE(c.pedidos, 0), 0) * c.factor_operativo), 0))::NUMERIC, 6)
        ELSE 0
    END AS indice_eficiencia_operativa,
    CASE
        WHEN COALESCE(c.pedidos, 0) > 0 THEN ROUND((c.hl / c.pedidos)::NUMERIC, 6)
        ELSE 0
    END AS hl_por_pedido
FROM vw_cliente_costo_operativo c;

-- -------------------------------------------------------------
-- 6) Subclasificacion logistica extendida
-- Nuevas etiquetas:
--   GANADOR EFICIENTE
--   GANADOR AUTOELEVADOR
--   ALTO VALOR CARO DE SERVIR
--   ALTO VOLUMEN BAJA COMPLEJIDAD
--   ALTO COSTO OPERATIVO
-- -------------------------------------------------------------
DROP VIEW IF EXISTS vw_cliente_cluster_logistico CASCADE;
CREATE VIEW vw_cliente_cluster_logistico AS
WITH base AS (
    SELECT
        d.cliente,
        d.descripcion_cliente,
        d.sucursal,
        d.localidad,
        d.cluster_dpo,
        d.subcluster_logistico,
        d.venta_ytd,
        d.hl_ytd,
        d.pedidos_ytd,
        d.dropsize_bultos_ytd,
        d.pct_rechazo_pedidos,
        a.tiene_autoelevador,
        a.factor_operativo,
        c.costo_servir_ajustado,
        c.costo_logistico_ajustado_total,
        c.ratio_costo_logistico_ajustado_pct,
        c.score_total_operativo,
        e.indice_eficiencia_operativa
    FROM vw_cliente_cluster_dpo d
    JOIN vw_cliente_autoelevador a
        ON a.cliente_id = d.cliente
       AND a.sucursal = d.sucursal
    JOIN vw_cliente_costo_operativo c
        ON c.cliente_id = d.cliente
       AND c.sucursal = d.sucursal
    JOIN vw_cliente_eficiencia_operativa e
        ON e.cliente_id = d.cliente
       AND e.sucursal = d.sucursal
),
u AS (
    SELECT
        percentile_cont(0.70) WITHIN GROUP (ORDER BY venta_ytd) AS p70_venta,
        percentile_cont(0.70) WITHIN GROUP (ORDER BY hl_ytd) AS p70_hl,
        percentile_cont(0.70) WITHIN GROUP (ORDER BY pedidos_ytd) AS p70_pedidos,
        percentile_cont(0.75) WITHIN GROUP (ORDER BY ratio_costo_logistico_ajustado_pct) AS p75_ratio_costo,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY ratio_costo_logistico_ajustado_pct) AS p50_ratio_costo,
        percentile_cont(0.75) WITHIN GROUP (ORDER BY indice_eficiencia_operativa) AS p75_eficiencia,
        percentile_cont(0.25) WITHIN GROUP (ORDER BY pct_rechazo_pedidos) AS p25_rechazo,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY dropsize_bultos_ytd) AS p50_dropsize
    FROM base
    WHERE cluster_dpo NOT IN ('Inactivo', 'Ruta Temp')
)
SELECT
    b.*,
    CASE
        WHEN b.cluster_dpo = 'Ganador'
         AND b.tiene_autoelevador
         AND b.venta_ytd >= u.p70_venta
         AND b.hl_ytd >= u.p70_hl
            THEN 'GANADOR AUTOELEVADOR'

        WHEN b.cluster_dpo = 'Ganador'
         AND b.indice_eficiencia_operativa >= u.p75_eficiencia
         AND b.ratio_costo_logistico_ajustado_pct <= u.p50_ratio_costo
         AND b.pct_rechazo_pedidos <= u.p25_rechazo
            THEN 'GANADOR EFICIENTE'

        WHEN b.venta_ytd >= u.p70_venta
         AND b.pedidos_ytd >= u.p70_pedidos
         AND NOT b.tiene_autoelevador
         AND b.ratio_costo_logistico_ajustado_pct >= u.p75_ratio_costo
            THEN 'ALTO VALOR CARO DE SERVIR'

        WHEN b.hl_ytd >= u.p70_hl
         AND b.dropsize_bultos_ytd >= u.p50_dropsize
         AND b.pct_rechazo_pedidos <= u.p25_rechazo
         AND b.ratio_costo_logistico_ajustado_pct <= u.p50_ratio_costo
            THEN 'ALTO VOLUMEN BAJA COMPLEJIDAD'

        WHEN b.factor_operativo = 3
         AND b.ratio_costo_logistico_ajustado_pct >= u.p75_ratio_costo
            THEN 'ALTO COSTO OPERATIVO'

        ELSE UPPER(COALESCE(b.subcluster_logistico, 'ESTANDAR'))
    END AS subcluster_logistico_operativo
FROM base b
CROSS JOIN u;

COMMIT;

