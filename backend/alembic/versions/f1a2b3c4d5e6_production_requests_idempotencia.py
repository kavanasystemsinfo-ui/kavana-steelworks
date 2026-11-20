"""production_requests_idempotencia

Clave de idempotencia del registro de producción (T-159, auditoría H1):
una fila por petición del cliente; UNIQUE (tenant_id, client_request_id)
hace imposible registrar dos veces el mismo parte aunque llegue duplicado.

Revision ID: f1a2b3c4d5e6
Revises: d92118365460
Create Date: 2026-11-20 19:55:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: str | Sequence[str] | None = 'd92118365460'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'production_requests',
        sa.Column('id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('client_request_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('response', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'client_request_id', name='uq_production_request_cliente'),
    )


def downgrade() -> None:
    op.drop_table('production_requests')
