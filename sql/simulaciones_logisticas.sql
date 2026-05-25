-- Módulo: Simulación Logística Mensual
-- PostgreSQL / Railway
-- Compatibilidad: PostgreSQL 13+

CREATE TABLE IF NOT EXISTS simulaciones_logisticas (
    id                       BIGSERIAL PRIMARY KEY,
    empresa_id               VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id              VARCHAR(50) NOT NULL,
    anio                     SMALLINT   NOT NULL,
    mes                      SMALLINT   NOT NULL CHECK (mes BETWEEN 1 AND 12),
    anio_base                SMALLINT   NOT NULL,
    mes_base                 SMALLINT   NOT NULL CHECK (mes_base BETWEEN 1 AND 12),

    -- Parámetros ingresados por el usuario
    crecimiento_esperado     NUMERIC(8,2)  NOT NULL DEFAULT 0,
    ausentismo_esperado      NUMERIC(8,2)  NOT NULL DEFAULT 0,
    camiones_disponibles     NUMERIC(8,2)  NOT NULL DEFAULT 0,
    dias_trabajados          SMALLINT      NOT NULL DEFAULT 22,
    dias_pico_esperados      SMALLINT      NOT NULL DEFAULT 0,

    -- Datos base (mismo mes del año anterior)
    hl_base                  NUMERIC(18,4) NOT NULL DEFAULT 0,
    bultos_base              NUMERIC(18,4) NOT NULL DEFAULT 0,
    pallets_base             NUMERIC(18,4) NOT NULL DEFAULT 0,
    up_base                  NUMERIC(18,4) NOT NULL DEFAULT 0,
    pdv_base                 NUMERIC(18,4) NOT NULL DEFAULT 0,
    salidas_base             NUMERIC(18,4) NOT NULL DEFAULT 0,
    camiones_base            NUMERIC(12,4) NOT NULL DEFAULT 0,
    personas_base            NUMERIC(12,4) NOT NULL DEFAULT 0,
    rechazos_base            NUMERIC(12,4) NOT NULL DEFAULT 0,
    dropsize_base            NUMERIC(12,4) NOT NULL DEFAULT 0,
    dias_trabajados_base     SMALLINT      NOT NULL DEFAULT 0,
    dias_pico_base           SMALLINT      NOT NULL DEFAULT 0,

    -- Proyecciones de volumen
    hl_plan                  NUMERIC(18,4) NOT NULL DEFAULT 0,
    bultos_plan              NUMERIC(18,4) NOT NULL DEFAULT 0,
    pallets_plan             NUMERIC(18,4) NOT NULL DEFAULT 0,
    up_plan                  NUMERIC(18,4) NOT NULL DEFAULT 0,
    pdv_plan                 NUMERIC(18,4) NOT NULL DEFAULT 0,

    -- Recursos calculados (mes normal)
    salidas_necesarias       NUMERIC(12,4) NOT NULL DEFAULT 0,
    camiones_necesarios      NUMERIC(12,4) NOT NULL DEFAULT 0,
    personas_necesarias      NUMERIC(12,4) NOT NULL DEFAULT 0,

    -- Recursos calculados (días pico)
    camiones_dia_pico        NUMERIC(12,4) NOT NULL DEFAULT 0,
    personas_dia_pico        NUMERIC(12,4) NOT NULL DEFAULT 0,
    salidas_dia_pico         NUMERIC(12,4) NOT NULL DEFAULT 0,

    -- Flota
    camiones_adicionales     NUMERIC(12,4) NOT NULL DEFAULT 0,

    -- Riesgo
    riesgo_score             SMALLINT      NOT NULL DEFAULT 0,
    riesgo_nivel             VARCHAR(20)   NOT NULL DEFAULT 'BAJO',
    recomendaciones_json     TEXT,

    -- Estado de la simulación
    estado                   VARCHAR(20)   NOT NULL DEFAULT 'ABIERTA'
                             CHECK (estado IN ('ABIERTA','EN_AVANCE','CERRADA')),
    observaciones            TEXT,
    created_at               TIMESTAMP     NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_siml_empresa_sucursal
    ON simulaciones_logisticas (empresa_id, sucursal_id, anio, mes);

-- Seguimiento de avance durante el mes
CREATE TABLE IF NOT EXISTS avances_simulaciones_logisticas (
    id                       BIGSERIAL PRIMARY KEY,
    simulacion_id            BIGINT        NOT NULL
                             REFERENCES simulaciones_logisticas(id) ON DELETE CASCADE,
    dias_transcurridos       SMALLINT      NOT NULL,
    hl_real                  NUMERIC(18,4),
    bultos_real              NUMERIC(18,4),
    pallets_real             NUMERIC(18,4),
    pdv_real                 NUMERIC(18,4),
    salidas_real             NUMERIC(18,4),
    camiones_real            NUMERIC(12,4),
    personas_real            NUMERIC(12,4),
    rechazos_real            NUMERIC(12,4),
    avance_esperado          NUMERIC(8,4),
    dispersion_hl_pct        NUMERIC(8,2),
    dispersion_bultos_pct    NUMERIC(8,2),
    dispersion_pallets_pct   NUMERIC(8,2),
    dispersion_pdv_pct       NUMERIC(8,2),
    dispersion_salidas_pct   NUMERIC(8,2),
    dispersion_camiones_pct  NUMERIC(8,2),
    dispersion_personas_pct  NUMERIC(8,2),
    dispersion_rechazos_pct  NUMERIC(8,2),
    created_at               TIMESTAMP     NOT NULL DEFAULT NOW()
);

-- Cierre mensual con datos reales finales
CREATE TABLE IF NOT EXISTS cierres_simulaciones_logisticas (
    id                       BIGSERIAL PRIMARY KEY,
    simulacion_id            BIGINT        NOT NULL
                             REFERENCES simulaciones_logisticas(id) ON DELETE CASCADE,
    hl_real                  NUMERIC(18,4),
    bultos_real              NUMERIC(18,4),
    pallets_real             NUMERIC(18,4),
    up_real                  NUMERIC(18,4),
    pdv_real                 NUMERIC(18,4),
    salidas_real             NUMERIC(18,4),
    camiones_real            NUMERIC(12,4),
    personas_real            NUMERIC(12,4),
    rechazos_real            NUMERIC(12,4),
    dias_pico_real           SMALLINT,
    ausentismo_real          NUMERIC(8,2),
    dropsize_real            NUMERIC(12,4),
    error_hl_pct             NUMERIC(8,2),
    error_bultos_pct         NUMERIC(8,2),
    error_pallets_pct        NUMERIC(8,2),
    error_pdv_pct            NUMERIC(8,2),
    error_salidas_pct        NUMERIC(8,2),
    error_camiones_pct       NUMERIC(8,2),
    error_personas_pct       NUMERIC(8,2),
    error_rechazos_pct       NUMERIC(8,2),
    conclusiones             TEXT,
    created_at               TIMESTAMP     NOT NULL DEFAULT NOW(),
    UNIQUE (simulacion_id)
);

-- Aprendizaje histórico para ajustar futuras simulaciones
CREATE TABLE IF NOT EXISTS aprendizaje_simulaciones_logisticas (
    id                       BIGSERIAL PRIMARY KEY,
    empresa_id               VARCHAR(50)   NOT NULL DEFAULT '1',
    sucursal_id              VARCHAR(50)   NOT NULL,
    mes                      SMALLINT      NOT NULL CHECK (mes BETWEEN 1 AND 12),
    anio                     SMALLINT      NOT NULL,
    simulacion_id            BIGINT,
    error_hl_pct             NUMERIC(8,2),
    error_camiones_pct       NUMERIC(8,2),
    error_personas_pct       NUMERIC(8,2),
    error_salidas_pct        NUMERIC(8,2),
    factor_ajuste_hl         NUMERIC(8,4),
    factor_ajuste_camiones   NUMERIC(8,4),
    factor_ajuste_personas   NUMERIC(8,4),
    factor_ajuste_salidas    NUMERIC(8,4),
    created_at               TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aprend_suc_mes
    ON aprendizaje_simulaciones_logisticas (empresa_id, sucursal_id, mes);
