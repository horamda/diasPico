-- Modulo: Planificacion Operativa por Dias Pico
-- Base de datos objetivo en este proyecto: PostgreSQL / Railway.
--
-- TODO FK: cuando existan tablas maestras empresas y sucursales, agregar:
--   empresa_id  -> empresas(id)
--   sucursal_id -> sucursales(id)

CREATE TABLE IF NOT EXISTS factor_estacionalidad (
    id BIGSERIAL PRIMARY KEY,
    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50),
    mes SMALLINT NOT NULL CHECK (mes BETWEEN 1 AND 12),
    factor_hl NUMERIC(12,4) NOT NULL DEFAULT 1.0000,
    factor_pdv NUMERIC(12,4) NOT NULL DEFAULT 1.0000,
    factor_salidas NUMERIC(12,4) NOT NULL DEFAULT 1.0000,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, sucursal_id, mes)
);

CREATE TABLE IF NOT EXISTS planificacion_variables (
    id BIGSERIAL PRIMARY KEY,
    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50),
    codigo VARCHAR(50) NOT NULL,
    nombre VARCHAR(120) NOT NULL,
    categoria VARCHAR(80),
    unidad VARCHAR(30),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, sucursal_id, codigo)
);

CREATE TABLE IF NOT EXISTS planificacion_variables_valores (
    id BIGSERIAL PRIMARY KEY,
    variable_id BIGINT NOT NULL REFERENCES planificacion_variables(id) ON DELETE CASCADE,
    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50) NOT NULL,
    fecha DATE NOT NULL,
    valor NUMERIC(18,4),
    origen VARCHAR(50) NOT NULL DEFAULT 'MANUAL',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (variable_id, empresa_id, sucursal_id, fecha, origen)
);

CREATE TABLE IF NOT EXISTS planificacion_estadistica_diaria (
    id BIGSERIAL PRIMARY KEY,
    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50) NOT NULL,
    fecha DATE NOT NULL,
    anio SMALLINT NOT NULL,
    mes SMALLINT NOT NULL CHECK (mes BETWEEN 1 AND 12),
    dia SMALLINT NOT NULL CHECK (dia BETWEEN 1 AND 31),
    hl NUMERIC(18,4) NOT NULL DEFAULT 0,
    bultos NUMERIC(18,4) NOT NULL DEFAULT 0,
    pallets NUMERIC(18,4) NOT NULL DEFAULT 0,
    rechazos_pct NUMERIC(12,4) NOT NULL DEFAULT 0,
    salidas INTEGER NOT NULL DEFAULT 0,
    pdv_unicos INTEGER NOT NULL DEFAULT 0,
    camiones_promedio NUMERIC(12,4) NOT NULL DEFAULT 0,
    camiones_pico NUMERIC(12,4) NOT NULL DEFAULT 0,
    empleados_normales NUMERIC(12,4) NOT NULL DEFAULT 0,
    empleados_pico NUMERIC(12,4) NOT NULL DEFAULT 0,
    es_dia_pico BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, sucursal_id, fecha)
);

