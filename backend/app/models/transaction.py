"""Modelos de transacciones de material: Kardex inmutable y consumos por orden."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin

TIPOS_TRANSACCION = (
    "entrada_compra",
    "salida_produccion",
    "ajuste_inventario",
    "merma",
    "devolucion",
    "reservado",
    "merma_puntas",
    "traslado",
)


class MaterialTransaction(UUIDMixin, TimestampMixin, Base):
    """Kardex de material. INMUTABLE: sin UPDATE ni DELETE (auditoría ISO 9001)."""

    __tablename__ = "material_transactions"
    __table_args__ = (CheckConstraint(f"tipo IN {TIPOS_TRANSACCION}", name="ck_transaction_tipo"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("materials.id"), nullable=False, index=True
    )
    stock_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("stock_items.id"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    cantidad: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    cantidad_anterior: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    cantidad_nueva: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    orden_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("orders.id"))
    linea_orden_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("order_lines.id")
    )
    motivo: Mapped[str | None] = mapped_column(Text)
    documento_referencia: Mapped[str | None] = mapped_column(String(255))
    realizado_por: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )


METODOS_CALCULO = (
    "density_formula",
    "model_override",
    "meters_legacy",
    "bom_static",
    "manual",
    "coil_end_scrap",
    "manual_late_registration",
    "none",
)
TIPOS_CONSUMO = (
    "automatico",
    "manual",
    "ajuste",
    "auto_audit",
    "merma_puntas",
    "salida_produccion",
)


class MaterialConsumo(UUIDMixin, TimestampMixin, Base):
    """Consumo de material vinculado a una orden/línea.

    total_cost = ROUND(consumed_quantity * cost_per_unit, 2) calculado en
    servicio (la spec propone CHECK/computed; se implementa en el servicio
    con TDD para mantener la lógica explícita).
    """

    __tablename__ = "material_consumos"
    __table_args__ = (
        CheckConstraint(
            f"calculation_method IN {METODOS_CALCULO}",
            name="ck_consumo_calculation_method",
        ),
        CheckConstraint(f"tipo IN {TIPOS_CONSUMO}", name="ck_consumo_tipo"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True
    )
    order_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("order_lines.id")
    )
    workstation_id: Mapped[str] = mapped_column(
        String(100), nullable=False, default="reconciliacion"
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("materials.id"), nullable=False
    )
    stock_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("stock_items.id")
    )
    lote: Mapped[str | None] = mapped_column(String(100))
    consumed_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(10), nullable=False, default="m")
    produced_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0")
    )
    meters_per_piece: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    kg_por_pieza: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), nullable=False, default=Decimal("0")
    )
    calculation_method: Mapped[str] = mapped_column(String(30), nullable=False, default="none")
    cost_per_unit: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), nullable=False, default=Decimal("0")
    )
    total_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0")
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, default="automatico")
    observaciones: Mapped[str | None] = mapped_column(Text)
    operator_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id")
    )
    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
