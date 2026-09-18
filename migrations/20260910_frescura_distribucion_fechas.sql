ALTER TABLE control_frescura_conteo_items
    ADD COLUMN IF NOT EXISTS distribucion_fechas JSONB NOT NULL DEFAULT '[]'::jsonb;
