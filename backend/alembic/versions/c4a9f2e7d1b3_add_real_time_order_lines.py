"""add real_time a order_lines (spec 02 3.4, registro de producción)

Revision ID: c4a9f2e7d1b3
Revises: bb59fc949213
Create Date: 2026-08-15 09:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4a9f2e7d1b3'
down_revision: Union[str, Sequence[str], None] = 'bb59fc949213'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Añade real_time (minutos de sesión acumulados) a order_lines."""
    op.add_column('order_lines', sa.Column('real_time', sa.Numeric(14, 4), nullable=False, server_default='0'))


def downgrade() -> None:
    """Quita real_time de order_lines."""
    op.drop_column('order_lines', 'real_time')
