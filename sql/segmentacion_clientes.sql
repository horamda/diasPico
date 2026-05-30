-- =============================================================
-- segmentacion_clientes.sql  —  DPO 2026 · Plan 4.2
-- Segmentación logística-comercial de clientes en 4 clusters.
-- Base: ventas_detalle + articulos + rechazos (PostgreSQL Railway)
-- =============================================================

-- ============================================================
-- TABLAS DE SOPORTE
-- ============================================================

CREATE TABLE IF NOT EXISTS seg_parametros (
    id                  SERIAL PRIMARY KEY,
    empresa_id          VARCHAR(50)   NOT NULL DEFAULT '1',
    sucursal_id         VARCHAR(50),                          -- NULL = aplica a todas
    costo_entrega_hl    NUMERIC(10,4) NOT NULL DEFAULT 0,
    costo_almacen_hl    NUMERIC(10,4) NOT NULL DEFAULT 0,
    percentil_alta      NUMERIC(5,4)  NOT NULL DEFAULT 0.70,  -- umbral venta alta
    percentil_baja      NUMERIC(5,4)  NOT NULL DEFAULT 0.30,  -- umbral venta baja
    umbral_crecimiento  NUMERIC(8,4)  DEFAULT NULL,           -- NULL = usar mediana
    anio_base           SMALLINT      NOT NULL DEFAULT 2025,
    anio_ytd            SMALLINT      NOT NULL DEFAULT 2026,
    mes_ytd_hasta       SMALLINT      DEFAULT NULL,           -- NULL = mes corriente
    peso_negocio        NUMERIC(5,4)  NOT NULL DEFAULT 0.35,
    peso_productividad  NUMERIC(5,4)  NOT NULL DEFAULT 0.20,
    peso_servicio       NUMERIC(5,4)  NOT NULL DEFAULT 0.20,
    peso_rentabilidad   NUMERIC(5,4)  NOT NULL DEFAULT 0.15,
    peso_geo            NUMERIC(5,4)  NOT NULL DEFAULT 0.10,
    activo              BOOLEAN       NOT NULL DEFAULT TRUE,
    version_regla       SMALLINT      NOT NULL DEFAULT 1,
    updated_at          TIMESTAMP     NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_seg_pesos CHECK (
        ABS(peso_negocio + peso_productividad + peso_servicio
            + peso_rentabilidad + peso_geo - 1.0) < 0.02
    ),
    CONSTRAINT chk_seg_percentiles CHECK (
        percentil_alta > percentil_baja
        AND percentil_alta <= 1 AND percentil_baja >= 0
    )
);

INSERT INTO seg_parametros (empresa_id) VALUES ('1') ON CONFLICT DO NOTHING;
CREATE INDEX IF NOT EXISTS idx_seg_params_activo ON seg_parametros(activo, empresa_id);

