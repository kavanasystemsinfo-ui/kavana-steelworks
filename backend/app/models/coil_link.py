"""Burbuja de vinculación explícita: bobina ↔ orden ↔ línea.

Mejora estructural del v4: el legacy derivaba la burbuja escaneando
MaterialTransaction; aquí se modela como tabla propia con UNIQUE para
garantizar idempotencia de linkCoil.
"""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin

ESTADOS_COIL_LINK = ("vinculada", "consumida", "retal", "merma", "desvinculada")


class CoilLink(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "coil_links"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "stock_item_id",
            "order_id",
            "order_line_id",
            name="uq_coillink_burbuja",
        ),
        CheckConstraint(
            f"estado IN {ESTADOS_COIL_LINK}", name="ck_coillink_estado"
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    stock_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("stock_items.id"), nullable=False
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orders.id"), nullable=False
    )
    order_line_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("order_lines.id"), nullable=False
    )
    estado: Mapped[str] = mapped_column(
        String(12), nullable=False, default="vinculada"
    )
