"""Modelo de trazabilidad ISO 9001: ProductionLog (spec 04 §2.1).

Registro de evento de producción INMUTABLE: base de auditoría. La
inmutabilidad real se garantiza en PostgreSQL con un trigger que bloquea
UPDATE/DELETE (migración 04); aquí el modelo declara el contrato completo
(acciones del enum, metadata JSONB, índices por tenant/orden/operario).
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.models.tenant import User

ACCIONES_TRACE = (
    "start",
    "pause",
    "resume",
    "finish",
    "produce",
    "scrap",
    "setup_start",
    "setup_finish",
    "close_shift",
    "stopped",
    "quality_check",
)
_ACCIONES_SQL = ", ".join(f"'{a}'" for a in ACCIONES_TRACE)


class ProductionLog(UUIDMixin, TimestampMixin, Base):
    """Evento de producción inmutable (trazabilidad ISO 9001)."""

    __tablename__ = "production_logs"
    __table_args__ = (
        CheckConstraint(f"action IN ({_ACCIONES_SQL})", name="ck_productionlog_action"),
        Index("ix_productionlog_tenant_ts", "tenant_id", "timestamp"),
        Index("ix_productionlog_order_ts", "order_id", "timestamp"),
        Index("ix_productionlog_operator_ts", "operator_id", "timestamp"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True
    )
    line_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("order_lines.id"), nullable=False, index=True
    )
    operator_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, default=Decimal("0"))
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    shift: Mapped[str | None] = mapped_column(String(10))

    operator: Mapped[User] = relationship("User", foreign_keys=[operator_id], lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ProductionLog {self.action} qty={self.quantity} ts={self.timestamp}>"
