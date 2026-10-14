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

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import autenticar, require_roles
from app.models import Order, User

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


@router.get("/available", response_model=list[OrderOut])
def list_available_orders(
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator", "supervisor", "admin")),
    ] = None,
):
    """Órdenes disponibles para el panel del operario (port de manufacturing).

    A diferencia del listado global (solo supervisor/admin), el operario solo
    ve las órdenes activas de su propia estación de trabajo, derivada de
    default_workstation_code del usuario. Esto evita que el panel del operario
    dependa del listado supervisor (que le devolvía 403) y termine enviando
    un order_id nulo al registrar producción.
    """
    from app.models import Order, OrderLine

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
    from sqlalchemy.orm import selectinload

    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.tenant_id == current_user.tenant_id)
        .options(selectinload(Order.lines))
        .first()
    )

    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    # Convert to dict to include lines
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