CREATE TABLE IF NOT EXISTS planificacion_picos (
    id BIGSERIAL PRIMARY KEY,
    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50) NOT NULL,
    anio_plan SMALLINT NOT NULL,
    mes_plan SMALLINT NOT NULL CHECK (mes_plan BETWEEN 1 AND 12),
    anio_base SMALLINT NOT NULL,
    mes_base SMALLINT NOT NULL CHECK (mes_base BETWEEN 1 AND 12),
    hl_base NUMERIC(18,4) NOT NULL DEFAULT 0,
    dias_pico_base NUMERIC(12,4) NOT NULL DEFAULT 0,
    rechazos_pct_base NUMERIC(12,4) NOT NULL DEFAULT 0,
    salidas_base NUMERIC(18,4) NOT NULL DEFAULT 0,
    pdv_unicos_base NUMERIC(18,4) NOT NULL DEFAULT 0,
    camiones_promedio_base NUMERIC(12,4) NOT NULL DEFAULT 0,
    camiones_pico_base NUMERIC(12,4) NOT NULL DEFAULT 0,
    empleados_normal_base NUMERIC(12,4) NOT NULL DEFAULT 0,
    empleados_pico_base NUMERIC(12,4) NOT NULL DEFAULT 0,
    factor_hl NUMERIC(12,4) NOT NULL DEFAULT 1.0000,
    factor_pdv NUMERIC(12,4) NOT NULL DEFAULT 1.0000,
    factor_salidas NUMERIC(12,4) NOT NULL DEFAULT 1.0000,
    factor_rechazos NUMERIC(12,4) NOT NULL DEFAULT 1.0000,
    factor_dias_pico NUMERIC(12,4) NOT NULL DEFAULT 1.0000,
    factor_camiones NUMERIC(12,4) NOT NULL DEFAULT 1.0000,
    factor_empleados NUMERIC(12,4) NOT NULL DEFAULT 1.0000,
    hl_plan NUMERIC(18,4) NOT NULL DEFAULT 0,
    dias_pico_plan NUMERIC(12,4) NOT NULL DEFAULT 0,
    rechazos_pct_plan NUMERIC(12,4) NOT NULL DEFAULT 0,
    salidas_plan NUMERIC(18,4) NOT NULL DEFAULT 0,
    pdv_unicos_plan NUMERIC(18,4) NOT NULL DEFAULT 0,
    camiones_promedio_plan NUMERIC(12,4) NOT NULL DEFAULT 0,
    camiones_pico_plan NUMERIC(12,4) NOT NULL DEFAULT 0,
    empleados_normal_plan NUMERIC(12,4) NOT NULL DEFAULT 0,
    empleados_pico_plan NUMERIC(12,4) NOT NULL DEFAULT 0,
    estado VARCHAR(20) NOT NULL DEFAULT 'PLANIFICADO',
    metodo_distribucion VARCHAR(40) NOT NULL DEFAULT 'CALENDARIO_OPERATIVO',
    observaciones TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, sucursal_id, anio_plan, mes_plan)
);

CREATE TABLE IF NOT EXISTS planificacion_variables_plan (
    id BIGSERIAL PRIMARY KEY,
    planificacion_id BIGINT NOT NULL REFERENCES planificacion_picos(id) ON DELETE CASCADE,
    variable_id BIGINT NOT NULL REFERENCES planificacion_variables(id) ON DELETE CASCADE,
    valor_base NUMERIC(18,4),
    valor_plan NUMERIC(18,4),
    valor_real NUMERIC(18,4),
    desvio NUMERIC(12,4),
    impacto NUMERIC(12,4),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (planificacion_id, variable_id)
);

CREATE TABLE IF NOT EXISTS planificacion_picos_real (
    id BIGSERIAL PRIMARY KEY,
    planificacion_id BIGINT NOT NULL REFERENCES planificacion_picos(id) ON DELETE CASCADE,
    fecha_actualizacion DATE NOT NULL DEFAULT CURRENT_DATE,
    hl_real NUMERIC(18,4) NOT NULL DEFAULT 0,
    dias_pico_real NUMERIC(12,4) NOT NULL DEFAULT 0,
    rechazos_pct_real NUMERIC(12,4) NOT NULL DEFAULT 0,
    salidas_real NUMERIC(18,4) NOT NULL DEFAULT 0,
    pdv_unicos_real NUMERIC(18,4) NOT NULL DEFAULT 0,
    camiones_promedio_real NUMERIC(12,4) NOT NULL DEFAULT 0,
    camiones_pico_real NUMERIC(12,4) NOT NULL DEFAULT 0,
    empleados_normal_real NUMERIC(12,4) NOT NULL DEFAULT 0,
    empleados_pico_real NUMERIC(12,4) NOT NULL DEFAULT 0,
    desvio_hl_pct NUMERIC(12,4) NOT NULL DEFAULT 0,
    desvio_dias_pico_pct NUMERIC(12,4) NOT NULL DEFAULT 0,
    desvio_rechazos_pct NUMERIC(12,4) NOT NULL DEFAULT 0,
    desvio_salidas_pct NUMERIC(12,4) NOT NULL DEFAULT 0,
    desvio_pdv_pct NUMERIC(12,4) NOT NULL DEFAULT 0,
    desvio_camiones_pct NUMERIC(12,4) NOT NULL DEFAULT 0,
    desvio_empleados_pct NUMERIC(12,4) NOT NULL DEFAULT 0,
    estado_general VARCHAR(20) NOT NULL DEFAULT 'NORMAL',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (planificacion_id)
);

