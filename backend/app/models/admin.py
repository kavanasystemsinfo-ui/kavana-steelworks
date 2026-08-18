"""Modelos de administración multi-tenant (spec 07, ADR-015).

Normalización del monolito Tenant.js del v2:
- tenant_roles: roles configurables con permisos granulares.
- sequences: contadores automáticos por tenant+tipo+prefix (SELECT FOR UPDATE).
- workstations / workstation_groups: puestos de trabajo con mantenimiento.
"""

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
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin

ESTADOS_TENANT = ("active", "suspended", "trial")
METODOS_REGISTRO = ("timer", "quantity", "manual")
TIPOS_SECUENCIA = ("order", "lot")

PERMISOS_CATALOGO = (
    "stock.scan",
    "stock.link",
    "stock.finish",
    "stock.receive",
    "stock.list",
    "production.record",
    "quality.check",
    "quality.read",
    "incidencia.create",
    "incidencia.manage",
    "oee.read",
    "trace.read",
    "orders.read",
    "admin.users",
    "admin.tenant",
    "admin.sequences",
    "admin.workstations",
    "admin.roles",
)

# Rol admin del sistema: todos los permisos
PERMISOS_ADMIN = list(PERMISOS_CATALOGO)


class TenantRole(UUIDMixin, TimestampMixin, Base):
    """Rol configurable del tenant con permisos granulares (spec 07 §2.2)."""

    __tablename__ = "tenant_roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "role_key", name="uq_tenantrole_key"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    role_key: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    permissions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Sequence(UUIDMixin, TimestampMixin, Base):
    """Contador automático por tenant+tipo+prefix (spec 07 §2.3).

    El incremento se hace con SELECT ... FOR UPDATE (mejora sobre el $inc de
    MongoDB): dos peticiones concurrentes nunca reciben el mismo número.
    """

    __tablename__ = "sequences"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "sequence_type", "prefix", name="uq_sequence_tenant_type_prefix"
        ),
        CheckConstraint(
            f"sequence_type IN {TIPOS_SECUENCIA}", name="ck_sequence_tipo"
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    sequence_type: Mapped[str] = mapped_column(String(10), nullable=False)
    prefix: Mapped[str] = mapped_column(String(64), nullable=False)
    padding: Mapped[int] = mapped_column(nullable=False, default=3)
    next_number: Mapped[int] = mapped_column(nullable=False, default=1)


class WorkstationGroup(UUIDMixin, TimestampMixin, Base):
    """Grupo de puestos (p.ej. 'Línea 1' agrupa varios puestos)."""

    __tablename__ = "workstation_groups"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_wsgroup_name"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="#6366f1")

    workstations: Mapped[list["Workstation"]] = relationship(back_populates="group")


class Workstation(UUIDMixin, TimestampMixin, Base):
    """Puesto de trabajo con coste/hora y mantenimiento preventivo.

    El `code` sustituye al string suelto `workstation_id` de order_lines:
    el admin crea puestos y el resto del sistema los referencia por code.
    """

    __tablename__ = "workstations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_workstation_code"),
        CheckConstraint(
            f"registration_method IN {METODOS_REGISTRO}",
            name="ck_workstation_reg_method",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workstation_groups.id")
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="#3498db")
    hourly_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    registration_method: Mapped[str] = mapped_column(
        String(10), nullable=False, default="quantity"
    )
    maintenance_interval_hours: Mapped[int] = mapped_column(
        nullable=False, default=0
    )  # 0 = deshabilitado
    maintenance_pre_warning_hours: Mapped[int] = mapped_column(nullable=False, default=0)
    last_maintenance_reset: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accumulated_hours: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    group: Mapped[WorkstationGroup | None] = relationship(back_populates="workstations")
