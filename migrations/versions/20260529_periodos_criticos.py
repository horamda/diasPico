"""periodos criticos para calendario 3.4.1

Revision ID: 20260529_periodos_criticos
Revises:
Create Date: 2026-05-29
"""

from alembic import op

revision = "20260529_periodos_criticos"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS periodos_criticos (
            id SERIAL PRIMARY KEY,
            empresa_id VARCHAR(50) NOT NULL DEFAULT '1',
            sucursal_id VARCHAR(50) NOT NULL DEFAULT 'TODAS',
            nombre VARCHAR(100) NOT NULL,
            fecha_inicio DATE NOT NULL,
            fecha_fin DATE NOT NULL,
            motivo VARCHAR(255),
            anio INTEGER NOT NULL,
            estado VARCHAR(20) NOT NULL DEFAULT 'activo',
            creado TIMESTAMP DEFAULT NOW(),
            CONSTRAINT periodos_criticos_duracion CHECK (
                fecha_fin >= fecha_inicio
                AND fecha_fin <= fecha_inicio + INTERVAL '6 days'
            )
        );
        CREATE INDEX IF NOT EXISTS idx_periodos_criticos_lookup
            ON periodos_criticos(empresa_id, sucursal_id, anio);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS periodos_criticos;")
