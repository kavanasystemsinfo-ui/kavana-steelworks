"""feat catalogo: products + product_components (BOM)

Revision ID: c9e4f7a21b83
Revises: 59bee63a26fb
Create Date: 2026-10-15 10:00:00.000000

Catálogo de productos terminados con su lista de materiales (BOM), según
ADR-018. Cada componente apunta a una pieza fabricada (manufacturing_models)
O a un material directo (materials), garantizado por ck_component_xor.

Además se conecta order_lines.product_id (columna huérfana desde la migración
inicial) con products.id vía FK: en producción está 100% NULL, así que la
adición no puede fallar por datos existentes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e4f7a21b83'
down_revision: Union[str, Sequence[str], None] = '59bee63a26fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'products',
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'code', name='uq_product_tenant_code'),
    )
    op.create_index(op.f('ix_products_tenant_id'), 'products', ['tenant_id'], unique=False)
    op.create_table(
        'product_components',
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('manufacturing_model_id', sa.Uuid(), nullable=True),
        sa.Column('material_id', sa.Uuid(), nullable=True),
        sa.Column('quantity', sa.Numeric(14, 4), nullable=False),
        sa.Column('unit', sa.String(length=10), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            '(manufacturing_model_id IS NOT NULL AND material_id IS NULL) OR '
            '(manufacturing_model_id IS NULL AND material_id IS NOT NULL)',
            name='ck_component_xor',
        ),
        sa.ForeignKeyConstraint(['material_id'], ['materials.id'], ),
        sa.ForeignKeyConstraint(['manufacturing_model_id'], ['manufacturing_models.id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_product_components_product_id'), 'product_components', ['product_id'], unique=False)
    op.create_index(op.f('ix_product_components_manufacturing_model_id'), 'product_components', ['manufacturing_model_id'], unique=False)
    op.create_index(op.f('ix_product_components_material_id'), 'product_components', ['material_id'], unique=False)

    # order_lines.product_id pasa de columna huérfana a FK real (100% NULL en prod)
    op.create_foreign_key(
        'fk_orderlines_product',
        'order_lines',
        'products',
        ['product_id'],
        ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_orderlines_product', 'order_lines', type_='foreignkey')
    op.drop_index(op.f('ix_product_components_material_id'), table_name='product_components')
    op.drop_index(op.f('ix_product_components_manufacturing_model_id'), table_name='product_components')
    op.drop_index(op.f('ix_product_components_product_id'), table_name='product_components')
    op.drop_table('product_components')
    op.drop_index(op.f('ix_products_tenant_id'), table_name='products')
    op.drop_table('products')
