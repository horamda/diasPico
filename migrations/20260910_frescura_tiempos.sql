
CREATE TABLE IF NOT EXISTS control_frescura_sesiones (
    id BIGSERIAL PRIMARY KEY,
    sucursal VARCHAR(20) NOT NULL,
    fecha DATE NOT NULL,
    responsable VARCHAR(120) NOT NULL,
    iniciado_at TIMESTAMPTZ NOT NULL,
    activo_desde TIMESTAMPTZ,
    finalizado_at TIMESTAMPTZ,
    segundos_activos NUMERIC NOT NULL DEFAULT 0,
    estado VARCHAR(20) NOT NULL DEFAULT 'activo',
    borrador JSONB NOT NULL DEFAULT '{}'::jsonb,
    conteo_id BIGINT REFERENCES control_frescura_conteos(id),
    UNIQUE(sucursal, fecha, responsable)
);
ALTER TABLE control_frescura_conteos ADD COLUMN IF NOT EXISTS iniciado_at TIMESTAMPTZ;
ALTER TABLE control_frescura_conteos ADD COLUMN IF NOT EXISTS finalizado_at TIMESTAMPTZ;
ALTER TABLE control_frescura_conteos ADD COLUMN IF NOT EXISTS segundos_activos NUMERIC;
ALTER TABLE control_frescura_conteos ADD COLUMN IF NOT EXISTS segundos_transcurridos NUMERIC;
