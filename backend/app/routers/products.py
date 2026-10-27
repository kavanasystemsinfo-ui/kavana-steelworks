"""Router del catálogo de productos terminados y su lista de materiales (BOM).

Fase A2 (ADR-018): API CRUD completa para que la UI admin gestione el
catálogo (crear producto, definir componentes pieza/material) y para que el
form de órdenes del supervisor pueda referenciar productos existentes.

Reglas: cada componente apunta exactamente a un modelo de fabricación O a un
material (XOR validado aquí para devolver 400 en vez de un 500 por el CHECK
de BD); todo lo referenciado pertenece al tenant; el código es único por
tenant; un producto referenciado por líneas de orden no se puede borrar.
"""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.database import SessionLocal
from app.core.security import autenticar, require_roles
from app.models import Material, OrderLine, Product, ProductComponent, User
from app.models.quality import ManufacturingModel

router = APIRouter(prefix="/api/v1/products", tags=["products"])


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


class ComponentIn(BaseModel):
    manufacturing_model_id: uuid.UUID | None = None
    material_id: uuid.UUID | None = None
    quantity: Decimal = Field(default=Decimal("0"), ge=0)
    unit: str = Field(default="uds", max_length=10)


class ProductIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True
    components: list[ComponentIn] = Field(default_factory=list, max_length=200)


class ProductPatchIn(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None
    components: list[ComponentIn] | None = Field(default=None, max_length=200)


class ComponentOut(BaseModel):
    id: uuid.UUID
    manufacturing_model_id: uuid.UUID | None = None
    material_id: uuid.UUID | None = None
    quantity: float
    unit: str
    position: int


class ProductOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    is_active: bool
    components: list[ComponentOut]


def _component_out(c: ProductComponent) -> dict:
    modelo = c.manufacturing_model_id
    return {
        "id": str(c.id),
        "manufacturing_model_id": str(modelo) if modelo else None,
        "material_id": str(c.material_id) if c.material_id else None,
        "quantity": float(c.quantity),
        "unit": c.unit,
        "position": c.position,
    }


def _product_dict(p: Product) -> dict:
    return {
        "id": str(p.id),
        "code": p.code,
        "name": p.name,
        "description": p.description,
        "is_active": p.is_active,
        "components": [_component_out(c) for c in p.components],
    }


def _validar_componentes(db: Session, tenant_id: uuid.UUID, comps: list[ComponentIn]) -> None:
    for c in comps:
        if (c.manufacturing_model_id is None) == (c.material_id is None):
            raise HTTPException(
                status_code=400,
                detail="Cada componente debe referenciar exactamente un modelo o un material",
            )
        if c.manufacturing_model_id is not None:
            ok = (
                db.query(ManufacturingModel.id)
                .filter(
                    ManufacturingModel.id == c.manufacturing_model_id,
                    ManufacturingModel.tenant_id == tenant_id,
                )
                .first()
            )
            if ok is None:
                raise HTTPException(status_code=400, detail="manufacturing_model_id no existe")
        if c.material_id is not None:
            ok = (
                db.query(Material.id)
                .filter(Material.id == c.material_id, Material.tenant_id == tenant_id)
                .first()
            )
            if ok is None:
                raise HTTPException(status_code=400, detail="material_id no existe")


def _validar_code(db: Session, tenant_id: uuid.UUID, code: str, excluir: uuid.UUID | None = None):
    q = db.query(Product.id).filter(Product.tenant_id == tenant_id, Product.code == code)
    if excluir is not None:
        q = q.filter(Product.id != excluir)
    if q.first() is not None:
        raise HTTPException(status_code=409, detail=f"Ya existe un producto con el código {code}")


def _aplicar_componentes(product: Product, comps: list[ComponentIn]) -> None:
    product.components.clear()
    for idx, c in enumerate(comps, start=1):
        product.components.append(
            ProductComponent(
                manufacturing_model_id=c.manufacturing_model_id,
                material_id=c.material_id,
                quantity=c.quantity,
                unit=c.unit,
                position=idx,
            )
        )


def _cargar(db: Session, product_id: uuid.UUID, tenant_id: uuid.UUID) -> Product:
    p = (
        db.query(Product)
        .options(selectinload(Product.components))
        .filter(Product.id == product_id, Product.tenant_id == tenant_id)
        .first()
    )
    if p is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return p


@router.get("", response_model=list[ProductOut])
def list_products(
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Catálogo del tenant con sus BOMs (supervisor/admin)."""
    productos = (
        db.query(Product)
        .options(selectinload(Product.components))
        .filter(Product.tenant_id == current_user.tenant_id)
        .order_by(Product.code)
        .all()
    )
    return [_product_dict(p) for p in productos]


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Detalle de un producto con su BOM."""
    return _product_dict(_cargar(db, product_id, current_user.tenant_id))


@router.post("", status_code=201)
def create_product(
    body: ProductIn,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Crea un producto con su lista de materiales."""
    _validar_code(db, current_user.tenant_id, body.code)
    _validar_componentes(db, current_user.tenant_id, body.components)

    p = Product(
        tenant_id=current_user.tenant_id,
        code=body.code,
        name=body.name,
        description=body.description,
        is_active=body.is_active,
    )
    db.add(p)
    db.flush()
    _aplicar_componentes(p, body.components)
    db.commit()
    return _product_dict(_cargar(db, p.id, current_user.tenant_id))


@router.put("/{product_id}")
def update_product(
    product_id: uuid.UUID,
    body: ProductPatchIn,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Edita el producto; si vienen componentes, reemplaza la BOM completa."""
    p = _cargar(db, product_id, current_user.tenant_id)
    cambios = body.model_dump(exclude_unset=True)
    if "code" in cambios:
        _validar_code(db, current_user.tenant_id, cambios["code"], excluir=p.id)
    if "components" in cambios:
        _validar_componentes(db, current_user.tenant_id, body.components or [])

    for campo in ("code", "name", "description", "is_active"):
        if campo in cambios:
            setattr(p, campo, cambios[campo])
    if "components" in cambios:
        _aplicar_componentes(p, body.components or [])
    db.commit()
    return _product_dict(_cargar(db, p.id, current_user.tenant_id))


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Borra el producto y su BOM (409 si líneas de orden lo referencian)."""
    p = _cargar(db, product_id, current_user.tenant_id)

    # Validación explícita: en SQLite las FKs no están activas por defecto y el
    # IntegrityError de PG no saltaría; las líneas referenciadas prohíben borrar.
    usada_por = db.query(OrderLine.id).filter(OrderLine.product_id == p.id).first()
    if usada_por is not None:
        raise HTTPException(
            status_code=409,
            detail="El producto está referenciado por líneas de orden",
        )

    db.delete(p)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="El producto está referenciado por líneas de orden",
        ) from None
