"""Router de trazabilidad ISO 9001 (spec 04 §3.1): consulta de traza por orden.

Solo lectura: los ProductionLog son inmutables, no hay endpoints de
modificación ni borrado (la inmutabilidad real se garantiza en PostgreSQL
con trigger, migración 04).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Order

router = APIRouter(prefix="/api/v1/trace", tags=["traceability"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbDep = Annotated[Session, Depends(get_db)]


class OperatorOut(BaseModel):
    id: uuid.UUID
    name: str


class TraceEventOut(BaseModel):
    id: uuid.UUID
    action: str
    quantity: Decimal
    timestamp: datetime
    metadata: dict | None = None
    shift: str | None = None
    operator: OperatorOut | None = None


@router.get("/orders/{order_id}", response_model=list[TraceEventOut])
def get_order_trace(order_id: uuid.UUID, db: DbDep):
    """Serie temporal completa de eventos de una orden (timestamp asc)."""
    from app.services.traceability import get_order_trace as trace_service

    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    logs = trace_service(db, order.tenant_id, order_id)
    return [
        TraceEventOut(
            id=log.id,
            action=log.action,
            quantity=log.quantity,
            timestamp=log.timestamp,
            # SQLAlchemy JSON mutable devuelve un wrapper; normalizar a dict
            metadata=dict(log.metadata_ or {}),
            shift=log.shift,
            operator=(
                OperatorOut(id=log.operator.id, name=log.operator.name)
                if log.operator is not None
                else None
            ),
        )
        for log in logs
    ]
