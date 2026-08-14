"""Router de stock-items: recepción de bobinas (Materias Primas, spec 06)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Material
from app.services import receiving as receiving_service

router = APIRouter(prefix="/api/v1/stock-items", tags=["stock"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbDep = Annotated[Session, Depends(get_db)]


class ReceiveCoilRequest(BaseModel):
    tenant_id: uuid.UUID
    material_id: uuid.UUID
    lote: str
    coil_id: str | None = None
    peso: Decimal = Field(gt=0)
    width_mm: Decimal | None = None
    thickness_mm: Decimal | None = None
    coste_real: Decimal | None = Field(default=None, ge=0)
    ubicacion: str | None = None
    heat_number: str | None = None
    grado_acero: str | None = None
    supplier_coil_id: str | None = None


class ReceiveCoilResponse(BaseModel):
    id: uuid.UUID
    lote: str
    coil_id: str | None
    estado: str
    peso: Decimal
    ubicacion: str | None
    costo_method: str

    class Config:
        from_attributes = True


@router.post("", response_model=ReceiveCoilResponse)
def receive(body: ReceiveCoilRequest, db: DbDep):
    """Registra una bobina entrante (entrada directa a producción)."""
    try:
        bobina = receiving_service.receive_coil(
            db,
            body.tenant_id,
            user_id=None,  # TODO: user desde el token JWT
            material_id=body.material_id,
            lote=body.lote,
            coil_id=body.coil_id,
            peso=body.peso,
            width_mm=body.width_mm,
            thickness_mm=body.thickness_mm,
            coste_real=body.coste_real,
            ubicacion=body.ubicacion,
            heat_number=body.heat_number,
            grado_acero=body.grado_acero,
            supplier_coil_id=body.supplier_coil_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ReceiveCoilResponse(
        id=bobina.id,
        lote=bobina.lote,
        coil_id=bobina.coil_id,
        estado=bobina.estado,
        peso=bobina.cantidad_disponible,
        ubicacion=bobina.ubicacion,
        costo_method=bobina.costing_method,
    )


class StockItemOut(BaseModel):
    id: uuid.UUID
    lote: str
    coil_id: str | None
    material_id: uuid.UUID
    cantidad_disponible: Decimal
    estado: str
    ubicacion: str | None
    fecha_entrada: datetime | None

    class Config:
        from_attributes = True


class MaterialOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    cost_per_unit: Decimal | None
    unit: str | None
    stock_current: Decimal | None

    class Config:
        from_attributes = True


@router.get("/materials", response_model=list[MaterialOut])
def list_materials(db: DbDep):
    """Lista materiales activos del tenant (para el formulario de recepción)."""
    return db.query(Material).filter(Material.is_active == True).all()  # noqa: E712


class PicoSugerencia(BaseModel):
    """Pico/retal disponible en almacén (sugerencia de uso, idea Jorge)."""

    stock_item_id: uuid.UUID
    lote: str
    coil_id: str | None
    material_code: str
    peso_kg: Decimal
    ubicacion: str | None
    fecha_entrada: datetime | None


@router.get("/picos", response_model=list[PicoSugerencia])
def sugerencias_picos(db: DbDep):
    """Picos y retales en almacén para aconsejar su uso antes de abrir
    bobina nueva. Sugerencia visible, nunca imposición (decisión Jorge)."""
    from app.models import StockItem

    items = (
        db.query(StockItem)
        .filter(StockItem.estado.in_(["pico", "retal"]))
        .order_by(StockItem.fecha_entrada.asc())
        .all()
    )
    return [
        PicoSugerencia(
            stock_item_id=i.id,
            lote=i.lote,
            coil_id=i.coil_id,
            material_code=i.material.code if i.material else "?",
            peso_kg=i.cantidad_disponible,
            ubicacion=i.ubicacion,
            fecha_entrada=i.fecha_entrada,
        )
        for i in items
    ]


@router.get("", response_model=list[StockItemOut])
def list_stock(db: DbDep):
    """Lista bobinas (para el panel de Materias Primas)."""
    from app.models import StockItem

    return db.query(StockItem).order_by(StockItem.fecha_entrada.desc()).limit(100).all()
