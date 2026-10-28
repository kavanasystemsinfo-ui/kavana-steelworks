"""feat operario: calculadoras de embalaje por puesto

Revision ID: a8c3e5f1b2d4
Revises: e3b7c1d9f4a2
Create Date: 2026-10-28 18:00:00.000000

Rediseño del panel de operario (fase 2): plantillas piezas/paquete ×
paquetes/fila × filas/palet que crea el operario en su puesto. Tabla nueva;
no toca datos existentes.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a8c3e5f1b2d4'
down_revision: str | Sequence[str] | None = 'e3b7c1d9f4a2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'calculadoras_puesto',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('puesto', sa.String(length=100), nullable=False),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('piezas_paquete', sa.Integer(), nullable=False),
        sa.Column('paquetes_fila', sa.Integer(), nullable=False),
        sa.Column('filas_palet', sa.Integer(), nullable=False),
        sa.Column('creada_por', sa.Uuid(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['creada_por'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'puesto', 'nombre', name='uq_calculadora_puesto_nombre'),
    )
    op.create_index('ix_calculadoras_puesto_tenant_id', 'calculadoras_puesto', ['tenant_id'])
    op.create_index('ix_calculadoras_puesto_puesto', 'calculadoras_puesto', ['puesto'])


def downgrade() -> None:
    op.drop_index('ix_calculadoras_puesto_puesto', table_name='calculadoras_puesto')
    op.drop_index('ix_calculadoras_puesto_tenant_id', table_name='calculadoras_puesto')
    op.drop_table('calculadoras_puesto')
