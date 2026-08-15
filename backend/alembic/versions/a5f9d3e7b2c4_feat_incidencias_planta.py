"""feat(incidencias): incidencias de planta con cierre financiero (spec 04 §6)

Revision ID: a5f9d3e7b2c4
Revises: a4f8c2e9d6b1
Create Date: 2026-08-15 21:00:00.000000

Tablas: incidencias, incidencia_historial_estados. La resolución financiera
se modela como columnas nullable en la misma fila (el legacy la trata como
objeto embebido con actualización parcial: cada campo conserva su valor
previo si no viene en el update).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a5f9d3e7b2c4"
down_revision: str | Sequence[str] | None = "a4f8c2e9d6b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "incidencias",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("linea_id", sa.String(length=100), nullable=True),
        sa.Column("puesto", sa.String(length=100), nullable=False),
        sa.Column("operario_id", sa.Uuid(), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("foto", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("resolucion_tipo", sa.String(length=50), nullable=True),
        sa.Column("resolucion_descripcion", sa.Text(), nullable=True),
        sa.Column("tiempo_parada_min", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("coste", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("responsable_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("coste >= 0", name="ck_incidencia_coste"),
        sa.CheckConstraint(
            "estado IN ('abierta', 'en_revision', 'resuelta', 'cerrada')",
            name="ck_incidencia_estado",
        ),
        sa.CheckConstraint(
            "tiempo_parada_min >= 0", name="ck_incidencia_tiempo"
        ),
        sa.CheckConstraint(
            "tipo IN ('maquina', 'material', 'seguridad', 'otro')",
            name="ck_incidencia_tipo",
        ),
        sa.ForeignKeyConstraint(["operario_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["responsable_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_incidencias_operario_id"), "incidencias", ["operario_id"], unique=False
    )
    op.create_index(
        op.f("ix_incidencias_tenant_id"), "incidencias", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_incidencia_tenant_estado_ts",
        "incidencias",
        ["tenant_id", "estado", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_incidencia_tenant_tipo",
        "incidencias",
        ["tenant_id", "tipo"],
        unique=False,
    )

    op.create_table(
        "incidencia_historial_estados",
        sa.Column("incidencia_id", sa.Uuid(), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["incidencia_id"], ["incidencias.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_incidencia_historial_estados_incidencia_id"),
        "incidencia_historial_estados",
        ["incidencia_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_incidencia_historial_estados_incidencia_id"),
        table_name="incidencia_historial_estados",
    )
    op.drop_table("incidencia_historial_estados")
    op.drop_index("ix_incidencia_tenant_tipo", table_name="incidencias")
    op.drop_index("ix_incidencia_tenant_estado_ts", table_name="incidencias")
    op.drop_index(op.f("ix_incidencias_tenant_id"), table_name="incidencias")
    op.drop_index(op.f("ix_incidencias_operario_id"), table_name="incidencias")
    op.drop_table("incidencias")
