"""segmentacion promotor y cache unificada

Revision ID: 20260531_seg_prom_cache
Revises: 20260525_seg_cache_idx
Create Date: 2026-05-31
"""

from alembic import op


revision = "20260531_seg_prom_cache"
down_revision = "20260525_seg_cache_idx"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE seg_clientes_atributos
        ADD COLUMN IF NOT EXISTS promotor VARCHAR(255);
    """)


def downgrade():
    op.execute("""
        ALTER TABLE seg_clientes_atributos
        DROP COLUMN IF EXISTS promotor;
    """)
