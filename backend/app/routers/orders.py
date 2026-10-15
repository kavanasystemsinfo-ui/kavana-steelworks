"""Router de órdenes de producción: CRUD, máquina de estados y lecturas.

Fase A1 (ADR-018 y plan de réplica de manufacturing): además del listado
para trazabilidad y del listado del operario, el supervisor/admin puede crear
órdenes con sus líneas, editarlas, lanzarlas, completarlas o descartarlas.
La máquina de estados replica la de kavana-manufacturing
(`orders/:id/transition`): draft -> active -> completed | cancelled.

Patrón de tenant: derivado del JWT (require_roles), igual que el resto de
routers con roles de la demo.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from app.core.database import SessionLocal
from app.core.security import autenticar, require_roles
from app.models import Material, Order, OrderLine, Product, User, Workstation
from app.models.quality import ManufacturingModel
from app.services.sequences import next_sequence

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

LIMITE_ORDENES = 50  # spec 04: límites de listado para no degradar la UI

ESTADOS_FINALES = ("completed", "cancelled")
TRANSICIONES = {
    "draft": ("active", "cancelled"),
    "active": ("completed", "cancelled"),
    "completed": (),
    "cancelled": (),
}


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


class LineIn(BaseModel):
    workstation_id: str = Field(min_length=1, max_length=100)
    total_quantity: float = Field(gt=0)
    linea_numero: int | None = Field(default=None, ge=1)
    product_id: uuid.UUID | None = None
    modelo_id: uuid.UUID | None = None
    material_id: uuid.UUID | None = None
    meters_per_piece: float | None = Field(default=None, gt=0)


class OrderCreateIn(BaseModel):
    cliente: str | None = Field(default=None, max_length=255)
    fecha_entrega: datetime | None = None
    notas: str | None = Field(default=None, max_length=2000)
    estado_inicial: str = Field(default="draft", max_length=20)
    lines: list[LineIn] = Field(min_length=1, max_length=100)


class OrderUpdateIn(BaseModel):
    cliente: str | None = Field(default=None, max_length=255)
    fecha_entrega: datetime | None = None
    notas: str | None = Field(default=None, max_length=2000)


class TransitionIn(BaseModel):
    to: str = Field(min_length=1, max_length=20)


def _order_dict(order: Order) -> dict:
    """Serializa la orden con sus líneas (detalle usado por GET/POST/transition)."""
    return {
        "id": str(order.id),
        "numero": order.numero,
        "estado": order.estado,
        "cliente": order.cliente,
        "fecha_entrega": order.fecha_entrega.isoformat() if order.fecha_entrega else None,
        "notas": order.notas,
        "lines": [
            {
                "id": str(line.id),
                "linea_numero": line.linea_numero,
                "product_id": str(line.product_id) if line.product_id else None,
                "modelo_id": str(line.modelo_id) if line.modelo_id else None,
                "workstation_id": line.workstation_id,
                "estado": line.estado,
                "total_quantity": float(line.total_quantity),
                "produced_quantity": float(line.produced_quantity),
                "material_id": str(line.material_id) if line.material_id else None,
                "active_coil_id": str(line.active_coil_id) if line.active_coil_id else None,
                "active_coil_code": line.active_coil_code,
                "real_material_qty": float(line.real_material_qty),
                "real_material_cost": float(line.real_material_cost),
                "real_cost": float(line.real_cost),
                "scrap_material_qty": float(line.scrap_material_qty),
                "target_material_qty": (
                    float(line.target_material_qty) if line.target_material_qty else None
                ),
                "target_material_unit": line.target_material_unit,
                "meters_per_piece": float(line.meters_per_piece) if line.meters_per_piece else None,
            }
            for line in order.lines
        ],
    }


def _cargar(db: Session, order_id: uuid.UUID, tenant_id: uuid.UUID) -> Order:
    order = (
        db.query(Order)
        .options(selectinload(Order.lines))
        .filter(Order.id == order_id, Order.tenant_id == tenant_id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return order


def _validar_lineas(db: Session, tenant_id: uuid.UUID, lines: list[LineIn]) -> None:
    """Todo lo que referencia una línea debe existir en el tenant."""
    codigos = {
        c
        for (c,) in db.query(Workstation.code).filter(Workstation.tenant_id == tenant_id).all()
    }
    for ln in lines:
        if ln.workstation_id not in codigos:
            raise HTTPException(
                status_code=400,
                detail=f"Puesto de trabajo inexistente: {ln.workstation_id}",
            )
        if ln.modelo_id is not None:
            ok = db.query(ManufacturingModel.id).filter(
                ManufacturingModel.id == ln.modelo_id,
                ManufacturingModel.tenant_id == tenant_id,
            ).first()
            if ok is None:
                raise HTTPException(status_code=400, detail="modelo_id no pertenece al tenant")
        if ln.product_id is not None:
            ok = db.query(Product.id).filter(
                Product.id == ln.product_id, Product.tenant_id == tenant_id
            ).first()
            if ok is None:
                raise HTTPException(status_code=400, detail="product_id no pertenece al tenant")
        if ln.material_id is not None:
            ok = db.query(Material.id).filter(
                Material.id == ln.material_id, Material.tenant_id == tenant_id
            ).first()
            if ok is None:
                raise HTTPException(status_code=400, detail="material_id no pertenece al tenant")


@router.get("", response_model=list[OrderOut])
def list_orders(
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Órdenes del tenant (creación descendente, límite 50)."""
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


