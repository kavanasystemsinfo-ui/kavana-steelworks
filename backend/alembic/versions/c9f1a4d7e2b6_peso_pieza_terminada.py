"""feat chatarra: peso de la pieza terminada en el modelo

Revision ID: c9f1a4d7e2b6
Revises: b5d2f8a3c6e1
Create Date: 2026-10-28 22:00:00.000000

Opcional por modelo: con el peso real de la pieza terminada, la chatarra de
proceso (rebaba y punzonado) sale exacta. Columna nueva y nula; no toca
datos existentes.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9f1a4d7e2b6'
down_revision: str | Sequence[str] | None = 'b5d2f8a3c6e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'manufacturing_models',
        sa.Column('peso_pieza_terminada_kg', sa.Numeric(precision=12, scale=4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('manufacturing_models', 'peso_pieza_terminada_kg')
