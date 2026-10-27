"""Modelos de catálogo de productos terminados y su lista de materiales (BOM).

Product = producto de venta (p. ej. una estantería). ProductComponent = cada
componente de su BOM: o bien una pieza fabricada (ManufacturingModel) o bien un
material directo (Material, p. ej. tornillería o malla comprada). El CHECK XOR
garantiza que cada componente apunte a exactamente uno de los dos.

ADR-018 (productos y BOM): las órdenes siguen fabricando piezas concretas; el
BOM da contexto de ensamblaje y permite consultar qué lleva cada producto.
"""

import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Product(UUIDMixin, TimestampMixin, Base):
    """Producto terminado del catálogo (ej. estantería)."""

    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_product_tenant_code"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    components: Mapped[list["ProductComponent"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductComponent.position",
    )


class ProductComponent(UUIDMixin, TimestampMixin, Base):
    """Componente de la BOM: pieza fabricada (modelo) O material directo."""

    __tablename__ = "product_components"
    __table_args__ = (
        CheckConstraint(
            "(manufacturing_model_id IS NOT NULL AND material_id IS NULL) OR "
            "(manufacturing_model_id IS NULL AND material_id IS NOT NULL)",
            name="ck_component_xor",
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    manufacturing_model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("manufacturing_models.id"), index=True
    )
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("materials.id"), index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, default=Decimal("0"))
    unit: Mapped[str] = mapped_column(String(10), nullable=False, default="uds")
    position: Mapped[int] = mapped_column(nullable=False, default=0)

    product: Mapped["Product"] = relationship(back_populates="components")
