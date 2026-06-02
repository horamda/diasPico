"""segmentacion otif por cliente

Revision ID: 20260531_seg_otif
Revises: 20260531_seg_prom_cache
Create Date: 2026-05-31
"""

from alembic import op


revision = "20260531_seg_otif"
down_revision = "20260531_seg_prom_cache"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE seg_clientes_atributos
        ADD COLUMN IF NOT EXISTS otif_valor NUMERIC(6,2);
        ALTER TABLE seg_clientes_atributos
        ADD COLUMN IF NOT EXISTS otif_fecha DATE;
        ALTER TABLE seg_cliente_dpo_cache
        ADD COLUMN IF NOT EXISTS otif_valor NUMERIC(6,2);
        ALTER TABLE seg_cliente_cluster_historico
        ADD COLUMN IF NOT EXISTS otif_valor NUMERIC(6,2);
    """)


def downgrade():
    op.execute("""
        ALTER TABLE seg_cliente_cluster_historico
        DROP COLUMN IF EXISTS otif_valor;
        ALTER TABLE seg_cliente_dpo_cache
        DROP COLUMN IF EXISTS otif_valor;
        ALTER TABLE seg_clientes_atributos
        DROP COLUMN IF EXISTS otif_fecha;
        ALTER TABLE seg_clientes_atributos
        DROP COLUMN IF EXISTS otif_valor;
    """)
