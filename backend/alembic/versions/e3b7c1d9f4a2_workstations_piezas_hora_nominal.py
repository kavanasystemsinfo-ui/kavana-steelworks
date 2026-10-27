"""feat panel: ritmo nominal por puesto (piezas/hora)

Revision ID: e3b7c1d9f4a2
Revises: c9e4f7a21b83
Create Date: 2026-10-27 14:00:00.000000

Base del plan del turno en el panel de mando. Columna nueva y opcional: los
puestos existentes quedan a NULL (sin plan) hasta que se configure su ritmo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3b7c1d9f4a2'
down_revision: Union[str, Sequence[str], None] = 'c9e4f7a21b83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'workstations',
        sa.Column('piezas_hora_nominal', sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('workstations', 'piezas_hora_nominal')
