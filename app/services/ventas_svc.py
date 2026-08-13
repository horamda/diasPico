from threading import Lock

from app.database import pg_conn

_VENTAS_DETALLE_READY = False
_VENTAS_DETALLE_LOCK = Lock()


VENTAS_DETALLE_DDL = """
CREATE TABLE IF NOT EXISTS ventas_detalle (
    id BIGSERIAL PRIMARY KEY,
    sucursal VARCHAR(50),
    empresa VARCHAR(50),
    documento VARCHAR(50),
    letra VARCHAR(20),
    serie VARCHAR(20),
    numero VARCHAR(50),
    detalle_documento VARCHAR(100),
    sin_cargo VARCHAR(20),
    id_articulo INTEGER,
    descripcion_articulo VARCHAR(255),
    descripcion_detallada_articulo VARCHAR(255),
    bultos NUMERIC,
    bultos_rechazados NUMERIC,
    importe_neto NUMERIC,
    importe_neto_rechazado NUMERIC,
    unidad_medida NUMERIC,
    unidad_medida_rechazado NUMERIC,
    unidad_paquete NUMERIC,
    unidad_paquete_rechazado NUMERIC,
    fecha DATE,
    rechazo_codigo VARCHAR(50),
    motivo_rechazo VARCHAR(255),
    descripcion_detallada_motivo VARCHAR(255),
    cliente VARCHAR(50),
    descripcion_cliente VARCHAR(255),
    descripcion_detallada_cliente VARCHAR(255),
    domicilio_cliente VARCHAR(255),
    canal VARCHAR(50),
    descripcion_canal VARCHAR(100),
    descripcion_detallada_canal VARCHAR(255),
    vendedor VARCHAR(50),
    descripcion_vendedor VARCHAR(100),
    descripcion_detallada_vendedor VARCHAR(255),
    ruta VARCHAR(50),
    descripcion_ruta VARCHAR(100),
    descripcion_detallada_ruta VARCHAR(255),
    supervisor VARCHAR(50),
    descripcion_supervisor VARCHAR(100),
    descripcion_detallada_supervisor VARCHAR(255),
    chofer VARCHAR(50),
    descripcion_chofer VARCHAR(100),
    descripcion_detallada_chofer VARCHAR(255),
    transporte VARCHAR(50),
    descripcion_transporte VARCHAR(100),
    descripcion_detallada_transporte VARCHAR(255),
    division VARCHAR(50),
    descripcion_division VARCHAR(100),
    unidad_negocio VARCHAR(50),
    descripcion_unidad_negocio VARCHAR(100),
    origen VARCHAR(50),
    rechazo_total VARCHAR(20),
    creado TIMESTAMP DEFAULT NOW()
)
"""


def ensure_ventas_detalle_table() -> None:
    global _VENTAS_DETALLE_READY
    if _VENTAS_DETALLE_READY:
        return
    with _VENTAS_DETALLE_LOCK:
        if _VENTAS_DETALLE_READY:
            return
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(2026052503)")
                cur.execute(f"""
                    {VENTAS_DETALLE_DDL};
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS empresa VARCHAR(50);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS letra VARCHAR(20);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS sin_cargo VARCHAR(20);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS descripcion_detallada_articulo VARCHAR(255);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS importe_neto_rechazado NUMERIC;
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS unidad_paquete NUMERIC;
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS unidad_paquete_rechazado NUMERIC;
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS rechazo_codigo VARCHAR(50);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS descripcion_detallada_motivo VARCHAR(255);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS descripcion_detallada_cliente VARCHAR(255);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS domicilio_cliente VARCHAR(255);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS descripcion_detallada_canal VARCHAR(255);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS descripcion_detallada_vendedor VARCHAR(255);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS descripcion_detallada_ruta VARCHAR(255);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS descripcion_detallada_supervisor VARCHAR(255);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS chofer VARCHAR(50);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS descripcion_chofer VARCHAR(100);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS descripcion_detallada_chofer VARCHAR(255);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS descripcion_transporte VARCHAR(100);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS descripcion_detallada_transporte VARCHAR(255);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS division VARCHAR(50);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS descripcion_division VARCHAR(100);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS unidad_negocio VARCHAR(50);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS descripcion_unidad_negocio VARCHAR(100);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS origen VARCHAR(50);
                    ALTER TABLE ventas_detalle ADD COLUMN IF NOT EXISTS rechazo_total VARCHAR(20);
                    CREATE INDEX IF NOT EXISTS idx_ventas_detalle_fecha ON ventas_detalle(fecha);
                    CREATE INDEX IF NOT EXISTS idx_ventas_detalle_sucursal ON ventas_detalle(sucursal);
                    CREATE INDEX IF NOT EXISTS idx_ventas_detalle_sucursal_fecha ON ventas_detalle(sucursal, fecha);
                    CREATE INDEX IF NOT EXISTS idx_ventas_detalle_fecha_sucursal ON ventas_detalle(fecha, sucursal);
                    CREATE INDEX IF NOT EXISTS idx_ventas_detalle_suc_fecha_cliente ON ventas_detalle(sucursal, fecha, cliente);
                    CREATE INDEX IF NOT EXISTS idx_ventas_detalle_fecha_cliente ON ventas_detalle(fecha, cliente);
                    CREATE INDEX IF NOT EXISTS idx_ventas_detalle_articulo ON ventas_detalle(id_articulo);
                    CREATE INDEX IF NOT EXISTS idx_ventas_detalle_motivo ON ventas_detalle(motivo_rechazo);
                    CREATE INDEX IF NOT EXISTS idx_ventas_detalle_documento_codigo ON ventas_detalle(documento);
                    CREATE INDEX IF NOT EXISTS idx_ventas_detalle_documento ON ventas_detalle(detalle_documento);
                    CREATE INDEX IF NOT EXISTS idx_ventas_detalle_empresa ON ventas_detalle(empresa);
                    CREATE INDEX IF NOT EXISTS idx_ventas_detalle_cliente ON ventas_detalle(cliente);
                    CREATE INDEX IF NOT EXISTS idx_ventas_detalle_portal_suc_fecha
                        ON ventas_detalle(sucursal, fecha)
                        INCLUDE (unidad_medida, bultos, cliente, detalle_documento, documento, id_articulo,
                                 unidad_medida_rechazado, bultos_rechazados, unidad_paquete, motivo_rechazo,
                                 rechazo_total, origen);
                """)
        _VENTAS_DETALLE_READY = True
