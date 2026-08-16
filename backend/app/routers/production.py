"""Router de producción: registro de piezas con auto-consumo FIFO (spec 02 3.4)."""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import SessionLocal

router = APIRouter(prefix="/api/v1/production", tags=["production"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbDep = Annotated[Session, Depends(get_db)]


class RecordProductionRequest(BaseModel):
    order_id: uuid.UUID
    line_id: uuid.UUID
    incremental_quantity: Decimal = Field(ge=0)
    hours_worked: Decimal = Field(default=0, ge=0)
    observaciones: str | None = Field(default=None, max_length=2000)


@router.post("/record")
def record_production(body: RecordProductionRequest, db: DbDep):
    """Registra producción incremental: el FIFO consume el material automático.

    Modo auditoría (línea con bobina vinculada): consume por burbuja de
    vinculación priorizando la bobina activa; el fallo bloquea. Modo simple
    (sin bobina): FIFO global y el fallo no bloquea (nunca consumos fantasma).
    """
    from app.services.production import record_production as record_service

    try:
        return record_service(
            db,
            tenant_id=None,  # TODO: tenant desde el token JWT
            user_id=None,  # TODO: user desde el token JWT (se resuelve en servicio)
            order_id=body.order_id,
            line_id=body.line_id,
            incremental_quantity=body.incremental_quantity,
            hours_worked=body.hours_worked,
            observaciones=body.observaciones or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
