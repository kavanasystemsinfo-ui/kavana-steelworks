"""Clave de idempotencia del registro de producción (T-159, auditoría H1).

Cada parte que el operario envía desde la tablet lleva un client_request_id
(uuid generado una sola vez al pulsar «Registrar»). La primera petición
guarda aquí su respuesta; un reintento con el mismo id la devuelve sin
registrar nada. El UNIQUE (tenant_id, client_request_id) resuelve la
carrera de dos peticiones simultáneas: la segunda choca, relee y devuelve.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# JSONB en PostgreSQL (producción), JSON genérico en SQLite (tests)
_ResponseJSON = JSON().with_variant(JSONB, "postgresql")


class ProductionRequest(Base):
    """Petición de registro ya atendida (respuesta guardada para reintentos)."""

    __tablename__ = "production_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "client_request_id", name="uq_production_request_cliente"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    client_request_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(_ResponseJSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
