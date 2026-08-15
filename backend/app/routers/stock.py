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
        .filter(
            StockItem.estado.in_(["pico", "retal"]),
            StockItem.ubicacion == "Retales",  # solo picos retirados al almacén
        )
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


@router.get("/scan", response_model=dict | None)
def scan_coil(coil_id: str | None = None, lote: str | None = None, db: DbDep = None):
    """Escaneo de bobina (flujo operario): busca por coil_id o lote.

    Modo automático: devuelve material, dimensiones y peso. Modo manual:
    el operario ajusta peso y lote desde la etiqueta física.
    """
    from app.services.inventory import find_coil

    try:
        return find_coil(db, None, coil_id=coil_id, lote=lote)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class LinkCoilRequest(BaseModel):
    stock_item_id: uuid.UUID
    order_id: uuid.UUID
    line_id: uuid.UUID


@router.post("/link")
def link(body: LinkCoilRequest, db: DbDep):
    """Vincula la bobina a la orden (cobro BULK por adelantado)."""
    from app.services.inventory import link_coil

    try:
        return link_coil(
            db,
            tenant_id=None,  # TODO: tenant desde el token JWT
            user_id=None,
            stock_item_id=body.stock_item_id,
            order_id=body.order_id,
            line_id=body.line_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class FinBobinaRequest(BaseModel):
    stock_item_id: uuid.UUID
    order_id: uuid.UUID
    line_id: uuid.UUID
    radio_mm: float = Field(ge=0)


@router.post("/fin-bobina")
def fin_bobina(body: FinBobinaRequest, db: DbDep):
    """Fin de bobina: el operario mide los milímetros de radio restantes
    y el sistema convierte a kg con la fórmula v2 (Densidad Calibrada Kavana)."""
    from app.services.inventory import create_retal

    try:
        return create_retal(
            db,
            tenant_id=None,  # TODO: tenant desde el token JWT
            user_id=None,
            stock_item_id=body.stock_item_id,
            radio_mm=body.radio_mm,
            order_id=body.order_id,
            line_id=body.line_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class RetirarPicoRequest(BaseModel):
    stock_item_id: uuid.UUID
    order_id: uuid.UUID | None = None
    line_id: uuid.UUID | None = None


@router.post("/retirar")
def retirar(body: RetirarPicoRequest, db: DbDep):
    """Botón 'Retirar': segunda opción del fin de bobina (visión Jorge).

    Devuelve el pico al inventario (ubicación 'Retales'). Aparecerá después
    como material SUGERIDO cuando una orden use ese material. Es distinto
    del fin de bobina, que deja el pico en la máquina.
    """
    from app.services.inventory import retirar_pico

    try:
        return retirar_pico(
            db,
            tenant_id=None,  # TODO: tenant desde el token JWT
            user_id=None,
            stock_item_id=body.stock_item_id,
            order_id=body.order_id,
            line_id=body.line_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[StockItemOut])
def list_stock(db: DbDep):
    """Lista bobinas (para el panel de Materias Primas)."""
    from app.models import StockItem

    return db.query(StockItem).order_by(StockItem.fecha_entrada.desc()).limit(100).all()
