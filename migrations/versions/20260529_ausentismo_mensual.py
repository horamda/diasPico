"""ausentismo mensual historico para periodos criticos

Revision ID: 20260529_ausentismo_mensual
Revises:
Create Date: 2026-05-29
"""

from alembic import op

revision = "20260529_ausentismo_mensual"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS ausentismo_mensual (
            id SERIAL PRIMARY KEY,
            empresa_id  VARCHAR(50) NOT NULL DEFAULT '1',
            sucursal_id VARCHAR(50) NOT NULL DEFAULT 'TODAS',
            anio        INTEGER     NOT NULL,
            mes         INTEGER     NOT NULL CHECK (mes BETWEEN 1 AND 12),
            pct_ausentismo NUMERIC(6,2) NOT NULL,
            actualizado TIMESTAMP DEFAULT NOW(),
            UNIQUE(empresa_id, sucursal_id, anio, mes)
        );
        CREATE INDEX IF NOT EXISTS idx_ausentismo_mensual_lookup
            ON ausentismo_mensual(empresa_id, sucursal_id, anio);
    """)

    op.execute("""
        INSERT INTO ausentismo_mensual (empresa_id, sucursal_id, anio, mes, pct_ausentismo)
        VALUES
            ('1','TODAS',2025,1,3.02),
            ('1','TODAS',2025,2,5.65),
            ('1','TODAS',2025,3,16.00),
            ('1','TODAS',2025,4,15.58),
            ('1','TODAS',2025,5,2.80),
            ('1','TODAS',2025,6,1.19),
            ('1','TODAS',2025,7,2.10),
            ('1','TODAS',2025,8,2.69),
            ('1','TODAS',2025,9,3.46),
            ('1','TODAS',2025,10,12.94),
            ('1','TODAS',2025,11,6.82),
            ('1','TODAS',2025,12,13.33),
            ('1','TODAS',2026,1,2.72),
            ('1','TODAS',2026,2,3.42),
            ('1','TODAS',2026,3,3.30),
            ('1','TODAS',2026,4,5.87)
        ON CONFLICT (empresa_id, sucursal_id, anio, mes)
        DO UPDATE SET pct_ausentismo = EXCLUDED.pct_ausentismo,
                      actualizado = NOW();
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS ausentismo_mensual;")
