"""Router de autocontrol de calidad (spec 04 §3.2): registro y consulta.

El registro de un autocontrol NUNCA bloquea la producción: un resultado
`rejected` se persiste igual (spec 04 regla 7). Solo lectura para consultas;
los QualityRecord no son inmutables (a diferencia de los ProductionLog).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import autenticar, require_roles
from app.models import User

router = APIRouter(prefix="/api/v1/quality", tags=["quality"])


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


class MeasurementIn(BaseModel):
    check_name: str = Field(max_length=255)
    value_entered: bool | int | float | str


class QualityCheckIn(BaseModel):
    order_id: uuid.UUID
    workstation_id: str = Field(max_length=255)
    manufacturing_model_id: uuid.UUID
    stock_item_id: uuid.UUID | None = None
    measurements: list[MeasurementIn] = Field(max_length=100)
    notes: str | None = Field(default=None, max_length=2000)


class MeasurementOut(BaseModel):
    check_name: str
    value_entered: bool | int | float | str | None
    is_passed: bool
    nominal: Decimal | None
    tol_plus: Decimal | None
    tol_minus: Decimal | None


class QualityRecordOut(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    workstation_id: str
    overall_status: str
    notes: str | None
    created_at: datetime
    operator: dict | None = None
    measurements: list[MeasurementOut] = []


class OperatorOut(BaseModel):
    id: uuid.UUID
    name: str


class PlanCheckOut(BaseModel):
    id: uuid.UUID
    name: str
    tipo: str
    tool_id: str | None
    nominal_value: Decimal | None
    tolerance_plus: Decimal | None
    tolerance_minus: Decimal | None
    is_critical: bool


class ModelOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    material_code: str | None
    quality_plan: list[PlanCheckOut] = []


@router.post("/checks", status_code=201)
def registrar_autocontrol(
    body: QualityCheckIn,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator", "supervisor", "admin")),
    ] = None,
):
    """Registra un autocontrol del operario y devuelve el estado evaluado."""
    from app.services.quality import registrar_autocontrol as service

    try:
        record = service(
            db,
            tenant_id=None,  # TODO: tenant desde el token JWT
            operator_id=current_user.id,
            order_id=body.order_id,
            workstation_id=body.workstation_id,
            manufacturing_model_id=body.manufacturing_model_id,
            stock_item_id=body.stock_item_id,
            mediciones=[m.model_dump() for m in body.measurements],
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "success": True,
        "msg": f"Inspección registrada: {record.overall_status.upper()}",
        "record": _record_out(record),
    }


@router.get("/records")
def get_quality_records(
    db: DbDep,
    order_id: uuid.UUID | None = None,
    limit: int = 20,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator", "supervisor", "admin")),
    ] = None,
):
    """Últimos registros de calidad del tenant (spec 04 §3.2.4)."""
    from app.services.quality import listar_registros

    records = listar_registros(db, current_user.tenant_id, order_id=order_id, limit=limit)
    return {"success": True, "records": [_record_out(r) for r in records]}


@router.get("/reminder-state")
def get_reminder_state(
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator")),
    ] = None,
):
    """Estado para recordatorios de autocontrol (spec 04 §3.2.5).

    Solo el operario lo consume (el recordatorio es UI del panel de
    operario): expone el inicio del turno activo y el último autocontrol
    del usuario autenticado; el frontend calcula los 15 min del primer
    aviso y el ciclo de 2 h. No bloqueantes, sin cadencia en backend.
    """
    from app.services.quality import estado_recordatorios

    return estado_recordatorios(db, current_user.id)


@router.get("/models", response_model=list[ModelOut])
def get_quality_models(
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator", "supervisor", "admin")),
    ] = None,
):
    """Plantillas activas con su plan de controles (para el formulario)."""
    from app.services.quality import listar_modelos

    return [
        ModelOut(
            id=m.id,
            code=m.code,
            name=m.name,
            material_code=m.material_code,
            quality_plan=[
                PlanCheckOut(
                    id=c.id,
                    name=c.name,
                    tipo=c.tipo,
                    tool_id=c.tool_id,
                    nominal_value=c.nominal_value,
                    tolerance_plus=c.tolerance_plus,
                    tolerance_minus=c.tolerance_minus,
                    is_critical=c.is_critical,
                )
                for c in m.quality_plan
            ],
        )
        for m in listar_modelos(db, current_user.tenant_id)
    ]


def _record_out(r) -> dict:
    """Serialización explícita (mismo patrón que trace.py)."""
    return {
        "id": r.id,
        "order_id": r.order_id,
        "workstation_id": r.workstation_id,
        "overall_status": r.overall_status,
        "notes": r.notes,
        "created_at": r.created_at,
        "operator": (
            {"id": r.operator.id, "name": r.operator.name}
            if r.operator is not None
            else None
        ),
        "measurements": [
            {
                "check_name": m.check_name,
                "value_entered": m.value_entered,
                "is_passed": m.is_passed,
                "nominal": m.nominal,
                "tol_plus": m.tol_plus,
                "tol_minus": m.tol_minus,
            }
            for m in r.measurements
        ],
    }
