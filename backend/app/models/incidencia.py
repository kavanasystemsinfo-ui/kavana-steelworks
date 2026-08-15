"""Modelos de incidencias de planta (spec 04 §2.4 y §6).

- Incidencia: reporte del operario con estado y resolución financiera
  (la resolución conserva los campos previos si el update no los trae,
  igual que el objeto embebido del legacy).
- IncidenciaHistorial: traza de cambios de estado (la primera fila se
  inserta en el alta, estado 'abierta').
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.models.tenant import User

TIPOS_INCIDENCIA = ("maquina", "material", "seguridad", "otro")
ESTADOS_INCIDENCIA = ("abierta", "en_revision", "resuelta", "cerrada")
_TIPOS_SQL = ", ".join(f"'{t}'" for t in TIPOS_INCIDENCIA)
_ESTADOS_SQL = ", ".join(f"'{e}'" for e in ESTADOS_INCIDENCIA)


class Incidencia(UUIDMixin, TimestampMixin, Base):
    """Incidencia de planta: reporte, estados y cierre financiero."""

    __tablename__ = "incidencias"
    __table_args__ = (
        CheckConstraint(f"tipo IN ({_TIPOS_SQL})", name="ck_incidencia_tipo"),
        CheckConstraint(
            f"estado IN ({_ESTADOS_SQL})", name="ck_incidencia_estado"
        ),
        CheckConstraint("tiempo_parada_min >= 0", name="ck_incidencia_tiempo"),
        CheckConstraint("coste >= 0", name="ck_incidencia_coste"),
        Index("ix_incidencia_tenant_estado_ts", "tenant_id", "estado", "created_at"),
        Index("ix_incidencia_tenant_tipo", "tenant_id", "tipo"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orders.id")
    )
    linea_id: Mapped[str | None] = mapped_column(String(100))
    puesto: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    operario_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, default="otro")
    foto: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="abierta")

    # Resolución financiera (spec 04 §3.3: campos independientes, conservan
    # su valor previo si el update no los trae)
    resolucion_tipo: Mapped[str | None] = mapped_column(String(50))
    resolucion_descripcion: Mapped[str | None] = mapped_column(Text)
    tiempo_parada_min: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    coste: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    responsable_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id")
    )

    operario: Mapped[User] = relationship(
        "User", foreign_keys=[operario_id], lazy="joined"
    )
    responsable: Mapped[User | None] = relationship(
        "User", foreign_keys=[responsable_id], lazy="joined"
    )
    historial: Mapped[list["IncidenciaHistorial"]] = relationship(
        back_populates="incidencia",
        cascade="all, delete-orphan",
        order_by="IncidenciaHistorial.timestamp",
    )


class IncidenciaHistorial(UUIDMixin, TimestampMixin, Base):
    """Cambio de estado de una incidencia (traza de auditoría)."""

    __tablename__ = "incidencia_historial_estados"

    incidencia_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("incidencias.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    comentario: Mapped[str | None] = mapped_column(Text)

    incidencia: Mapped[Incidencia] = relationship(back_populates="historial")
    usuario: Mapped[User] = relationship("User", lazy="joined")
