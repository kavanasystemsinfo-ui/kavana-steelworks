"""feat admin multitenant: tenant roles, sequences, workstations

Revision ID: 59bee63a26fb
Revises: a7f2c5e9d4b1
Create Date: 2026-08-16 21:49:22.715510

Nota de la migración: las columnas nuevas de `tenants` (slug, status, auth,
theme, finances, sequences_config) se añaden con server_default y luego se
pasan a NOT NULL, porque la tabla ya contiene el tenant demo. Sin ese paso
intermedio, el add_column fallaría en despliegues con datos.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '59bee63a26fb'
down_revision: Union[str, Sequence[str], None] = 'a7f2c5e9d4b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('sequences',
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('sequence_type', sa.String(length=10), nullable=False),
    sa.Column('prefix', sa.String(length=64), nullable=False),
    sa.Column('padding', sa.Integer(), nullable=False),
    sa.Column('next_number', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("sequence_type IN ('order', 'lot')", name='ck_sequence_tipo'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'sequence_type', 'prefix', name='uq_sequence_tenant_type_prefix')
    )
    op.create_index(op.f('ix_sequences_tenant_id'), 'sequences', ['tenant_id'], unique=False)
    op.create_table('tenant_roles',
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('role_key', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('permissions', sa.JSON(), nullable=False),
    sa.Column('is_system', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'role_key', name='uq_tenantrole_key')
    )
    op.create_index(op.f('ix_tenant_roles_tenant_id'), 'tenant_roles', ['tenant_id'], unique=False)
    op.create_table('workstation_groups',
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('color', sa.String(length=20), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'name', name='uq_wsgroup_name')
    )
    op.create_index(op.f('ix_workstation_groups_tenant_id'), 'workstation_groups', ['tenant_id'], unique=False)
    op.create_table('workstations',
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('group_id', sa.Uuid(), nullable=True),
    sa.Column('code', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('color', sa.String(length=20), nullable=False),
    sa.Column('hourly_cost', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('registration_method', sa.String(length=10), nullable=False),
    sa.Column('maintenance_interval_hours', sa.Integer(), nullable=False),
    sa.Column('maintenance_pre_warning_hours', sa.Integer(), nullable=False),
    sa.Column('last_maintenance_reset', sa.DateTime(timezone=True), nullable=True),
    sa.Column('accumulated_hours', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("registration_method IN ('timer', 'quantity', 'manual')", name='ck_workstation_reg_method'),
    sa.ForeignKeyConstraint(['group_id'], ['workstation_groups.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'code', name='uq_workstation_code')
    )
    op.create_index(op.f('ix_workstations_tenant_id'), 'workstations', ['tenant_id'], unique=False)

    # ── tenants: añadir columnas con default, backfill, luego NOT NULL ──────
    op.add_column('tenants', sa.Column('slug', sa.String(length=64), nullable=True))
    op.add_column('tenants', sa.Column('status', sa.String(length=12), nullable=True, server_default='active'))
    op.add_column('tenants', sa.Column('auth', sa.JSON(), nullable=True, server_default=sa.text("'{}'::jsonb")))
    op.add_column('tenants', sa.Column('theme', sa.JSON(), nullable=True, server_default=sa.text("'{}'::jsonb")))
    op.add_column('tenants', sa.Column('finances', sa.JSON(), nullable=True, server_default=sa.text("'{}'::jsonb")))
    op.add_column('tenants', sa.Column('sequences_config', sa.JSON(), nullable=True, server_default=sa.text("'{}'::jsonb")))

    # Backfill: slug derivado del nombre (normalizado) para filas existentes.
    op.execute(
        "UPDATE tenants SET slug = lower(regexp_replace(name, '[^a-zA-Z0-9]+', '-', 'g')) "
        "WHERE slug IS NULL OR slug = ''"
    )

    op.alter_column('tenants', 'slug', existing_type=sa.String(length=64), nullable=False)
    op.alter_column('tenants', 'status', existing_type=sa.String(length=12), nullable=False)
    op.alter_column('tenants', 'auth', existing_type=sa.JSON(), nullable=False)
    op.alter_column('tenants', 'theme', existing_type=sa.JSON(), nullable=False)
    op.alter_column('tenants', 'finances', existing_type=sa.JSON(), nullable=False)
    op.alter_column('tenants', 'sequences_config', existing_type=sa.JSON(), nullable=False)

    op.create_index(op.f('ix_tenants_slug'), 'tenants', ['slug'], unique=True)
    op.create_check_constraint('ck_tenant_status', 'tenants', "status IN ('active', 'suspended', 'trial')")

    op.add_column('users', sa.Column('employee_number', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('default_workstation_code', sa.String(length=100), nullable=True))
    op.create_index(op.f('ix_users_employee_number'), 'users', ['employee_number'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_users_employee_number'), table_name='users')
    op.drop_column('users', 'default_workstation_code')
    op.drop_column('users', 'employee_number')
    op.drop_constraint('ck_tenant_status', 'tenants', type_='check')
    op.drop_index(op.f('ix_tenants_slug'), table_name='tenants')
    op.drop_column('tenants', 'sequences_config')
    op.drop_column('tenants', 'finances')
    op.drop_column('tenants', 'theme')
    op.drop_column('tenants', 'auth')
    op.drop_column('tenants', 'status')
    op.drop_column('tenants', 'slug')
    op.drop_index(op.f('ix_workstations_tenant_id'), table_name='workstations')
    op.drop_table('workstations')
    op.drop_index(op.f('ix_workstation_groups_tenant_id'), table_name='workstation_groups')
    op.drop_table('workstation_groups')
    op.drop_index(op.f('ix_tenant_roles_tenant_id'), table_name='tenant_roles')
    op.drop_table('tenant_roles')
    op.drop_index(op.f('ix_sequences_tenant_id'), table_name='sequences')
    op.drop_table('sequences')