-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS seg_clientes_atributos (
    cliente         VARCHAR(50) PRIMARY KEY,
    sucursal_id     VARCHAR(50),
    localidad       VARCHAR(100),
    autoelevador    BOOLEAN     DEFAULT FALSE,
    nps_valor       NUMERIC(6,2),
    nps_fecha       DATE,
    rmd_valor       NUMERIC(6,2),
    rmd_fecha       DATE,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    updated_at      TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_seg_cli_suc       ON seg_clientes_atributos(sucursal_id);
CREATE INDEX IF NOT EXISTS idx_seg_cli_localidad ON seg_clientes_atributos(localidad);
CREATE INDEX IF NOT EXISTS idx_seg_cli_activo    ON seg_clientes_atributos(activo);

-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS cliente_autoelevador (
    id                BIGSERIAL PRIMARY KEY,
    is_cliente        VARCHAR(100) NOT NULL,
    autoelevador      BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_importacion TIMESTAMP NOT NULL DEFAULT NOW(),
    fuente            VARCHAR(100) NOT NULL DEFAULT 'manual',
    updated_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_cliente_autoelevador_cliente UNIQUE (is_cliente),
    CONSTRAINT chk_cliente_autoelevador_cliente
        CHECK (NULLIF(BTRIM(is_cliente), '') IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_cli_auto_cliente ON cliente_autoelevador(is_cliente);
CREATE INDEX IF NOT EXISTS idx_cli_auto_flag    ON cliente_autoelevador(autoelevador);

-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS seg_cliente_cluster_historico (
    id                      BIGSERIAL PRIMARY KEY,
    cliente                 VARCHAR(50)   NOT NULL,
    descripcion_cliente     VARCHAR(255),
    sucursal_id             VARCHAR(50),
    localidad               VARCHAR(100),
    periodo_anio            SMALLINT      NOT NULL,
    periodo_mes             SMALLINT      NOT NULL DEFAULT 0, -- 0 = cálculo anual
    cluster_dpo             VARCHAR(50),
    subcluster_logistico    VARCHAR(80),
    score_total             NUMERIC(6,2),
    dim_negocio             NUMERIC(6,2),
    dim_productividad       NUMERIC(6,2),
    dim_servicio            NUMERIC(6,2),
    dim_rentabilidad        NUMERIC(6,2),
    dim_geo                 NUMERIC(6,2),
    venta_ytd               NUMERIC(18,2),
    hl_ytd                  NUMERIC(18,4),
    crecimiento_pct         NUMERIC(10,4),
    costo_logistico_total   NUMERIC(18,2),
    ratio_costo_logistico   NUMERIC(8,4),
    pedidos_ytd             INTEGER,
    dropsize_ytd            NUMERIC(10,4),
    pct_rechazo_pedidos     NUMERIC(8,4),
    fecha_calculo           TIMESTAMP     NOT NULL DEFAULT NOW(),
    version_regla           SMALLINT      NOT NULL DEFAULT 1,
    proceso                 VARCHAR(100)  NOT NULL DEFAULT 'sistema',
    UNIQUE (cliente, periodo_anio, periodo_mes)
);

CREATE INDEX IF NOT EXISTS idx_seg_hist_cliente  ON seg_cliente_cluster_historico(cliente);
CREATE INDEX IF NOT EXISTS idx_seg_hist_periodo  ON seg_cliente_cluster_historico(periodo_anio, periodo_mes);
CREATE INDEX IF NOT EXISTS idx_seg_hist_cluster  ON seg_cliente_cluster_historico(cluster_dpo);
CREATE INDEX IF NOT EXISTS idx_seg_hist_suc      ON seg_cliente_cluster_historico(sucursal_id);

-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS seg_auditoria (
    id                      BIGSERIAL PRIMARY KEY,
    accion                  VARCHAR(100) NOT NULL,
    periodo_anio            SMALLINT,
    periodo_mes             SMALLINT,
    clientes_procesados     INTEGER DEFAULT 0,
    clientes_ganador        INTEGER DEFAULT 0,
    clientes_en_crecimiento INTEGER DEFAULT 0,
    clientes_basico         INTEGER DEFAULT 0,
    clientes_ventas_bajas   INTEGER DEFAULT 0,
    version_regla           SMALLINT,
    parametros              JSONB,
    ejecutado_por           VARCHAR(100) NOT NULL DEFAULT 'sistema',
    ejecutado_at            TIMESTAMP    NOT NULL DEFAULT NOW(),
    duracion_ms             INTEGER,
    error_detalle           TEXT
);

CREATE INDEX IF NOT EXISTS idx_seg_aud_at     ON seg_auditoria(ejecutado_at DESC);
CREATE INDEX IF NOT EXISTS idx_seg_aud_accion ON seg_auditoria(accion);


-- ============================================================
-- VISTA 1: vw_cliente_metricas
-- Métricas base: ventas, volumen, pedidos, rechazos, costos
-- Aplica los mismos filtros que el panel de picos:
--   • solo tipo_producto = 'mercaderia'
--   • excluye REMITO y COMOD
-- ============================================================

DROP VIEW IF EXISTS vw_cliente_metricas CASCADE;
CREATE VIEW vw_cliente_metricas AS
WITH params AS (
    SELECT
        costo_entrega_hl,
        costo_almacen_hl,
        anio_base,
        anio_ytd,
        COALESCE(mes_ytd_hasta,
                 EXTRACT(MONTH FROM CURRENT_DATE)::INT) AS mes_ytd_hasta
    FROM seg_parametros
    WHERE activo = TRUE
    ORDER BY (sucursal_id IS NULL) DESC, id DESC
    LIMIT 1
),
base AS (
    SELECT
        NULLIF(TRIM(v.cliente), '')                                      AS cliente,
        NULLIF(TRIM(v.descripcion_cliente), '')                          AS descripcion_cliente,
        COALESCE(NULLIF(TRIM(v.sucursal), ''), '1')                     AS sucursal,
        v.fecha,
        COALESCE(v.importe_neto, 0)                                      AS importe,
        COALESCE(v.bultos, 0)                                            AS bultos,
        COALESCE(v.unidad_medida, 0)                                     AS hl,
        COALESCE(v.unidad_paquete, 0)                                    AS up,
        CASE WHEN COALESCE(a.bultos_por_pallet, 0) > 0
             THEN COALESCE(v.bultos, 0) / a.bultos_por_pallet
             ELSE 0 END                                                   AS pallets,
        CASE WHEN COALESCE(rz.tomar, FALSE) AND (
                COALESCE(v.bultos_rechazados,       0) > 0
             OR COALESCE(v.unidad_medida_rechazado, 0) > 0
             OR COALESCE(v.unidad_paquete_rechazado,0) > 0)
             THEN 1 ELSE 0 END                                            AS es_rechazo,
        v.fecha::TEXT || '|' || NULLIF(TRIM(v.cliente), '')              AS pedido_key
    FROM ventas_detalle v
    JOIN articulos a ON a.id_articulo = v.id_articulo
    LEFT JOIN LATERAL (
        SELECT tomar FROM rechazos r
        WHERE LOWER(TRIM(COALESCE(v.motivo_rechazo, ''))) = r.motivo_key
           OR LOWER(TRIM(COALESCE(v.motivo_rechazo, ''))) LIKE r.motivo_key || ' %'
        ORDER BY LENGTH(r.motivo_key) DESC
        LIMIT 1
    ) rz ON TRUE
    WHERE LOWER(TRIM(COALESCE(a.tipo_producto, ''))) = 'mercaderia'
      AND LOWER(TRIM(COALESCE(v.documento,        ''))) NOT LIKE 'remit%'
      AND LOWER(TRIM(COALESCE(v.documento,        ''))) NOT LIKE 'comod%'
      AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'remit%'
      AND LOWER(TRIM(COALESCE(v.detalle_documento,''))) NOT LIKE 'comod%'
      AND NULLIF(TRIM(v.cliente), '') IS NOT NULL
),
anio_base_m AS (
    SELECT
        b.cliente, b.sucursal,
        MAX(b.descripcion_cliente)    AS descripcion_cliente,
        SUM(b.importe)                AS venta_base,
        SUM(b.hl)                     AS hl_base,
        SUM(b.bultos)                 AS bultos_base,
        SUM(b.pallets)                AS pallets_base,
        SUM(b.up)                     AS up_base,
        COUNT(DISTINCT b.pedido_key)  AS pedidos_base
    FROM base b
    CROSS JOIN params p
    WHERE EXTRACT(YEAR FROM b.fecha)::INT = p.anio_base
    GROUP BY b.cliente, b.sucursal
),
anio_ytd_m AS (
    SELECT
        b.cliente, b.sucursal,
        SUM(b.importe)                AS venta_ytd,
        SUM(b.hl)                     AS hl_ytd,
        SUM(b.bultos)                 AS bultos_ytd,
        SUM(b.pallets)                AS pallets_ytd,
        SUM(b.up)                     AS up_ytd,
        COUNT(DISTINCT b.pedido_key)  AS pedidos_ytd,
        SUM(b.es_rechazo)             AS rechazos_ytd
    FROM base b
    CROSS JOIN params p
    WHERE EXTRACT(YEAR  FROM b.fecha)::INT = p.anio_ytd
      AND EXTRACT(MONTH FROM b.fecha)::INT <= p.mes_ytd_hasta
    GROUP BY b.cliente, b.sucursal
),
base_mismoper AS (
    SELECT
        b.cliente, b.sucursal,
        SUM(b.importe)                AS venta_base_per,
        COUNT(DISTINCT b.pedido_key)  AS pedidos_base_per,
        SUM(b.es_rechazo)             AS rechazos_base_per
    FROM base b
    CROSS JOIN params p
    WHERE EXTRACT(YEAR  FROM b.fecha)::INT = p.anio_base
      AND EXTRACT(MONTH FROM b.fecha)::INT <= p.mes_ytd_hasta
    GROUP BY b.cliente, b.sucursal
)
SELECT
    COALESCE(y.cliente,  ab.cliente)   AS cliente,
    COALESCE(y.sucursal, ab.sucursal)  AS sucursal,
    COALESCE(ab.descripcion_cliente, y.cliente, '') AS descripcion_cliente,
    -- Venta
    COALESCE(ab.venta_base, 0)         AS venta_anio_base,
    COALESCE(y.venta_ytd,  0)          AS venta_ytd,
    COALESCE(bm.venta_base_per, 0)     AS venta_base_mismo_per,
    CASE WHEN COALESCE(bm.venta_base_per, 0) > 0
         THEN ROUND(((COALESCE(y.venta_ytd, 0) - bm.venta_base_per)
                     / bm.venta_base_per * 100)::NUMERIC, 2)
         ELSE NULL END                 AS crecimiento_pct,
    -- Volumen
    COALESCE(ab.hl_base,  0)           AS hl_anio_base,
    COALESCE(y.hl_ytd,    0)           AS hl_ytd,
    COALESCE(ab.bultos_base,  0)       AS bultos_anio_base,
    COALESCE(y.bultos_ytd,    0)       AS bultos_ytd,
    COALESCE(ab.pallets_base, 0)       AS pallets_anio_base,
    COALESCE(y.pallets_ytd,   0)       AS pallets_ytd,
    COALESCE(ab.up_base, 0)            AS up_anio_base,
    COALESCE(y.up_ytd,   0)            AS up_ytd,
    -- Pedidos
    COALESCE(ab.pedidos_base, 0)       AS pedidos_anio_base,
    COALESCE(y.pedidos_ytd,   0)       AS pedidos_ytd,
    -- Drop Size
    CASE WHEN COALESCE(y.pedidos_ytd, 0) > 0
         THEN ROUND((y.bultos_ytd / y.pedidos_ytd)::NUMERIC, 2) ELSE 0
    END                                AS dropsize_bultos_ytd,
    CASE WHEN COALESCE(y.pedidos_ytd, 0) > 0
         THEN ROUND((y.hl_ytd    / y.pedidos_ytd)::NUMERIC, 4) ELSE 0
    END                                AS dropsize_hl_ytd,
    -- Ticket promedio
    CASE WHEN COALESCE(y.pedidos_ytd, 0) > 0
         THEN ROUND((y.venta_ytd  / y.pedidos_ytd)::NUMERIC, 2) ELSE 0
    END                                AS ticket_promedio_ytd,
    -- Rechazos
    COALESCE(y.rechazos_ytd, 0)        AS rechazos_ytd,
    CASE WHEN COALESCE(y.pedidos_ytd, 0) > 0
         THEN ROUND((COALESCE(y.rechazos_ytd,0)::NUMERIC / y.pedidos_ytd * 100), 2) ELSE 0
    END                                AS pct_rechazo_pedidos,
    -- Atributos de cliente
    COALESCE(ca.localidad, '')         AS localidad,
    COALESCE(cae.autoelevador, ca.autoelevador, FALSE) AS autoelevador,
    ca.nps_valor,
    ca.rmd_valor,
    -- Costos logísticos (calculados sobre YTD)
    ROUND((COALESCE(y.hl_ytd, 0) * p.costo_entrega_hl)::NUMERIC, 2)               AS costo_entrega,
    ROUND((COALESCE(y.hl_ytd, 0) * p.costo_almacen_hl)::NUMERIC, 2)               AS costo_almacen,
    ROUND((COALESCE(y.hl_ytd, 0)
           * (p.costo_entrega_hl + p.costo_almacen_hl))::NUMERIC, 2)               AS costo_logistico_total,
    ROUND((COALESCE(y.venta_ytd, 0)
           - COALESCE(y.hl_ytd, 0)
             * (p.costo_entrega_hl + p.costo_almacen_hl))::NUMERIC, 2)             AS margen_logistico_proxy,
    CASE WHEN COALESCE(y.venta_ytd, 0) > 0
         THEN ROUND((COALESCE(y.hl_ytd, 0)
                     * (p.costo_entrega_hl + p.costo_almacen_hl)
                     / y.venta_ytd * 100)::NUMERIC, 2)
         ELSE 0 END                    AS ratio_costo_logistico_pct
FROM anio_ytd_m y
FULL OUTER JOIN anio_base_m ab
    ON ab.cliente = y.cliente AND ab.sucursal = y.sucursal
LEFT JOIN base_mismoper bm
    ON bm.cliente = COALESCE(y.cliente, ab.cliente)
   AND bm.sucursal = COALESCE(y.sucursal, ab.sucursal)
LEFT JOIN seg_clientes_atributos ca
    ON ca.cliente = COALESCE(y.cliente, ab.cliente)
LEFT JOIN cliente_autoelevador cae
    ON cae.is_cliente = COALESCE(y.cliente, ab.cliente)
CROSS JOIN params p;


-- ============================================================
-- VISTA 2: vw_cliente_cluster_dpo
-- Clasificación DPO 2x2 (ingreso × crecimiento) +
-- subcluster logístico. Umbrales dinámicos por percentil.
-- ============================================================

DROP VIEW IF EXISTS vw_cliente_cluster_dpo CASCADE;
CREATE VIEW vw_cliente_cluster_dpo AS
WITH m AS (
    SELECT * FROM vw_cliente_metricas
    WHERE venta_ytd > 0 OR venta_anio_base > 0
),
umbrales AS (
    SELECT
        percentile_cont(
            COALESCE(
                (SELECT percentil_alta FROM seg_parametros
                 WHERE activo = TRUE ORDER BY (sucursal_id IS NULL) DESC, id DESC LIMIT 1),
                0.70)
        ) WITHIN GROUP (ORDER BY venta_ytd)              AS umbral_venta_alta,
        percentile_cont(
            COALESCE(
                (SELECT percentil_baja FROM seg_parametros
                 WHERE activo = TRUE ORDER BY (sucursal_id IS NULL) DESC, id DESC LIMIT 1),
                0.30)
        ) WITHIN GROUP (ORDER BY venta_ytd)              AS umbral_venta_baja,
        COALESCE(
            (SELECT umbral_crecimiento FROM seg_parametros
             WHERE activo = TRUE AND umbral_crecimiento IS NOT NULL
             ORDER BY (sucursal_id IS NULL) DESC, id DESC LIMIT 1),
            percentile_cont(0.5) WITHIN GROUP (ORDER BY crecimiento_pct)
        )                                                 AS umbral_crecimiento,
        percentile_cont(0.25) WITHIN GROUP (ORDER BY dropsize_bultos_ytd)        AS p25_dropsize,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY dropsize_bultos_ytd)        AS p50_dropsize,
        percentile_cont(0.75) WITHIN GROUP (ORDER BY ratio_costo_logistico_pct)  AS p75_ratio_costo
    FROM m
)
SELECT
    m.*,
    u.umbral_venta_alta,
    u.umbral_venta_baja,
    u.umbral_crecimiento,
    -- ── Cluster DPO (matriz ingreso × crecimiento) ──────────
    CASE
        WHEN m.venta_ytd >= u.umbral_venta_alta
         AND COALESCE(m.crecimiento_pct, 0) > COALESCE(u.umbral_crecimiento, 0)
            THEN 'Ganador'
        WHEN COALESCE(m.crecimiento_pct, 0) > COALESCE(u.umbral_crecimiento, 0)
            THEN 'En crecimiento'
        WHEN m.venta_ytd >= u.umbral_venta_baja
            THEN 'Básico'
        ELSE 'Ventas bajas'
    END AS cluster_dpo,
    -- ── Subcluster logístico ─────────────────────────────────
    CASE
        WHEN COALESCE(m.ratio_costo_logistico_pct, 0) > u.p75_ratio_costo
         AND m.dropsize_bultos_ytd < u.p25_dropsize
            THEN 'Caro de servir'
        WHEN COALESCE(m.pct_rechazo_pedidos, 0) > 20
            THEN 'Complejo'
        WHEN COALESCE(m.crecimiento_pct, 0) > 15
         AND COALESCE(m.pct_rechazo_pedidos, 0) < 5
            THEN 'Alto potencial'
        WHEN COALESCE(m.ratio_costo_logistico_pct, 0) <= 20
         AND m.dropsize_bultos_ytd >= u.p50_dropsize
            THEN 'Eficiente'
        WHEN COALESCE(m.ratio_costo_logistico_pct, 0) <= 25
         AND COALESCE(m.margen_logistico_proxy, 0) > 0
            THEN 'Rentable'
        ELSE 'Estándar'
    END AS subcluster_logistico
FROM m
CROSS JOIN umbrales u;


-- ============================================================
-- VISTA 3: vw_cliente_score
-- Score 0-100 por cliente.
-- Fórmula (suma de puntos máximos = 100):
--   Negocio       35 pts: venta(15) + HL(10) + crecimiento(10)
--   Productividad 20 pts: dropsize(10) + pallets/ped(5) + autoelevador(5)
--   Servicio      20 pts: rechazos(10) + RMD(5) + NPS(5)
--   Rentabilidad  15 pts: ratio_costo(10) + margen(5)
--   Geo/Frecuencia 10 pts: pedidos(7) + localidad(2) + sucursal(1)
-- Normalización min-max por columna (ventana global).
-- Menor es mejor para: rechazos, ratio_costo. Resto: mayor es mejor.
-- NULLs en RMD/NPS → imputados con mediana.
-- Crecimiento: capped en [-100, +300] para resistir outliers.
-- ============================================================

DROP VIEW IF EXISTS vw_cliente_score CASCADE;
CREATE VIEW vw_cliente_score AS
WITH m AS (
    SELECT * FROM vw_cliente_metricas
    WHERE venta_ytd > 0 OR venta_anio_base > 0
),
medianas AS (
    SELECT
        COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY rmd_valor), 5) AS med_rmd,
        COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY nps_valor), 5) AS med_nps,
        COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY crecimiento_pct), 0) AS med_crec
    FROM m
),
clamped AS (
    SELECT
        m.*,
        GREATEST(-100, LEAST(300,
            COALESCE(m.crecimiento_pct, md.med_crec)))         AS crec_cap,
        COALESCE(m.rmd_valor, md.med_rmd)                      AS rmd_imp,
        COALESCE(m.nps_valor, md.med_nps)                      AS nps_imp,
        CASE WHEN m.pedidos_ytd > 0
             THEN m.pallets_ytd / m.pedidos_ytd ELSE 0 END     AS pal_por_ped,
        GREATEST(0, m.ratio_costo_logistico_pct)               AS ratio_pos
    FROM m
    CROSS JOIN medianas md
),
rngs AS (
    SELECT
        c.*,
        MIN(venta_ytd)          OVER () AS mn_v,  MAX(venta_ytd)          OVER () AS mx_v,
        MIN(hl_ytd)             OVER () AS mn_h,  MAX(hl_ytd)             OVER () AS mx_h,
        MIN(crec_cap)           OVER () AS mn_c,  MAX(crec_cap)           OVER () AS mx_c,
        MIN(dropsize_bultos_ytd)OVER () AS mn_d,  MAX(dropsize_bultos_ytd)OVER () AS mx_d,
        MIN(pal_por_ped)        OVER () AS mn_p,  MAX(pal_por_ped)        OVER () AS mx_p,
        MIN(pct_rechazo_pedidos)OVER () AS mn_r,  MAX(pct_rechazo_pedidos)OVER () AS mx_r,
        MIN(rmd_imp)            OVER () AS mn_rmd,MAX(rmd_imp)            OVER () AS mx_rmd,
        MIN(nps_imp)            OVER () AS mn_nps,MAX(nps_imp)            OVER () AS mx_nps,
        MIN(ratio_pos)          OVER () AS mn_rc, MAX(ratio_pos)          OVER () AS mx_rc,
        MIN(margen_logistico_proxy) OVER () AS mn_mg, MAX(margen_logistico_proxy) OVER () AS mx_mg,
        MIN(pedidos_ytd)        OVER () AS mn_ped,MAX(pedidos_ytd)        OVER () AS mx_ped
    FROM clamped c
),
normed AS (
    SELECT
        r.*,
        CASE WHEN mx_v   > mn_v   THEN (venta_ytd           - mn_v  )/(mx_v  -mn_v  ) ELSE 0.5 END AS nv,
        CASE WHEN mx_h   > mn_h   THEN (hl_ytd               - mn_h  )/(mx_h  -mn_h  ) ELSE 0.5 END AS nh,
        CASE WHEN mx_c   > mn_c   THEN (crec_cap             - mn_c  )/(mx_c  -mn_c  ) ELSE 0.5 END AS nc,
        CASE WHEN mx_d   > mn_d   THEN (dropsize_bultos_ytd  - mn_d  )/(mx_d  -mn_d  ) ELSE 0.5 END AS nd,
        CASE WHEN mx_p   > mn_p   THEN (pal_por_ped          - mn_p  )/(mx_p  -mn_p  ) ELSE 0.5 END AS np,
        CASE WHEN mx_r   > mn_r   THEN 1-(pct_rechazo_pedidos- mn_r  )/(mx_r  -mn_r  ) ELSE 0.5 END AS nr,
        CASE WHEN mx_rmd > mn_rmd THEN (rmd_imp              - mn_rmd)/(mx_rmd-mn_rmd) ELSE 0.5 END AS nrmd,
        CASE WHEN mx_nps > mn_nps THEN (nps_imp              - mn_nps)/(mx_nps-mn_nps) ELSE 0.5 END AS nnps,
        CASE WHEN mx_rc  > mn_rc  THEN 1-(ratio_pos          - mn_rc )/(mx_rc -mn_rc ) ELSE 0.5 END AS nrc,
        CASE WHEN mx_mg  > mn_mg  THEN (margen_logistico_proxy- mn_mg)/(mx_mg -mn_mg ) ELSE 0.5 END AS nmg,
        CASE WHEN mx_ped > mn_ped THEN (pedidos_ytd           - mn_ped)/(mx_ped-mn_ped) ELSE 0.5 END AS nped
    FROM rngs r
)
SELECT
    cliente,
    descripcion_cliente,
    sucursal,
    localidad,
    -- Dimensiones (para radar chart)
    ROUND((nv*15 + nh*10 + nc*10)::NUMERIC, 2)                                 AS dim_negocio,
    ROUND((nd*10 + np*5  + (CASE WHEN autoelevador THEN 5.0 ELSE 0.0 END))::NUMERIC, 2) AS dim_productividad,
    ROUND((nr*10 + nrmd*5 + nnps*5)::NUMERIC, 2)                               AS dim_servicio,
    ROUND((nrc*10 + nmg*5)::NUMERIC, 2)                                         AS dim_rentabilidad,
    ROUND((nped*7
           + (CASE WHEN NULLIF(localidad,'') IS NOT NULL THEN 2.0 ELSE 0.0 END)
           + (CASE WHEN NULLIF(sucursal,'')  IS NOT NULL THEN 1.0 ELSE 0.0 END))::NUMERIC, 2) AS dim_geo,
    -- Puntos individuales (desglose)
    ROUND((nv  *15)::NUMERIC,2) AS pts_venta,
    ROUND((nh  *10)::NUMERIC,2) AS pts_hl,
    ROUND((nc  *10)::NUMERIC,2) AS pts_crecimiento,
    ROUND((nd  *10)::NUMERIC,2) AS pts_dropsize,
    ROUND((np  * 5)::NUMERIC,2) AS pts_pallets_ped,
    ROUND((CASE WHEN autoelevador THEN 5.0 ELSE 0.0 END)::NUMERIC,2) AS pts_autoelevador,
    ROUND((nr  *10)::NUMERIC,2) AS pts_rechazos,
    ROUND((nrmd* 5)::NUMERIC,2) AS pts_rmd,
    ROUND((nnps* 5)::NUMERIC,2) AS pts_nps,
    ROUND((nrc *10)::NUMERIC,2) AS pts_ratio_costo,
    ROUND((nmg * 5)::NUMERIC,2) AS pts_margen,
    ROUND((nped* 7)::NUMERIC,2) AS pts_frecuencia,
    -- Score total 0-100
    ROUND((
        nv*15 + nh*10 + nc*10
      + nd*10 + np*5  + (CASE WHEN autoelevador THEN 5.0 ELSE 0.0 END)
      + nr*10 + nrmd*5 + nnps*5
      + nrc*10 + nmg*5
      + nped*7
      + (CASE WHEN NULLIF(localidad,'') IS NOT NULL THEN 2.0 ELSE 0.0 END)
      + (CASE WHEN NULLIF(sucursal,'')  IS NOT NULL THEN 1.0 ELSE 0.0 END)
    )::NUMERIC, 2) AS score_total
