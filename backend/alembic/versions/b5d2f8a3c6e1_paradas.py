"""feat operario: paradas de máquina con un toque

Revision ID: b5d2f8a3c6e1
Revises: a8c3e5f1b2d4
Create Date: 2026-10-28 20:00:00.000000

Rediseño del panel de operario (fase 3): el operario toca el motivo de la
parada y el tiempo cuenta solo. Tabla nueva; no toca datos existentes.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b5d2f8a3c6e1'
down_revision: str | Sequence[str] | None = 'a8c3e5f1b2d4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MOTIVOS = "'averia', 'ajustes', 'cambio_modelo', 'limpieza', 'mantenimiento', 'otros'"


def upgrade() -> None:
    op.create_table(
        'paradas',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('puesto', sa.String(length=100), nullable=False),
        sa.Column('operario_id', sa.Uuid(), nullable=False),
        sa.Column('order_id', sa.Uuid(), nullable=True),
        sa.Column('line_id', sa.Uuid(), nullable=True),
        sa.Column('motivo', sa.String(length=20), nullable=False),
        sa.Column('nota', sa.Text(), nullable=True),
        sa.Column('inicio', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fin', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f'motivo IN ({MOTIVOS})', name='ck_parada_motivo'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['operario_id'], ['users.id']),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_paradas_tenant_id', 'paradas', ['tenant_id'])
    op.create_index('ix_paradas_puesto', 'paradas', ['puesto'])
    op.create_index('ix_paradas_operario_id', 'paradas', ['operario_id'])


def downgrade() -> None:
    op.drop_index('ix_paradas_operario_id', table_name='paradas')
    op.drop_index('ix_paradas_puesto', table_name='paradas')
    op.drop_index('ix_paradas_tenant_id', table_name='paradas')
    op.drop_table('paradas')
