"""feat(incidencias): sesiones de subida de fotos QR + móvil (spec 04 §3.3.2)

Revision ID: a7f2c5e9d4b1
Revises: a6e1b4f8c3d2
Create Date: 2026-08-15 22:30:00.000000

Tabla incidencia_uploads (patrón kavana-manufacturing): sesión con TTL,
status pending/uploaded/used/expired, foto BYTEA temporal que se copia a la
incidencia al crearla (finalize).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7f2c5e9d4b1"
down_revision: str | Sequence[str] | None = "a6e1b4f8c3d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "incidencia_uploads",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("photo", sa.LargeBinary(), nullable=True),
        sa.Column("photo_mime", sa.String(length=50), nullable=True),
        sa.Column("photo_size", sa.Integer(), nullable=True),
        sa.Column("incidencia_id", sa.Uuid(), nullable=True),
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
            "status IN ('pending', 'uploaded', 'used', 'expired')",
            name="ck_incidencia_upload_status",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["incidencia_id"], ["incidencias.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_incidencia_uploads_tenant_id"),
        "incidencia_uploads",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_incidencia_uploads_session_id"),
        "incidencia_uploads",
        ["session_id"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_incidencia_uploads_session_id"), table_name="incidencia_uploads"
    )
    op.drop_index(
        op.f("ix_incidencia_uploads_tenant_id"), table_name="incidencia_uploads"
    )
    op.drop_table("incidencia_uploads")