FROM normed;


-- ============================================================
-- VISTA 4: vw_cliente_plan_servicio
-- Cluster + score + plan de acción + alertas operativas
-- ============================================================

DROP VIEW IF EXISTS vw_cliente_plan_servicio CASCADE;
CREATE VIEW vw_cliente_plan_servicio AS
SELECT
    c.cliente,
    c.descripcion_cliente,
    c.sucursal,
    c.localidad,
    c.autoelevador,
    c.cluster_dpo,
    c.subcluster_logistico,
    s.score_total,
    s.dim_negocio,
    s.dim_productividad,
    s.dim_servicio,
    s.dim_rentabilidad,
    s.dim_geo,
    s.pts_venta,
    s.pts_hl,
    s.pts_crecimiento,
    s.pts_dropsize,
    s.pts_rechazos,
    s.pts_rmd,
    s.pts_nps,
    c.venta_ytd,
    c.venta_anio_base,
    c.crecimiento_pct,
    c.hl_ytd,
    c.bultos_ytd,
    c.pallets_ytd,
    c.pedidos_ytd,
    c.dropsize_bultos_ytd,
    c.ticket_promedio_ytd,
    c.rechazos_ytd,
    c.pct_rechazo_pedidos,
    c.nps_valor,
    c.rmd_valor,
    c.costo_entrega,
    c.costo_almacen,
    c.costo_logistico_total,
    c.margen_logistico_proxy,
    c.ratio_costo_logistico_pct,
    -- Plan de servicio sugerido
    CASE c.cluster_dpo
        WHEN 'Ganador'
            THEN 'Prioridad de inventario · mejor OTIF · ventanas horarias precisas · evaluar flex/express'
        WHEN 'En crecimiento'
            THEN 'Seguimiento comercial-logístico · mejorar frecuencia · acompañar experiencia de entrega'
        WHEN 'Básico'
            THEN 'Servicio estándar · mantener costo controlado · frecuencia óptima por ruta'
        WHEN 'Ventas bajas'
            THEN 'Optimizar frecuencia · consolidar pedidos · revisar rentabilidad de servir'
        ELSE 'Sin clasificación'
    END AS plan_servicio,
    -- Acción prioritaria por subcluster
    CASE c.subcluster_logistico
        WHEN 'Caro de servir'  THEN 'Revisar costo logístico · negociar drop size mínimo · evaluar consolidación'
        WHEN 'Alto potencial'  THEN 'Fortalecer relación comercial · asignar vendedor referente · mejorar OTIF'
        WHEN 'Eficiente'       THEN 'Mantener operación · compartir benchmarks positivos con el equipo'
        WHEN 'Rentable'        THEN 'Proteger cuenta · renovar acuerdo · ofrecer beneficios premium'
        WHEN 'Complejo'        THEN 'Plan de mejora de rechazo · visita técnica · acuerdo de entrega revisado'
        ELSE                        'Monitorear indicadores mensualmente'
    END AS accion_prioritaria,
    -- Alertas operativas
    CASE
        WHEN c.pct_rechazo_pedidos > 20                          THEN 'CRÍTICO: tasa de rechazo > 20 %'
        WHEN c.pct_rechazo_pedidos > 10                          THEN 'ATENCIÓN: tasa de rechazo > 10 %'
        WHEN c.ratio_costo_logistico_pct > 40                    THEN 'CRÍTICO: ratio costo logístico > 40 %'
        WHEN COALESCE(c.crecimiento_pct, 0) < -30               THEN 'ALERTA: caída de venta > 30 % vs año base'
        WHEN c.cluster_dpo = 'Ganador'
         AND COALESCE(c.crecimiento_pct, 0) < 0                 THEN 'AVISO: Ganador con caída YTD'
        ELSE NULL
    END AS alerta_operativa,
    -- Prioridad de gestión 1-4
    CASE c.cluster_dpo
        WHEN 'Ganador'        THEN 1
        WHEN 'En crecimiento' THEN 2
        WHEN 'Básico'         THEN 3
        WHEN 'Ventas bajas'   THEN 4
        ELSE 5
    END AS prioridad_gestion
