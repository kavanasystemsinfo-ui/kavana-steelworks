"""order_lines: columna material_id para validación de compatibilidad

Revision ID: d7e9f2c4a1b3
Revises: c4a9f2e7d1b3
Create Date: 2026-08-15 16:30:00.000000

Añade el material requerido por el modelo de la línea de orden. Es la base
de la validación de Jorge (anexo A, punto 8): el sistema sabe qué material
gasta el modelo y no deja vincular una bobina de características
incompatibles (ancho, espesor y tipo de material).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7e9f2c4a1b3"
down_revision: Union[str, Sequence[str], None] = "c4a9f2e7d1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("order_lines", sa.Column("material_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_order_lines_material_id"), "order_lines", ["material_id"], unique=False
    )
    op.create_foreign_key(
        "fk_order_lines_material_id", "order_lines", "materials", ["material_id"], ["id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_order_lines_material_id", "order_lines", type_="foreignkey")
    op.drop_index(op.f("ix_order_lines_material_id"), table_name="order_lines")
    op.drop_column("order_lines", "material_id")
