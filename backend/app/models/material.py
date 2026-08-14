"""Modelos de inventario: Material (maestro) y StockItem (bobina/lote)."""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin

UNIDADES = ("kg", "uds", "m", "litros")
ESTADOS_STOCK = ("activo", "agotado", "cuarentena", "bloqueado", "pico")


class Material(UUIDMixin, TimestampMixin, Base):
    """Material maestro. stock_current es derivada (se actualiza por transacciones)."""

    __tablename__ = "materials"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_material_tenant_code"),
        CheckConstraint("density BETWEEN 100 AND 30000", name="ck_material_density"),
        CheckConstraint(
            "unit IN ('kg','uds','m','litros')", name="ck_material_unit"
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    stock_current: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0")
    )
    stock_minimum: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0")
    )
    cost_per_unit: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), nullable=False, default=Decimal("0")
    )
    dimension_ancho_mm: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    dimension_espesor_mm: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    density: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("7850")
    )  # kg/m3, densidad del acero
    density_calibrada: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), default=Decimal("7.7807")
    )  # kg/dm3, Densidad Calibrada Kavana (Decisión 92)
    unit: Mapped[str] = mapped_column(
        String(10), nullable=False, default="kg"
    )
    external_links: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    stock_items: Mapped[list["StockItem"]] = relationship(
        back_populates="material", cascade="all, delete-orphan"
    )


class StockItem(UUIDMixin, TimestampMixin, Base):
    """Lote o bobina de material. La identidad física es coil_id escaneable.

    cantidad_disponible puede ser NEGATIVA (tolerancia de superávit en modo
    auditoría), por eso NO lleva CHECK >= 0 (decisión de la spec 01, sección 6.2).
    """

    __tablename__ = "stock_items"
    __table_args__ = (
        CheckConstraint(
            "width_mm IS NULL OR width_mm = 0 OR width_mm BETWEEN 10 AND 2500",
            name="ck_stockitem_width",
        ),
        CheckConstraint(
            "thickness_mm IS NULL OR thickness_mm = 0 OR thickness_mm BETWEEN 0.1 AND 25",
            name="ck_stockitem_thickness",
        ),
        CheckConstraint("coste_por_unidad >= 0", name="ck_stockitem_cost"),
        CheckConstraint(
            f"estado IN {ESTADOS_STOCK}", name="ck_stockitem_estado"
        ),
        CheckConstraint(
            "(estado = 'pico') = es_pico", name="ck_stockitem_pico_consistente"
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("materials.id"), nullable=False, index=True
    )
    lote: Mapped[str] = mapped_column(String(100), nullable=False)
    coil_id: Mapped[str | None] = mapped_column(String(100), index=True)
    cantidad_inicial: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0")
    )
    cantidad_disponible: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=Decimal("0")
    )
    unit: Mapped[str] = mapped_column(
        String(10), nullable=False, default="uds"
    )
    width_mm: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    thickness_mm: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    coste_por_unidad: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), nullable=False, default=Decimal("0")
    )
    costing_method: Mapped[str] = mapped_column(
        String(10), nullable=False, default="standard"
    )  # standard | real
    moneda: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    fecha_entrada: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )  # CLAVE FIFO
    fecha_caducidad: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ubicacion: Mapped[str | None] = mapped_column(String(255), index=True)
    estado: Mapped[str] = mapped_column(
        String(12), nullable=False, default="activo"
    )
    es_pico: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notas: Mapped[str | None] = mapped_column(Text)
    creado_por: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id")
    )

    material: Mapped[Material] = relationship(back_populates="stock_items")