FROM vw_cliente_cluster_dpo c
LEFT JOIN vw_cliente_score s ON s.cliente = c.cliente;


-- ============================================================
-- VISTA 5: resumen_cluster_sucursal
-- ============================================================

DROP VIEW IF EXISTS resumen_cluster_sucursal CASCADE;
CREATE VIEW resumen_cluster_sucursal AS
SELECT
    c.sucursal,
    c.cluster_dpo,
    COUNT(*)                                                                AS cantidad_clientes,
    ROUND(SUM(c.venta_ytd)::NUMERIC, 2)                                     AS venta_total_ytd,
    ROUND(SUM(c.hl_ytd)::NUMERIC, 4)                                        AS hl_total_ytd,
    ROUND(SUM(c.costo_logistico_total)::NUMERIC, 2)                         AS costo_logistico_total,
    ROUND(SUM(c.rechazos_ytd)::NUMERIC, 0)                                  AS rechazos_total,
    ROUND(SUM(c.pedidos_ytd)::NUMERIC, 0)                                   AS pedidos_total,
    ROUND(AVG(c.pct_rechazo_pedidos)::NUMERIC, 2)                           AS pct_rechazo_prom,
    ROUND(AVG(c.dropsize_bultos_ytd)::NUMERIC, 2)                           AS dropsize_prom,
    ROUND(AVG(c.ratio_costo_logistico_pct)::NUMERIC, 2)                     AS ratio_costo_prom,
    ROUND(AVG(COALESCE(c.crecimiento_pct, 0))::NUMERIC, 2)                  AS crecimiento_prom_pct,
    ROUND(AVG(c.rmd_valor)::NUMERIC, 2)                                     AS rmd_prom,
    ROUND(AVG(c.nps_valor)::NUMERIC, 2)                                     AS nps_prom,
    ROUND(AVG(s.score_total)::NUMERIC, 2)                                   AS score_prom,
    ROUND((SUM(c.venta_ytd)
           / NULLIF(SUM(SUM(c.venta_ytd)) OVER (PARTITION BY c.sucursal), 0)
           * 100)::NUMERIC, 2)                                              AS pct_venta_en_sucursal
