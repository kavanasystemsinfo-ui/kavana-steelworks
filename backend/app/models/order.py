"""Modelos de órdenes de producción y sus líneas."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin

ESTADOS_ORDEN = ("draft", "active", "completed", "cancelled")
ESTADOS_LINEA = ("pending", "in_progress", "stopped", "completed")


class Order(UUIDMixin, TimestampMixin, Base):
    """Orden de fabricación. Ciclo: draft → active → completed/cancelled."""

    __tablename__ = "orders"
    __table_args__ = (CheckConstraint(f"estado IN {ESTADOS_ORDEN}", name="ck_order_estado"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    numero: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    cliente: Mapped[str | None] = mapped_column(String(255))
    fecha_entrega: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notas: Mapped[str | None] = mapped_column(String(2000))

    # Costes acumulados (roll-up desde material_consumos vía trigger/servicio)
    real_material_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0")
    )
    real_total_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0")
    )
    estimado_total_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0")
    )

    lines: Mapped[list["OrderLine"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderLine(UUIDMixin, TimestampMixin, Base):
    """Línea de orden: un producto a fabricar en un puesto."""

    __tablename__ = "order_lines"
    __table_args__ = (
        CheckConstraint(f"estado IN {ESTADOS_LINEA}", name="ck_orderline_estado"),
        UniqueConstraint("order_id", "linea_numero", name="uq_orderline_numero"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True
    )
    linea_numero: Mapped[int] = mapped_column(nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    modelo_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    workstation_id: Mapped[str | None] = mapped_column(String(100))
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    # Cantidades y objetivos
    total_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0")
    )
    produced_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0")
    )
    target_material_qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    target_material_unit: Mapped[str | None] = mapped_column(String(10))
    meters_per_piece: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    # Costes y material real (burbuja de vinculación)
    real_material_qty: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0")
    )
    real_material_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0")
    )
    real_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, default=Decimal("0"))
    scrap_material_qty: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0")
    )
    active_coil_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("stock_items.id")
    )
    active_coil_code: Mapped[str | None] = mapped_column(String(100))

    order: Mapped[Order] = relationship(back_populates="lines")
