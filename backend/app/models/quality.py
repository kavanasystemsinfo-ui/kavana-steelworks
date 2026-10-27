"""Modelos de autocontrol de calidad (spec 04 §2.2-2.3 y §6).

- ManufacturingModel: plantilla de pieza con su qualityPlan (controles).
- QualityPlanCheck: un control del plan (qué medir, herramienta, tolerancias).
- QualityRecord: registro de inspección con mediciones EVALUADAS y estado global.
- QualityMeasurement: medición procesada de un check (is_passed, nominal efectivo).

Nota: la columna del check se llama `tipo` (no `type` como la spec 04 §6):
`type` es palabra reservada de SQL y rompería el CHECK en PostgreSQL. El
contrato del API usa `tipo` igual que el resto del esquema v2 en español.
"""

import uuid
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.models.tenant import User

TIPOS_CHECK = ("numeric", "pass_fail", "visual")
ESTADOS_QUALITY = ("approved", "rejected", "rework")
_TIPOS_SQL = ", ".join(f"'{t}'" for t in TIPOS_CHECK)
_ESTADOS_SQL = ", ".join(f"'{e}'" for e in ESTADOS_QUALITY)


class ManufacturingModel(UUIDMixin, TimestampMixin, Base):
    """Plantilla de pieza: código, material y plan de controles de calidad."""

    __tablename__ = "manufacturing_models"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_manufacturing_model_code"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    material_code: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    quality_plan: Mapped[list["QualityPlanCheck"]] = relationship(
        back_populates="model",
        cascade="all, delete-orphan",
        order_by="QualityPlanCheck.position",
    )


class QualityPlanCheck(UUIDMixin, TimestampMixin, Base):
    """Un control del plan de calidad (spec 04 §2.3)."""

    __tablename__ = "quality_plan_checks"
    __table_args__ = (
        CheckConstraint(f"tipo IN ({_TIPOS_SQL})", name="ck_qualityplancheck_tipo"),
        UniqueConstraint(
            "manufacturing_model_id", "name", name="uq_qualityplancheck_name"
        ),
    )

    manufacturing_model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("manufacturing_models.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(nullable=False, default=0)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    tool_id: Mapped[str | None] = mapped_column(String(100))
    nominal_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    tolerance_plus: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    tolerance_minus: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    model: Mapped[ManufacturingModel] = relationship(back_populates="quality_plan")


class QualityRecord(UUIDMixin, TimestampMixin, Base):
    """Registro de inspección de calidad (spec 04 §2.2)."""

    __tablename__ = "quality_records"
    __table_args__ = (
        CheckConstraint(
            f"overall_status IN ({_ESTADOS_SQL})", name="ck_qualityrecord_status"
        ),
        Index("ix_qualityrecord_tenant_order", "tenant_id", "order_id"),
        Index("ix_qualityrecord_tenant_ts", "tenant_id", "created_at"),
        Index("ix_qualityrecord_tenant_status", "tenant_id", "overall_status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True
    )
    workstation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    operator_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    stock_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("stock_items.id")
    )
    manufacturing_model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("manufacturing_models.id"), nullable=False
    )
    overall_status: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    operator: Mapped["User"] = relationship(  # noqa: F821
        "User", foreign_keys=[operator_id], lazy="joined"
    )
    measurements: Mapped[list["QualityMeasurement"]] = relationship(
        back_populates="record", cascade="all, delete-orphan"
    )


class QualityMeasurement(UUIDMixin, TimestampMixin, Base):
    """Medición procesada de un check (con is_passed y nominal efectivo)."""

    __tablename__ = "quality_measurements"
    __table_args__ = (
        UniqueConstraint(
            "quality_record_id", "check_name", name="uq_qualitymeasurement_check"
        ),
    )

    quality_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("quality_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    check_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value_entered: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    nominal: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    tol_plus: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    tol_minus: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))

    record: Mapped[QualityRecord] = relationship(back_populates="measurements")
