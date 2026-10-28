"""Router de producción: registro de piezas con auto-consumo FIFO (spec 02 3.4)."""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import autenticar, require_roles
from app.models import User

router = APIRouter(prefix="/api/v1/production", tags=["production"])


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


class Desglose(BaseModel):
    """Cómo se contaron las piezas con la calculadora del puesto."""

    calculadora: str | None = Field(default=None, max_length=120)
    palets: int = Field(default=0, ge=0)
    filas: int = Field(default=0, ge=0)
    paquetes: int = Field(default=0, ge=0)
    piezas: int = Field(default=0, ge=0)


class RecordProductionRequest(BaseModel):
    order_id: uuid.UUID
    line_id: uuid.UUID
    incremental_quantity: Decimal = Field(ge=0)
    # Sin horas (0), se cuentan solas desde el último registro del operario en
    # la línea o desde que inició sesión (rediseño del panel, 28-10)
    hours_worked: Decimal = Field(default=0, ge=0)
    observaciones: str | None = Field(default=None, max_length=2000)
    desglose: Desglose | None = None


@router.post("/record")
def record_production(
    body: RecordProductionRequest,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator")),
    ] = None,
):
    """Registra producción incremental: el FIFO consume el material automático.

    Modo auditoría (línea con bobina vinculada): consume por burbuja de
    vinculación priorizando la bobina activa; el fallo bloquea. Modo simple
    (sin bobina): FIFO global y el fallo no bloquea (nunca consumos fantasma).
    """
    from app.services.ficha_operario import horas_automaticas
    from app.services.production import record_production as record_service

    horas = body.hours_worked
    if horas == 0 and body.incremental_quantity > 0:
        horas = horas_automaticas(db, current_user.id, body.line_id)
    try:
        return record_service(
            db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            order_id=body.order_id,
            line_id=body.line_id,
            incremental_quantity=body.incremental_quantity,
            hours_worked=horas,
            observaciones=body.observaciones or "",
            desglose=body.desglose.model_dump() if body.desglose else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/ficha")
def ficha(
    order_id: uuid.UUID,
    line_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator")),
    ] = None,
):
    """Datos clave de la orden para el panel de operario: orden, cliente,
    entrega, modelo, material con medidas, largo, ritmo, lo hecho y la bobina
    montada (kilos y para cuántas piezas dan)."""
    from app.services.ficha_operario import ficha_orden

    try:
        return ficha_orden(db, current_user.tenant_id, current_user.id, order_id, line_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class CalculadoraIn(BaseModel):
    puesto: str = Field(min_length=1, max_length=100)
    nombre: str = Field(min_length=1, max_length=120)
    piezas_paquete: int = Field(ge=1, le=100000)
    paquetes_fila: int = Field(ge=1, le=1000)
    filas_palet: int = Field(ge=1, le=1000)


def _calculadora_dict(c) -> dict:
    return {
        "id": str(c.id),
        "puesto": c.puesto,
        "nombre": c.nombre,
        "piezas_paquete": c.piezas_paquete,
        "paquetes_fila": c.paquetes_fila,
        "filas_palet": c.filas_palet,
        "piezas_fila": c.piezas_fila,
        "piezas_palet": c.piezas_palet,
    }


@router.get("/calculadoras")
def listar_calculadoras(
    puesto: str,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator")),
    ] = None,
):
    """Calculadoras de embalaje del puesto (las ve cualquier operario de él)."""
    from sqlalchemy import select

    from app.models import CalculadoraPuesto

    return [
        _calculadora_dict(c)
        for c in db.scalars(
            select(CalculadoraPuesto)
            .where(
                CalculadoraPuesto.tenant_id == current_user.tenant_id,
                CalculadoraPuesto.puesto == puesto,
            )
            .order_by(CalculadoraPuesto.created_at.asc())
        )
    ]


@router.post("/calculadoras", status_code=201)
def crear_calculadora(
    body: CalculadoraIn,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator")),
    ] = None,
):
    """El operario guarda una calculadora en su puesto (Jorge, 28-10)."""
    from sqlalchemy import select

    from app.models import CalculadoraPuesto

    nombre = body.nombre.strip()
    repetida = db.scalar(
        select(CalculadoraPuesto).where(
            CalculadoraPuesto.tenant_id == current_user.tenant_id,
            CalculadoraPuesto.puesto == body.puesto,
            CalculadoraPuesto.nombre == nombre,
        )
    )
    if repetida is not None:
        raise HTTPException(
            status_code=409, detail=f"Ya hay una calculadora «{nombre}» en este puesto"
        )
    calc = CalculadoraPuesto(
        tenant_id=current_user.tenant_id,
        puesto=body.puesto,
        nombre=nombre,
        piezas_paquete=body.piezas_paquete,
        paquetes_fila=body.paquetes_fila,
        filas_palet=body.filas_palet,
        creada_por=current_user.id,
    )
    db.add(calc)
    db.commit()
    db.refresh(calc)
    return _calculadora_dict(calc)
