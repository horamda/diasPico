"""segmentacion periodos y pesos score

Revision ID: 20260525_seg_periodos
Revises:
Create Date: 2026-05-25
"""

from alembic import op


revision = "20260525_seg_periodos"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS seg_parametros (
            id SERIAL PRIMARY KEY,
            empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
            sucursal_id VARCHAR(50),
            costo_entrega_hl NUMERIC(10,4) NOT NULL DEFAULT 0,
            costo_almacen_hl NUMERIC(10,4) NOT NULL DEFAULT 0,
            percentil_alta NUMERIC(5,4) NOT NULL DEFAULT 0.70,
            percentil_baja NUMERIC(5,4) NOT NULL DEFAULT 0.30,
            umbral_crecimiento NUMERIC(8,4) DEFAULT NULL,
            anio_base SMALLINT NOT NULL DEFAULT 2025,
            anio_ytd SMALLINT NOT NULL DEFAULT 2026,
            mes_ytd_hasta SMALLINT DEFAULT NULL,
            peso_negocio NUMERIC(5,4) NOT NULL DEFAULT 0.35,
            peso_productividad NUMERIC(5,4) NOT NULL DEFAULT 0.20,
            peso_servicio NUMERIC(5,4) NOT NULL DEFAULT 0.20,
            peso_rentabilidad NUMERIC(5,4) NOT NULL DEFAULT 0.15,
            peso_geo NUMERIC(5,4) NOT NULL DEFAULT 0.10,
            activo BOOLEAN NOT NULL DEFAULT TRUE,
            version_regla SMALLINT NOT NULL DEFAULT 1,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_seg_pesos CHECK (
                ABS(peso_negocio + peso_productividad + peso_servicio
                    + peso_rentabilidad + peso_geo - 1.0) < 0.02
            )
        );
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS seg_clientes_atributos (
            cliente VARCHAR(50) PRIMARY KEY,
            sucursal_id VARCHAR(50),
            localidad VARCHAR(100),
            autoelevador BOOLEAN DEFAULT FALSE,
            nps_valor NUMERIC(6,2),
            nps_fecha DATE,
            rmd_valor NUMERIC(6,2),
            rmd_fecha DATE,
            activo BOOLEAN NOT NULL DEFAULT TRUE,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS seg_cliente_cluster_historico (
            id BIGSERIAL PRIMARY KEY,
            cliente VARCHAR(50) NOT NULL,
            descripcion_cliente VARCHAR(255),
            sucursal_id VARCHAR(50),
            localidad VARCHAR(100),
            periodo_anio SMALLINT NOT NULL,
            periodo_mes SMALLINT NOT NULL DEFAULT 0,
            cluster_dpo VARCHAR(50),
            subcluster_logistico VARCHAR(80),
            score_total NUMERIC(6,2),
            dim_negocio NUMERIC(6,2),
            dim_productividad NUMERIC(6,2),
            dim_servicio NUMERIC(6,2),
            dim_rentabilidad NUMERIC(6,2),
            dim_geo NUMERIC(6,2),
            venta_ytd NUMERIC(18,2),
            hl_ytd NUMERIC(18,4),
            crecimiento_pct NUMERIC(10,4),
            costo_logistico_total NUMERIC(18,2),
            ratio_costo_logistico NUMERIC(8,4),
            pedidos_ytd INTEGER,
            dropsize_ytd NUMERIC(10,4),
            pct_rechazo_pedidos NUMERIC(8,4),
            fecha_calculo TIMESTAMP NOT NULL DEFAULT NOW(),
            version_regla SMALLINT NOT NULL DEFAULT 1,
            proceso VARCHAR(100) NOT NULL DEFAULT 'sistema',
            UNIQUE (cliente, periodo_anio, periodo_mes)
        );
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS seg_auditoria (
            id BIGSERIAL PRIMARY KEY,
            accion VARCHAR(100) NOT NULL,
            periodo_anio SMALLINT,
            periodo_mes SMALLINT,
            clientes_procesados INTEGER DEFAULT 0,
            clientes_ganador INTEGER DEFAULT 0,
            clientes_en_crecimiento INTEGER DEFAULT 0,
            clientes_basico INTEGER DEFAULT 0,
            clientes_ventas_bajas INTEGER DEFAULT 0,
            version_regla SMALLINT,
            parametros JSONB,
            ejecutado_por VARCHAR(100) NOT NULL DEFAULT 'sistema',
            ejecutado_at TIMESTAMP NOT NULL DEFAULT NOW(),
            duracion_ms INTEGER,
            error_detalle TEXT
        );
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS seg_periodos_calculo (
            id BIGSERIAL PRIMARY KEY,
            empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
            periodo_anio SMALLINT NOT NULL,
            periodo_mes SMALLINT NOT NULL DEFAULT 0,
            fecha_desde DATE NOT NULL,
            fecha_hasta DATE NOT NULL,
            fecha_base_desde DATE NOT NULL,
            fecha_base_hasta DATE NOT NULL,
            activo BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_seg_periodo_mes CHECK (periodo_mes BETWEEN 0 AND 12),
            CONSTRAINT chk_seg_periodo_rango CHECK (
                fecha_desde <= fecha_hasta
                AND fecha_base_desde <= fecha_base_hasta
            )
        );
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS seg_score_pesos (
            variable VARCHAR(50) PRIMARY KEY,
            dimension VARCHAR(50) NOT NULL,
            peso NUMERIC(8,4) NOT NULL,
            mayor_es_mejor BOOLEAN NOT NULL DEFAULT TRUE,
            activo BOOLEAN NOT NULL DEFAULT TRUE,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_seg_periodos_activo
        ON seg_periodos_calculo(empresa_id, activo, id DESC);
        CREATE INDEX IF NOT EXISTS idx_seg_score_dimension
        ON seg_score_pesos(dimension, activo);
    """)
    op.execute("""
        ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS venta_base_mismo_periodo NUMERIC(18,2);
        ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS bultos_ytd NUMERIC(18,4);
        ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS pallets_ytd NUMERIC(18,4);
        ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS up_ytd NUMERIC(18,4);
        ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS rechazos_ytd NUMERIC(18,4);
        ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS nps_valor NUMERIC(6,2);
        ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS rmd_valor NUMERIC(6,2);
        ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS costo_entrega NUMERIC(18,2);
        ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS costo_almacen NUMERIC(18,2);
        ALTER TABLE seg_cliente_cluster_historico ADD COLUMN IF NOT EXISTS margen_logistico_proxy NUMERIC(18,2);
    """)
    op.execute("""
        INSERT INTO seg_score_pesos(variable, dimension, peso, mayor_es_mejor) VALUES
            ('venta', 'negocio', 15, TRUE),
            ('hl', 'negocio', 10, TRUE),
            ('crecimiento', 'negocio', 10, TRUE),
            ('dropsize', 'productividad', 10, TRUE),
            ('pallets_pedido', 'productividad', 5, TRUE),
            ('autoelevador', 'productividad', 5, TRUE),
            ('rechazos', 'servicio', 10, FALSE),
            ('rmd', 'servicio', 5, TRUE),
            ('nps', 'servicio', 5, TRUE),
            ('ratio_costo', 'rentabilidad', 10, FALSE),
            ('margen', 'rentabilidad', 5, TRUE),
            ('frecuencia', 'geo', 7, TRUE),
            ('localidad', 'geo', 2, TRUE),
            ('sucursal', 'geo', 1, TRUE)
        ON CONFLICT (variable) DO NOTHING;
    """)
    op.execute("""
        INSERT INTO seg_parametros(empresa_id)
        SELECT '1'
        WHERE NOT EXISTS (
            SELECT 1 FROM seg_parametros WHERE empresa_id = '1' AND activo
        );
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS seg_score_pesos;")
    op.execute("DROP TABLE IF EXISTS seg_periodos_calculo;")
