"""model_workstation_materials: material de cada modelo en cada puesto

Revision ID: b5c8e1f3a9d2
Revises: c9f1a4d7e2b6
Create Date: 2026-11-07 18:00:00.000000

Solo crea una tabla nueva (no toca datos existentes). El material de una línea
de orden sale del par (modelo, puesto), como en el sistema legacy.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5c8e1f3a9d2"
down_revision: Union[str, Sequence[str], None] = "c9f1a4d7e2b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "model_workstation_materials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("manufacturing_model_id", sa.Uuid(), nullable=False),
        sa.Column("workstation_code", sa.String(length=100), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(
            ["manufacturing_model_id"], ["manufacturing_models.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "manufacturing_model_id", "workstation_code", name="uq_model_workstation_material"
        ),
    )
    for col in ("tenant_id", "manufacturing_model_id", "material_id"):
        op.create_index(
            op.f(f"ix_model_workstation_materials_{col}"),
            "model_workstation_materials",
            [col],
        )


def downgrade() -> None:
    op.drop_table("model_workstation_materials")
