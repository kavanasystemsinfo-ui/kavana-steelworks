"""feat(quality): autocontroles de calidad (spec 04 §6)

Revision ID: a4f8c2e9d6b1
Revises: fd6922f1785e
Create Date: 2026-08-15 20:15:00.000000

Tablas: manufacturing_models, quality_plan_checks, quality_records,
quality_measurements. La columna del check se llama `tipo` (no `type`,
palabra reservada de SQL que rompería el CHECK en PostgreSQL).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4f8c2e9d6b1"
down_revision: str | Sequence[str] | None = "fd6922f1785e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "manufacturing_models",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("material_code", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_manufacturing_model_code"),
    )
    op.create_index(
        op.f("ix_manufacturing_models_tenant_id"),
        "manufacturing_models",
        ["tenant_id"],
        unique=False,
    )

    op.create_table(
        "quality_plan_checks",
        sa.Column("manufacturing_model_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("tool_id", sa.String(length=100), nullable=True),
        sa.Column("nominal_value", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("tolerance_plus", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("tolerance_minus", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("is_critical", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint(
            "tipo IN ('numeric', 'pass_fail', 'visual')",
            name="ck_qualityplancheck_tipo",
        ),
        sa.ForeignKeyConstraint(
            ["manufacturing_model_id"],
            ["manufacturing_models.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "manufacturing_model_id", "name", name="uq_qualityplancheck_name"
        ),
    )
    op.create_index(
        op.f("ix_quality_plan_checks_manufacturing_model_id"),
        "quality_plan_checks",
        ["manufacturing_model_id"],
        unique=False,
    )

    op.create_table(
        "quality_records",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("workstation_id", sa.String(length=100), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("stock_item_id", sa.Uuid(), nullable=True),
        sa.Column("manufacturing_model_id", sa.Uuid(), nullable=False),
        sa.Column("overall_status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "overall_status IN ('approved', 'rejected', 'rework')",
            name="ck_qualityrecord_status",
        ),
        sa.ForeignKeyConstraint(
            ["manufacturing_model_id"], ["manufacturing_models.id"]
        ),
        sa.ForeignKeyConstraint(["operator_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["stock_item_id"], ["stock_items.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_quality_records_operator_id"),
        "quality_records",
        ["operator_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quality_records_order_id"),
        "quality_records",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quality_records_tenant_id"),
        "quality_records",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_qualityrecord_tenant_order",
        "quality_records",
        ["tenant_id", "order_id"],
        unique=False,
    )
    op.create_index(
        "ix_qualityrecord_tenant_status",
        "quality_records",
        ["tenant_id", "overall_status"],
        unique=False,
    )
    op.create_index(
        "ix_qualityrecord_tenant_ts",
        "quality_records",
        ["tenant_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "quality_measurements",
        sa.Column("quality_record_id", sa.Uuid(), nullable=False),
        sa.Column("check_name", sa.String(length=100), nullable=False),
        sa.Column("value_entered", sa.JSON(), nullable=False),
        sa.Column("is_passed", sa.Boolean(), nullable=False),
        sa.Column("nominal", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("tol_plus", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("tol_minus", sa.Numeric(precision=14, scale=3), nullable=True),
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
            ["quality_record_id"],
            ["quality_records.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "quality_record_id", "check_name", name="uq_qualitymeasurement_check"
        ),
    )
    op.create_index(
        op.f("ix_quality_measurements_quality_record_id"),
        "quality_measurements",
        ["quality_record_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_quality_measurements_quality_record_id"),
        table_name="quality_measurements",
    )
    op.drop_table("quality_measurements")
    op.drop_index("ix_qualityrecord_tenant_ts", table_name="quality_records")
    op.drop_index("ix_qualityrecord_tenant_status", table_name="quality_records")
    op.drop_index("ix_qualityrecord_tenant_order", table_name="quality_records")
    op.drop_index(op.f("ix_quality_records_tenant_id"), table_name="quality_records")
    op.drop_index(op.f("ix_quality_records_order_id"), table_name="quality_records")
    op.drop_index(op.f("ix_quality_records_operator_id"), table_name="quality_records")
    op.drop_table("quality_records")
    op.drop_index(
        op.f("ix_quality_plan_checks_manufacturing_model_id"),
        table_name="quality_plan_checks",
    )
    op.drop_table("quality_plan_checks")
    op.drop_index(
        op.f("ix_manufacturing_models_tenant_id"), table_name="manufacturing_models"
    )
    op.drop_table("manufacturing_models")
