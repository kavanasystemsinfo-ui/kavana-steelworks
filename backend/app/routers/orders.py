"""Router de órdenes de producción: listado para el selector de trazabilidad.

La UI de trazabilidad (panel Supervisor, Fase 5) necesita elegir una orden
y ver su serie de eventos. Este endpoint lista las órdenes del tenant con
los campos mínimos para el selector, ordenadas por creación descendente.

Patrón de tenant de la demo (igual que supervisor.py): sin auth por roles
todavía, se usa el primer tenant. Pendiente Fase 5: tenant desde el JWT.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.database import SessionLocal

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

LIMITE_ORDENES = 50  # spec 04: límites de listado para no degradar la UI


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbDep = Annotated[Session, Depends(get_db)]


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero: str
    estado: str
    cliente: str | None = None
    fecha_entrega: datetime | None = None


@router.get("", response_model=list[OrderOut])
def list_orders(db: DbDep):
    """Órdenes del tenant de la demo (creación descendente, límite 50)."""
    from app.models import Order, Tenant

    tenant = db.query(Tenant).order_by(Tenant.created_at).first()
    if tenant is None:
        return []

    return (
        db.query(Order)
        .filter(Order.tenant_id == tenant.id)
        .order_by(Order.created_at.desc())
        .limit(LIMITE_ORDENES)
        .all()
    )
