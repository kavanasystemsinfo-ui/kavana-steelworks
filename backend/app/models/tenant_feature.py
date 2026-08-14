"""Feature flags por tenant (ADR-003): módulos activables por plan."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TenantFeature(Base):
    """Features habilitadas de un tenant (mapa JSONB, patrón del v3).

    El catálogo de features y los planes viven en app/core/features.py.
    JSON portable (JSONB en PostgreSQL, JSON en SQLite para tests).
    """

    __tablename__ = "tenant_features"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    plan: Mapped[str] = mapped_column(default="basico", nullable=False)
    features: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
