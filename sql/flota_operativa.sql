-- Modulo: Flota operativa
-- Base de datos objetivo en este proyecto: PostgreSQL / Railway.
--
-- TODO FK: cuando existan tablas maestras empresas y sucursales, agregar:
--   empresa_id  -> empresas(id)
--   sucursal_id -> sucursales(id)

CREATE TABLE IF NOT EXISTS flota_vehiculos (
    id BIGSERIAL PRIMARY KEY,
    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50) NOT NULL,
    codigo VARCHAR(50) NOT NULL,
    descripcion VARCHAR(200) NOT NULL,
    marca VARCHAR(80),
    modelo VARCHAR(80),
    placa VARCHAR(50),
    carga_maxima_kg NUMERIC(12,2),
    capacidad_up NUMERIC(12,2),
    propio BOOLEAN NOT NULL DEFAULT TRUE,
    deposito_default_id VARCHAR(50),
    deposito_default_nombre VARCHAR(120),
    anulado BOOLEAN NOT NULL DEFAULT FALSE,
    activo_base BOOLEAN NOT NULL DEFAULT TRUE,
    fuente VARCHAR(50) NOT NULL DEFAULT 'MANUAL',
    observaciones TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, codigo)
);

CREATE TABLE IF NOT EXISTS flota_disponibilidad_mensual (
    id BIGSERIAL PRIMARY KEY,
    vehiculo_id BIGINT NOT NULL REFERENCES flota_vehiculos(id) ON DELETE CASCADE,
    empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50) NOT NULL,
    anio SMALLINT NOT NULL CHECK (anio BETWEEN 2020 AND 2100),
    mes SMALLINT NOT NULL CHECK (mes BETWEEN 1 AND 12),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    motivo VARCHAR(120),
    observaciones TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (vehiculo_id, anio, mes)
);

CREATE INDEX IF NOT EXISTS idx_flota_vehiculos_emp_suc
    ON flota_vehiculos(empresa_id, sucursal_id, anulado, activo_base);
CREATE INDEX IF NOT EXISTS idx_flota_vehiculos_placa
    ON flota_vehiculos(placa);
CREATE INDEX IF NOT EXISTS idx_flota_disp_periodo
    ON flota_disponibilidad_mensual(empresa_id, sucursal_id, anio, mes, activo);
CREATE INDEX IF NOT EXISTS idx_flota_disp_vehiculo_periodo
    ON flota_disponibilidad_mensual(vehiculo_id, anio, mes);

-- Seed inicial tomado de la captura enviada por el usuario.
-- No sobrescribe filas existentes para no pisar correcciones manuales posteriores.
INSERT INTO flota_vehiculos (
    empresa_id, sucursal_id, codigo, descripcion, marca, modelo, placa,
    carga_maxima_kg, capacidad_up, propio, deposito_default_id,
    deposito_default_nombre, anulado, activo_base, fuente
) VALUES
    ('1', '1', '1100', '(19) IVECO TECTOR (KTO613)', 'IVECO', '2018', 'KTO613', 18000, 700, TRUE, '1', 'CASA CENTRAL', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '1', '1101', '(11) DEUTZ DINAMIC (SBW518)', 'DEUTZ', '2000', 'SBW518', 5000, 300, TRUE, '1', 'CASA CENTRAL', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '1', '1102', '(12) DEUTZ STARK (AJP716)', 'DEUTZ', '2001', 'AJP716', 5000, 300, TRUE, '1', 'CASA CENTRAL', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '1', '1103', '(13) CHEVROLET NPR (BUX670)', 'CHEVROLET', '1997', 'BUX670', 6000, 400, TRUE, '1', 'CASA CENTRAL', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '1', '1104', '(10) MERCEDES 1112 (XAH510)', 'MERCEDES', '1969', 'XAH510', 7500, 400, TRUE, '1', 'CASA CENTRAL', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '1', '1105', '(03) IVECO 170E28 (AF186WY)', 'IVECO', '2022', 'AF186WY', 11400, 600, TRUE, '1', 'CASA CENTRAL', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '1', '1106', '(05) IVECO 170E28 (AF186WG)', 'IVECO', '2022', 'AF186WG', 11400, 600, TRUE, '1', 'CASA CENTRAL', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '1', '1112', '(18) IVECO TECTOR (AD330VW)', 'IVECO', '2018', 'AD330VW', 11400, 500, TRUE, '1', 'CASA CENTRAL', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '1', '1114', '(21) FORD 6000 (RYO641)', 'FORD', '1979', 'RYO641', 6000, 350, TRUE, '1', 'CASA CENTRAL', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '1', '1201', '(14) CHEVROLET NPR (CNV005)', 'CHEVROLET', '1998', 'CNV005', 6000, 400, TRUE, '1', 'CASA CENTRAL', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '1', '1203', '(25) IVECO TECTOR (OGG322)', 'IVECO', '2015', 'OGG322', 11400, 600, TRUE, '1', 'CASA CENTRAL', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '1', '1204', '(26) IVECO TECTOR (PIV845)', 'IVECO', '2016', 'PIV845', 11400, 600, TRUE, '1', 'CASA CENTRAL', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '1', '1205', '(23) MERCEDES 1114 (RMY742)', 'MERCEDES', '1976', 'RMY742', 7500, 400, TRUE, '1', 'CASA CENTRAL', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '1', '1211', '(22) FORD 7000 (XCT863)', 'FORD', '1979', 'XCT863', NULL, 350, TRUE, '1', 'CASA CENTRAL', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '1', '1307', '(04) IVECO TECTOR (HPU754)', 'IVECO', '2007', 'HPU754', 11400, 500, TRUE, '1', 'CASA CENTRAL', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '1', '1610', 'KANGOO GRIS', 'RENAULT', '2009', 'IBK258', 800, 25, TRUE, '1', 'CASA CENTRAL', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '1', '1611', 'FIORINO CENTRAL (AC668HU)', 'FIAT', '2018', 'AC668HU', 850, 25, TRUE, '1', 'CASA CENTRAL', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '2', '1110', '(02) IVECO TECTOR (AF021EJ)', 'IVECO', '2022', 'AF021EJ', 11400, 500, TRUE, '4', 'DEPOSITO DOLORES', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '2', '1202', '(24) IVECO ATTACK (MKC473)', 'IVECO', '2013', 'MKC473', 11400, 500, TRUE, '4', 'DEPOSITO DOLORES', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '2', '1301', '(15) MERCEDES 710 (DSB034)', 'MERCEDES', '2001', 'DSB034', 6000, 300, TRUE, '4', 'DEPOSITO DOLORES', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '2', '1302', '(16) MERCEDES 710 (DXF665)', 'MERCEDES', '2001', 'DXF665', 6000, 400, TRUE, '4', 'DEPOSITO DOLORES', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '2', '1303', 'FIORINO DOLORES (AC668HT)', 'FIAT', '2018', 'AC668HT', 850, 25, TRUE, '4', 'DEPOSITO DOLORES', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '2', '1306', '(06) IVECO TECTOR (HPU756)', 'IVECO', '2007', 'HPU756', 11400, 500, TRUE, '4', 'DEPOSITO DOLORES', FALSE, TRUE, 'CAPTURA_FLOTA'),
    ('1', '2', '1403', '(08) IVECO TECTOR (AF071AX)', 'IVECO', '2022', 'AF071AX', 11400, 500, TRUE, '4', 'DEPOSITO DOLORES', FALSE, TRUE, 'CAPTURA_FLOTA')
ON CONFLICT (empresa_id, codigo) DO NOTHING;
