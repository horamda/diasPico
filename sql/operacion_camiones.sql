-- Módulo: Operación de camiones (datos reales del Google Sheets)
-- Cada fila = un camión que salió en una fecha determinada.
-- nro_salida: 1 = primera salida (datos), 2 = segunda salida (recargas)

CREATE TABLE IF NOT EXISTS operacion_camiones (
    id          BIGSERIAL PRIMARY KEY,
    empresa_id  VARCHAR(20)  NOT NULL DEFAULT '1',
    sucursal_id VARCHAR(50)  NOT NULL,
    fecha       DATE         NOT NULL,
    nro_salida  SMALLINT     NOT NULL,
    chofer      VARCHAR(120) NOT NULL,
    ayudante_1  VARCHAR(120),
    ayudante_2  VARCHAR(120),
    sync_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, sucursal_id, fecha, nro_salida, chofer)
);

CREATE INDEX IF NOT EXISTS ix_op_cam_fecha
    ON operacion_camiones (sucursal_id, fecha);