CREATE TABLE IF NOT EXISTS planificacion_picos_dias (
    id BIGSERIAL PRIMARY KEY,
    planificacion_id BIGINT NOT NULL REFERENCES planificacion_picos(id) ON DELETE CASCADE,
    fecha DATE NOT NULL,
    dia_semana SMALLINT NOT NULL CHECK (dia_semana BETWEEN 0 AND 6),
    hl_plan NUMERIC(18,4) NOT NULL DEFAULT 0,
    hl_real NUMERIC(18,4) NOT NULL DEFAULT 0,
    salidas_plan NUMERIC(18,4) NOT NULL DEFAULT 0,
    salidas_real NUMERIC(18,4) NOT NULL DEFAULT 0,
    pdv_plan NUMERIC(18,4) NOT NULL DEFAULT 0,
    pdv_real NUMERIC(18,4) NOT NULL DEFAULT 0,
    es_pico_planificado BOOLEAN NOT NULL DEFAULT FALSE,
    es_pico_real BOOLEAN NOT NULL DEFAULT FALSE,
    camiones_plan NUMERIC(12,4) NOT NULL DEFAULT 0,
    camiones_real NUMERIC(12,4) NOT NULL DEFAULT 0,
    empleados_plan NUMERIC(12,4) NOT NULL DEFAULT 0,
    empleados_real NUMERIC(12,4) NOT NULL DEFAULT 0,
    estado VARCHAR(20) NOT NULL DEFAULT 'NORMAL',
    fecha_base DATE,
    criterio_asignacion VARCHAR(80),
    score_asignacion NUMERIC(12,4) NOT NULL DEFAULT 0,
    observaciones TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (planificacion_id, fecha)
);

CREATE TABLE IF NOT EXISTS planificacion_picos_escenarios (
    id BIGSERIAL PRIMARY KEY,
    planificacion_id BIGINT NOT NULL REFERENCES planificacion_picos(id) ON DELETE CASCADE,
    nombre VARCHAR(120) NOT NULL,
    tipo VARCHAR(20) NOT NULL DEFAULT 'MANUAL',
    activo BOOLEAN NOT NULL DEFAULT FALSE,
    hl_plan NUMERIC(18,4) NOT NULL DEFAULT 0,
    dias_pico_plan NUMERIC(12,4) NOT NULL DEFAULT 0,
    rechazos_pct_plan NUMERIC(12,4) NOT NULL DEFAULT 0,
    salidas_plan NUMERIC(18,4) NOT NULL DEFAULT 0,
    pdv_unicos_plan NUMERIC(18,4) NOT NULL DEFAULT 0,
    camiones_promedio_plan NUMERIC(12,4) NOT NULL DEFAULT 0,
    camiones_pico_plan NUMERIC(12,4) NOT NULL DEFAULT 0,
    empleados_normal_plan NUMERIC(12,4) NOT NULL DEFAULT 0,
    empleados_pico_plan NUMERIC(12,4) NOT NULL DEFAULT 0,
    observaciones TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (planificacion_id, nombre)
);

