"""Sesiones de subida de fotos de incidencias (flujo QR + móvil, spec 04 §3.3.2).

Portado de kavana-manufacturing (tabla incidencia_uploads): el session_id es
una credencial de un solo uso con TTL (15 min); la foto se guarda como BYTEA
en la sesión y se copia a la incidencia al crearla (finalize). El móvil
anónimo solo conoce el session_id; el tenant se resuelve desde la propia
sesión.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin

ESTADOS_SESION = ("pending", "uploaded", "used", "expired")
_ESTADOS_SQL = ", ".join(f"'{e}'" for e in ESTADOS_SESION)


class IncidenciaUploadSession(UUIDMixin, TimestampMixin, Base):
    """Sesión de subida de foto de incidencia (credencial de un solo uso)."""

    __tablename__ = "incidencia_uploads"
    __table_args__ = (
        CheckConstraint(f"status IN ({_ESTADOS_SQL})", name="ck_incidencia_upload_status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, unique=True, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="pending"
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    photo: Mapped[bytes | None] = mapped_column(LargeBinary)
    photo_mime: Mapped[str | None] = mapped_column(String(50))
    photo_size: Mapped[int | None] = mapped_column()
    incidencia_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidencias.id")
    )
