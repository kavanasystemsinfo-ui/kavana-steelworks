"""Calculadora de embalaje de un puesto (port de CalculatorPreset del legacy).

El operario crea plantillas con nombre en su puesto: piezas por paquete ×
paquetes por fila × filas por palet. En el panel registra con +1 palet,
+1 fila, +1 paquete o +1 pieza en lugar de contar piezas (Jorge, 28-10: las
crea el operario y las ve cualquiera de ese puesto).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CalculadoraPuesto(Base):
    __tablename__ = "calculadoras_puesto"
    __table_args__ = (
        UniqueConstraint("tenant_id", "puesto", "nombre", name="uq_calculadora_puesto_nombre"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    puesto: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    piezas_paquete: Mapped[int] = mapped_column(Integer, nullable=False)
    paquetes_fila: Mapped[int] = mapped_column(Integer, nullable=False)
    filas_palet: Mapped[int] = mapped_column(Integer, nullable=False)
    creada_por: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @property
    def piezas_fila(self) -> int:
        return self.piezas_paquete * self.paquetes_fila

    @property
    def piezas_palet(self) -> int:
        return self.piezas_fila * self.filas_palet
