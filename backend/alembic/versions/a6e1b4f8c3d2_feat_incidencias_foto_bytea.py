"""feat(incidencias): foto de incidencia como BYTEA (patrón kavana-manufacturing)

Revision ID: a6e1b4f8c3d2
Revises: a5f9d3e7b2c4
Create Date: 2026-08-15 22:00:00.000000

Añade foto_data (BYTEA), foto_mime y foto_size a incidencias: la evidencia
se guarda en PostgreSQL, sin servicios externos (la columna foto TEXT queda
como URL opcional del legacy/Cloudinary, sin uso en la demo).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a6e1b4f8c3d2"
down_revision: str | Sequence[str] | None = "a5f9d3e7b2c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "incidencias",
        sa.Column("foto_data", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "incidencias",
        sa.Column("foto_mime", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "incidencias",
        sa.Column("foto_size", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("incidencias", "foto_size")
    op.drop_column("incidencias", "foto_mime")
    op.drop_column("incidencias", "foto_data")
