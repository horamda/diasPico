"""segmentacion cache e indices de eficiencia

Revision ID: 20260525_seg_cache_idx
Revises: 20260525_seg_periodos
Create Date: 2026-05-25
"""

from alembic import op


revision = "20260525_seg_cache_idx"
down_revision = "20260525_seg_periodos"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS seg_schema_version (
            component VARCHAR(80) PRIMARY KEY,
            version VARCHAR(120) NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_seg_params_activo
        ON seg_parametros(activo, empresa_id);

        CREATE INDEX IF NOT EXISTS idx_seg_cli_suc
        ON seg_clientes_atributos(sucursal_id);

        CREATE INDEX IF NOT EXISTS idx_seg_cli_loc
        ON seg_clientes_atributos(localidad);

        CREATE INDEX IF NOT EXISTS idx_seg_hist_cli
        ON seg_cliente_cluster_historico(cliente);

        CREATE INDEX IF NOT EXISTS idx_seg_hist_per
        ON seg_cliente_cluster_historico(periodo_anio, periodo_mes);

        CREATE INDEX IF NOT EXISTS idx_seg_hist_cl
        ON seg_cliente_cluster_historico(cluster_dpo);

        CREATE INDEX IF NOT EXISTS idx_seg_hist_suc_periodo
        ON seg_cliente_cluster_historico(sucursal_id, periodo_anio, periodo_mes);

        CREATE INDEX IF NOT EXISTS idx_seg_hist_periodo_cluster
        ON seg_cliente_cluster_historico(periodo_anio, periodo_mes, cluster_dpo);

        CREATE INDEX IF NOT EXISTS idx_seg_aud_at
        ON seg_auditoria(ejecutado_at DESC);
    """)
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('public.ventas_detalle') IS NOT NULL THEN
                EXECUTE 'CREATE INDEX IF NOT EXISTS idx_ventas_detalle_seg_fecha_cliente_suc_art
                         ON ventas_detalle(fecha, cliente, sucursal, id_articulo)';
                EXECUTE 'CREATE INDEX IF NOT EXISTS idx_ventas_detalle_seg_cliente_suc_fecha
                         ON ventas_detalle(cliente, sucursal, fecha)';
            END IF;

            IF to_regclass('public.articulos') IS NOT NULL THEN
                EXECUTE 'CREATE INDEX IF NOT EXISTS idx_articulos_tipo_producto_id
                         ON articulos ((LOWER(TRIM(COALESCE(tipo_producto, '''')))), id_articulo)';
            END IF;
        END $$;
    """)
    op.execute("""
        INSERT INTO seg_schema_version(component, version, applied_at)
        VALUES ('segmentacion', '20260525_segmentacion_cache_v2', NOW())
        ON CONFLICT (component)
        DO UPDATE SET version = EXCLUDED.version, applied_at = NOW();
    """)


def downgrade():
    op.execute("""
        DROP INDEX IF EXISTS idx_ventas_detalle_seg_fecha_cliente_suc_art;
        DROP INDEX IF EXISTS idx_ventas_detalle_seg_cliente_suc_fecha;
        DROP INDEX IF EXISTS idx_articulos_tipo_producto_id;
        DROP INDEX IF EXISTS idx_seg_hist_periodo_cluster;
        DROP INDEX IF EXISTS idx_seg_hist_suc_periodo;
        DROP INDEX IF EXISTS idx_seg_aud_at;
        DROP INDEX IF EXISTS idx_seg_hist_cl;
        DROP INDEX IF EXISTS idx_seg_hist_per;
        DROP INDEX IF EXISTS idx_seg_hist_cli;
        DROP INDEX IF EXISTS idx_seg_cli_loc;
        DROP INDEX IF EXISTS idx_seg_cli_suc;
        DROP INDEX IF EXISTS idx_seg_params_activo;
    """)
