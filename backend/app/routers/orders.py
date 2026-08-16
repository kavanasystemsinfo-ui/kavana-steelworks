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

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import autenticar, require_roles
from app.models import User

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

LIMITE_ORDENES = 50  # spec 04: límites de listado para no degradar la UI


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbDep = Annotated[Session, Depends(get_db)]


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: DbDep = None,
) -> User:
    return autenticar(db, authorization)


class OrderOut(BaseModel):
    id: uuid.UUID
    numero: str
    estado: str
    cliente: str | None = None
    fecha_entrega: datetime | None = None
    workstation_id: str | None = None  # puesto de la primera línea (autocontrol)


@router.get("", response_model=list[OrderOut])
def list_orders(
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Órdenes del tenant de la demo (creación descendente, límite 50)."""
    from app.models import Order

    ordenes = (
        db.query(Order)
        .filter(Order.tenant_id == current_user.tenant_id)
        .order_by(Order.created_at.desc())
        .limit(LIMITE_ORDENES)
        .all()
    )
    return [
        OrderOut(
            id=o.id,
            numero=o.numero,
            estado=o.estado,
            cliente=o.cliente,
            fecha_entrega=o.fecha_entrega,
            workstation_id=o.lines[0].workstation_id if o.lines else None,
        )
        for o in ordenes
    ]