CREATE TABLE IF NOT EXISTS configuracion_picos (
    id BIGSERIAL PRIMARY KEY,
    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50),
    umbral_pico_hl_pct NUMERIC(12,4) NOT NULL DEFAULT 20,
    umbral_pico_salidas_pct NUMERIC(12,4) NOT NULL DEFAULT 20,
    umbral_pico_pdv_pct NUMERIC(12,4) NOT NULL DEFAULT 20,
    umbral_alerta_desvio_pct NUMERIC(12,4) NOT NULL DEFAULT 15,
    umbral_critico_desvio_pct NUMERIC(12,4) NOT NULL DEFAULT 30,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, sucursal_id)
);

CREATE TABLE IF NOT EXISTS capacidad_operativa (
    id BIGSERIAL PRIMARY KEY,
    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50) NOT NULL,
    fecha DATE NOT NULL,
    camiones_disponibles NUMERIC(12,4) NOT NULL DEFAULT 0,
    choferes NUMERIC(12,4) NOT NULL DEFAULT 0,
    acompanantes NUMERIC(12,4) NOT NULL DEFAULT 0,
    operarios_almacen NUMERIC(12,4) NOT NULL DEFAULT 0,
    capacidad_hl NUMERIC(18,4) NOT NULL DEFAULT 0,
    capacidad_pallets NUMERIC(18,4) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, sucursal_id, fecha)
);

CREATE INDEX IF NOT EXISTS idx_factor_est_emp_suc_mes
    ON factor_estacionalidad(empresa_id, sucursal_id, mes, activo);
CREATE INDEX IF NOT EXISTS idx_plan_variables_emp_suc_codigo
    ON planificacion_variables(empresa_id, sucursal_id, codigo, activo);
CREATE INDEX IF NOT EXISTS idx_plan_var_valores_periodo
    ON planificacion_variables_valores(variable_id, empresa_id, sucursal_id, fecha);
CREATE INDEX IF NOT EXISTS idx_plan_variables_plan_plan
    ON planificacion_variables_plan(planificacion_id, variable_id);
CREATE INDEX IF NOT EXISTS idx_plan_est_emp_suc_anio_mes
    ON planificacion_estadistica_diaria(empresa_id, sucursal_id, anio, mes);
CREATE INDEX IF NOT EXISTS idx_plan_est_fecha
    ON planificacion_estadistica_diaria(fecha);
CREATE INDEX IF NOT EXISTS idx_plan_picos_emp_suc_periodo
    ON planificacion_picos(empresa_id, sucursal_id, anio_plan, mes_plan);
CREATE INDEX IF NOT EXISTS idx_plan_real_plan
    ON planificacion_picos_real(planificacion_id);
CREATE INDEX IF NOT EXISTS idx_plan_dias_plan_fecha
    ON planificacion_picos_dias(planificacion_id, fecha);
CREATE UNIQUE INDEX IF NOT EXISTS idx_plan_escenario_activo
    ON planificacion_picos_escenarios(planificacion_id)
    WHERE activo;
CREATE INDEX IF NOT EXISTS idx_plan_escenarios_plan
    ON planificacion_picos_escenarios(planificacion_id, activo);
CREATE INDEX IF NOT EXISTS idx_config_picos_emp_suc
    ON configuracion_picos(empresa_id, sucursal_id, activo);
CREATE INDEX IF NOT EXISTS idx_capacidad_emp_suc_fecha
    ON capacidad_operativa(empresa_id, sucursal_id, fecha);

ALTER TABLE planificacion_picos
    ADD COLUMN IF NOT EXISTS metodo_distribucion VARCHAR(40) NOT NULL DEFAULT 'CALENDARIO_OPERATIVO';

ALTER TABLE planificacion_picos_dias
    ADD COLUMN IF NOT EXISTS fecha_base DATE,
    ADD COLUMN IF NOT EXISTS criterio_asignacion VARCHAR(80),
    ADD COLUMN IF NOT EXISTS score_asignacion NUMERIC(12,4) NOT NULL DEFAULT 0;

