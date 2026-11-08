"""trazabilidad_origen_bobina

Revision ID: d92118365460
Revises: b5c8e1f3a9d2
Create Date: 2026-11-08 13:56:54.436696

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd92118365460'
down_revision: Union[str, Sequence[str], None] = 'b5c8e1f3a9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - añade trazabilidad de origen de bobina (solo ADD)."""
    # 1) origen: 'recepcion' | 'alta_manual', default 'recepcion', NOT NULL
    op.add_column(
        "stock_items",
        sa.Column(
            "origen",
            sa.String(20),
            nullable=False,
            server_default="recepcion",
        ),
    )

    # 2) creada_por_user_id: FK a users, nullable (legacy rows = NULL)
    op.add_column(
        "stock_items",
        sa.Column(
            "creada_por_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )

    # 3) alta_ubicacion: puesto/ubicación declarada en alta manual, nullable
    op.add_column(
        "stock_items",
        sa.Column(
            "alta_ubicacion",
            sa.String(255),
            nullable=True,
        ),
    )

    # 4) pendiente_verificacion: bool, default false (legacy = false)
    op.add_column(
        "stock_items",
        sa.Column(
            "pendiente_verificacion",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    # 5) verificada_por_user_id: FK a users, nullable
    op.add_column(
        "stock_items",
        sa.Column(
            "verificada_por_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )

    # 6) verificada_en: datetime con timezone, nullable
    op.add_column(
        "stock_items",
        sa.Column(
            "verificada_en",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Índices útiles para consultas de verificación
    op.create_index("ix_stock_items_pendiente_verificacion", "stock_items", ["pendiente_verificacion"])
    op.create_index("ix_stock_items_origen", "stock_items", ["origen"])


def downgrade() -> None:
    """Downgrade schema - elimina columnas añadidas."""
    op.drop_index("ix_stock_items_origen", table_name="stock_items")
    op.drop_index("ix_stock_items_pendiente_verificacion", table_name="stock_items")
    op.drop_column("stock_items", "verificada_en")
    op.drop_column("stock_items", "verificada_por_user_id")
    op.drop_column("stock_items", "pendiente_verificacion")
    op.drop_column("stock_items", "alta_ubicacion")
    op.drop_column("stock_items", "creada_por_user_id")
    op.drop_column("stock_items", "origen")