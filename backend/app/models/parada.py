"""Parada de máquina registrada por el operario con un toque (fase 3 del
rediseño del panel de operario, Jorge 28-10).

No es una incidencia: limpieza, ajustes o un cambio de modelo no hay que
gestionarlos, solo medirlos. El operario toca el motivo, el tiempo cuenta
solo y al volver a producir se cierra. El panel de mando las suma a las
paradas igual que las incidencias.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

MOTIVOS_PARADA = {
    "averia": "avería",
    "ajustes": "ajustes",
    "cambio_modelo": "cambio de modelo",
    "limpieza": "limpieza",
    "mantenimiento": "mantenimiento",
    "otros": "otros",
}
_MOTIVOS_SQL = ", ".join(f"'{m}'" for m in MOTIVOS_PARADA)


class Parada(Base):
    __tablename__ = "paradas"
    __table_args__ = (CheckConstraint(f"motivo IN ({_MOTIVOS_SQL})", name="ck_parada_motivo"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    puesto: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    operario_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orders.id"), nullable=True
    )
    line_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    motivo: Mapped[str] = mapped_column(String(20), nullable=False)
    nota: Mapped[str | None] = mapped_column(Text)
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