-- Pesos configurables para deteccion de dias pico (pico_score)
ALTER TABLE configuracion_picos
    ADD COLUMN IF NOT EXISTS peso_pico_hl      NUMERIC(6,4) NOT NULL DEFAULT 0.45,
    ADD COLUMN IF NOT EXISTS peso_pico_salidas NUMERIC(6,4) NOT NULL DEFAULT 0.30,
    ADD COLUMN IF NOT EXISTS peso_pico_pdv     NUMERIC(6,4) NOT NULL DEFAULT 0.20;

-- Estacionalidad de recursos (camiones y empleados) igual que HL/PDV/salidas
ALTER TABLE factor_estacionalidad
    ADD COLUMN IF NOT EXISTS factor_camiones  NUMERIC(12,4) NOT NULL DEFAULT 1.0000,
    ADD COLUMN IF NOT EXISTS factor_empleados NUMERIC(12,4) NOT NULL DEFAULT 1.0000;

-- Configuracion de capacidad mensual: cuantos camiones/choferes/ayudantes hay disponibles
-- cada mes. Al guardar se propaga automaticamente a capacidad_operativa dia a dia.
CREATE TABLE IF NOT EXISTS capacidad_mensual (
    id                  BIGSERIAL PRIMARY KEY,
    empresa_id          VARCHAR(50)   NOT NULL DEFAULT '1',
    sucursal_id         VARCHAR(50)   NOT NULL,
    anio                SMALLINT      NOT NULL CHECK (anio BETWEEN 2020 AND 2100),
    mes                 SMALLINT      NOT NULL CHECK (mes BETWEEN 1 AND 12),
    camiones_disponibles INTEGER       NOT NULL DEFAULT 0,
    choferes            INTEGER       NOT NULL DEFAULT 0,
    ayudantes           INTEGER       NOT NULL DEFAULT 0,
    capacidad_hl        NUMERIC(18,4) NOT NULL DEFAULT 0,
    observaciones       TEXT,
    updated_at          TIMESTAMP     NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, sucursal_id, anio, mes)
);

CREATE INDEX IF NOT EXISTS idx_capacidad_mensual_emp_suc_periodo
    ON capacidad_mensual(empresa_id, sucursal_id, anio, mes);

-- Columnas para datos reales de camiones y recargas desde Google Sheets
ALTER TABLE planificacion_estadistica_diaria
    ADD COLUMN IF NOT EXISTS camiones_reales    INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS recargas_count     INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS personas_recargas  INTEGER NOT NULL DEFAULT 0;

-- Variables iniciales para ICM dinamico. TODO: cuando exista maestro empresas/sucursales,
-- mover estas semillas a configuracion por empresa.
INSERT INTO planificacion_variables (empresa_id, sucursal_id, codigo, nombre, categoria, unidad, activo, updated_at)
VALUES
    ('1', 'TODAS', 'HL', 'Hectolitros', 'VOLUMEN', 'HL', TRUE, NOW()),
    ('1', 'TODAS', 'PICOS', 'Dias pico', 'OPERACION', 'DIAS', TRUE, NOW()),
    ('1', 'TODAS', 'RECHAZOS', 'Rechazos', 'CALIDAD', 'PCT', TRUE, NOW()),
    ('1', 'TODAS', 'SALIDAS', 'Salidas', 'DISTRIBUCION', 'CANT', TRUE, NOW()),
    ('1', 'TODAS', 'PDV', 'PDV unicos', 'CLIENTES', 'CANT', TRUE, NOW()),
    ('1', 'TODAS', 'CAMIONES', 'Camiones promedio', 'RECURSOS', 'CANT', TRUE, NOW()),
    ('1', 'TODAS', 'EMPLEADOS', 'Empleados normales', 'RECURSOS', 'CANT', TRUE, NOW())
ON CONFLICT (empresa_id, sucursal_id, codigo) DO UPDATE SET
    nombre=EXCLUDED.nombre,
    categoria=EXCLUDED.categoria,
    unidad=EXCLUDED.unidad,
    activo=EXCLUDED.activo,
    updated_at=NOW();
