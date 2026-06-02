"""segmentacion historico metricas amplias

Revision ID: 20260531_seg_hist_metricas
Revises: 20260531_seg_otif
Create Date: 2026-05-31
"""

from alembic import op


revision = "20260531_seg_hist_metricas"
down_revision = "20260531_seg_otif"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE seg_cliente_cluster_historico
        ALTER COLUMN crecimiento_pct TYPE NUMERIC(14,4);
        ALTER TABLE seg_cliente_cluster_historico
        ALTER COLUMN ratio_costo_logistico TYPE NUMERIC(14,4);
        ALTER TABLE seg_cliente_cluster_historico
        ALTER COLUMN dropsize_ytd TYPE NUMERIC(14,4);
        ALTER TABLE seg_cliente_cluster_historico
        ALTER COLUMN pct_rechazo_pedidos TYPE NUMERIC(12,4);
    """)


def downgrade():
    op.execute("""
        ALTER TABLE seg_cliente_cluster_historico
        ALTER COLUMN crecimiento_pct TYPE NUMERIC(10,4);
        ALTER TABLE seg_cliente_cluster_historico
        ALTER COLUMN ratio_costo_logistico TYPE NUMERIC(8,4);
        ALTER TABLE seg_cliente_cluster_historico
        ALTER COLUMN dropsize_ytd TYPE NUMERIC(10,4);
        ALTER TABLE seg_cliente_cluster_historico
        ALTER COLUMN pct_rechazo_pedidos TYPE NUMERIC(8,4);
    """)