@router.get("/available", response_model=list[OrderOut])
def list_available_orders(
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator", "supervisor", "admin")),
    ] = None,
):
    """Órdenes disponibles para el panel del operario (port de manufacturing).

    El operario solo ve las órdenes draft/active de su propia estación de
    trabajo (default_workstation_code), para que el panel no dependa del
    listado supervisor (403) y no termine enviando order_id nulo.
    """
    from app.models import OrderLine

    ws_code = current_user.default_workstation_code
    if not ws_code:
        return []

    ordenes = (
        db.query(Order)
        .join(OrderLine, OrderLine.order_id == Order.id)
        .filter(
            Order.tenant_id == current_user.tenant_id,
            Order.estado.in_(("active", "draft")),
            OrderLine.workstation_id == ws_code,
        )
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


@router.post("", status_code=201)
def create_order(
    body: OrderCreateIn,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Crea una orden con sus líneas (número automático por secuencia)."""
    if body.estado_inicial not in ("draft", "active"):
        raise HTTPException(status_code=400, detail="estado_inicial debe ser draft o active")

    _validar_lineas(db, current_user.tenant_id, body.lines)

    numero = next_sequence(db, current_user.tenant_id, "order")
    order = Order(
        tenant_id=current_user.tenant_id,
        numero=numero,
        estado=body.estado_inicial,
        cliente=body.cliente,
        fecha_entrega=body.fecha_entrega,
        notas=body.notas,
    )
    db.add(order)
    db.flush()
    for idx, ln in enumerate(body.lines, start=1):
        db.add(
            OrderLine(
                order_id=order.id,
                linea_numero=ln.linea_numero or idx,
                product_id=ln.product_id,
                modelo_id=ln.modelo_id,
                material_id=ln.material_id,
                workstation_id=ln.workstation_id,
                estado="pending",
                total_quantity=ln.total_quantity,
                meters_per_piece=ln.meters_per_piece,
            )
        )
    db.commit()
    order = _cargar(db, order.id, current_user.tenant_id)
    return _order_dict(order)


@router.put("/{order_id}")
def update_order(
    order_id: uuid.UUID,
    body: OrderUpdateIn,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Edita la cabecera de la orden (cliente, fecha de entrega, notas)."""
    order = _cargar(db, order_id, current_user.tenant_id)
    if order.estado in ESTADOS_FINALES:
        raise HTTPException(status_code=409, detail="La orden ya está cerrada")

    cambios = body.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(order, campo, valor)
    db.commit()
    order = _cargar(db, order.id, current_user.tenant_id)
    return _order_dict(order)


@router.post("/{order_id}/transition")
def transition_order(
    order_id: uuid.UUID,
    body: TransitionIn,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Máquina de estados de la orden (port de manufacturing).

    Legal: draft -> active | cancelled, active -> completed | cancelled.
    Al completar, todas las líneas pendientes pasan a completed.
    """
    if body.to not in ("active", "completed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Destino de transición inválido: {body.to}")

    order = _cargar(db, order_id, current_user.tenant_id)
    if body.to not in TRANSICIONES[order.estado]:
        raise HTTPException(
            status_code=409,
            detail=f"Transición ilegal: {order.estado} -> {body.to}",
        )

    order.estado = body.to
    if body.to == "completed":
        for line in order.lines:
            if line.estado != "completed":
                line.estado = "completed"
    db.commit()
    order = _cargar(db, order.id, current_user.tenant_id)
    return _order_dict(order)


@router.delete("/{order_id}", status_code=204)
def delete_order(
    order_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Elimina una orden solo mientras es borrador (las líneas caen en cascada)."""
    order = _cargar(db, order_id, current_user.tenant_id)
    if order.estado != "draft":
        raise HTTPException(status_code=409, detail="Solo se pueden eliminar borradores")
    db.delete(order)
    db.commit()


@router.get("/{order_id}", response_model=dict)
def get_order(
    order_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator", "supervisor", "admin")),
    ] = None,
):
    """Obtener una orden específica con sus líneas para edición/vinculación."""
    order = _cargar(db, order_id, current_user.tenant_id)
    return _order_dict(order)
