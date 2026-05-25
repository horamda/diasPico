from app.database import pg_conn

_TRANSPORTES_READY = False


TRANSPORTES_DDL = """
CREATE TABLE IF NOT EXISTS transportes (
    codigo                      INTEGER PRIMARY KEY,
    descripcion                 VARCHAR(255),
    marca                       VARCHAR(100),
    modelo                      VARCHAR(100),
    placa                       VARCHAR(30),
    carga_maxima_kg             NUMERIC,
    capacidad_up                NUMERIC,
    propio                      BOOLEAN,
    sucursal                    VARCHAR(50),
    deposito_defecto            INTEGER,
    descripcion_deposito_defecto VARCHAR(255),
    anulado                     BOOLEAN,
    actualizado                 TIMESTAMP DEFAULT NOW()
)
"""

# Columnas que ya no se usan y deben eliminarse si existen en la BD
_COLS_A_ELIMINAR = [
    'placa_remolque', 'cert_inscripcion', 'lic_conductor',
    'costo_por_dia', 'proveedor_relacionado', 'descripcion_proveedor',
    'destino', 'cod_cliente', 'razon_social', 'maximo_pdvs',
    'plantillas_pend_liq', 'antiguedad_max_carga', 'cod_comision',
    'min_comision_por_dia', 'comision_varia_segun_cliente',
    'abona_comision_sobre_merc', 'descuenta_comision_liq', 'modalidad',
    'vendedor_asociado', 'proceso_liq_abreviado', 'deposito_asociado',
    'descripcion_deposito_asociado', 'cod_chofer', 'chofer',
    'cod_ayudante_1', 'ayudante_1', 'cod_ayudante_2', 'ayudante_2',
]


def ensure_transportes_table() -> None:
    global _TRANSPORTES_READY
    if _TRANSPORTES_READY:
        return
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                {TRANSPORTES_DDL};
                CREATE INDEX IF NOT EXISTS idx_transportes_placa    ON transportes(placa);
                CREATE INDEX IF NOT EXISTS idx_transportes_sucursal ON transportes(sucursal);
                CREATE INDEX IF NOT EXISTS idx_transportes_anulado  ON transportes(anulado);
            """)
            # Eliminar columnas obsoletas si la tabla ya existía con el esquema viejo
            for col in _COLS_A_ELIMINAR:
                cur.execute(f"ALTER TABLE transportes DROP COLUMN IF EXISTS {col}")
    _TRANSPORTES_READY = True