FROM vw_cliente_cluster_dpo c
LEFT JOIN vw_cliente_score s ON s.cliente = c.cliente
GROUP BY c.sucursal, c.cluster_dpo;


-- ============================================================
-- VISTA 6: resumen_cluster_localidad
-- ============================================================

DROP VIEW IF EXISTS resumen_cluster_localidad CASCADE;
CREATE VIEW resumen_cluster_localidad AS
SELECT
    COALESCE(NULLIF(c.localidad, ''), 'Sin localidad') AS localidad,
    c.sucursal,
    c.cluster_dpo,
    COUNT(*)                                                    AS cantidad_clientes,
    ROUND(SUM(c.venta_ytd)::NUMERIC, 2)                        AS venta_total_ytd,
    ROUND(SUM(c.hl_ytd)::NUMERIC, 4)                           AS hl_total_ytd,
    ROUND(SUM(c.costo_logistico_total)::NUMERIC, 2)            AS costo_logistico_total,
    ROUND(AVG(c.pct_rechazo_pedidos)::NUMERIC, 2)              AS pct_rechazo_prom,
    ROUND(AVG(c.dropsize_bultos_ytd)::NUMERIC, 2)              AS dropsize_prom,
    ROUND(AVG(COALESCE(c.crecimiento_pct, 0))::NUMERIC, 2)     AS crecimiento_prom_pct,
    ROUND(AVG(s.score_total)::NUMERIC, 2)                      AS score_prom
FROM vw_cliente_cluster_dpo c
LEFT JOIN vw_cliente_score s ON s.cliente = c.cliente
GROUP BY c.localidad, c.sucursal, c.cluster_dpo;


-- ============================================================
-- VISTAS MATERIALIZADAS (OPCIONAL — para producción)
-- Descomentar y ejecutar REFRESH manualmente o post-carga.
-- ============================================================
-- CREATE MATERIALIZED VIEW IF NOT EXISTS mv_cliente_metricas   AS SELECT * FROM vw_cliente_metricas;
-- CREATE MATERIALIZED VIEW IF NOT EXISTS mv_cliente_cluster_dpo AS SELECT * FROM vw_cliente_cluster_dpo;
-- CREATE MATERIALIZED VIEW IF NOT EXISTS mv_cliente_score       AS SELECT * FROM vw_cliente_score;
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mv_cliente_metricas;
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mv_cliente_cluster_dpo;
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mv_cliente_score;
