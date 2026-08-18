"""Modelos de identidad: Tenant y User."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin

ESTADOS_TENANT = ("active", "suspended", "trial")


class Tenant(UUIDMixin, TimestampMixin, Base):
    """Empresa arrendataria. Todo el sistema es multi-tenant por tenant_id.

    Spec 07 (ADR-015): se amplía desde el cascarón (name, is_active) al
    modelo configurable del v2. `theme` y `finances` son JSONB (config pura);
    roles, secuencias y puestos viven en tablas normalizadas.
    """

    __tablename__ = "tenants"
    __table_args__ = (CheckConstraint(f"status IN {ESTADOS_TENANT}", name="ck_tenant_status"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="active")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # auth: método de login y si pide número de línea (JSONB, config pura)
    auth: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # theme: colores y branding (JSONB)
    theme: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # finances: coste global y categorías de operario (JSONB)
    finances: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # sequences: config de prefix/padding por tipo (el contador vivo en tabla sequences)
    sequences_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    users: Mapped[list["User"]] = relationship(back_populates="tenant")


class User(UUIDMixin, TimestampMixin, Base):
    """Usuario del sistema (operario, supervisor, materias, admin).

    JWT de 8 horas = un turno estándar de fábrica (decisión legacy).
    Roles: operator | supervisor | materials | admin.
    Spec 07: employee_number (login por empleado) y puesto por defecto.
    """

    __tablename__ = "users"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="operator"
    )  # operator | supervisor | materials | admin
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Spec 07: empleado (login method employee_id) y puesto por defecto
    employee_number: Mapped[str | None] = mapped_column(String(64), index=True)
    default_workstation_code: Mapped[str | None] = mapped_column(String(100))

    tenant: Mapped[Tenant] = relationship(back_populates="users")
