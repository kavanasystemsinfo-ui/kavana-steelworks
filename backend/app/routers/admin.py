"""Router de Administración multi-tenant (spec 07, ADR-015).

Cada endpoint exige rol admin y opera SIEMPRE sobre el tenant del JWT
(nunca del path): un admin solo gestiona su propia empresa.

Endpoints:
- tenant GET/PUT (config de la empresa)
- users CRUD (soft delete: se desactiva, nunca se borra)
- sequences GET/PUT + GET next/{type} (peek sin consumir)
- workstations CRUD (soft delete)
- roles GET/PUT (solo custom editables; los del sistema son fijos)
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import autenticar, require_roles
from app.models import Tenant, TenantRole, User, Workstation, WorkstationGroup
from app.models.admin import PERMISOS_CATALOGO
from app.services import auth as auth_service
from app.services.sequences import peek_sequence

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

ROL_ADMIN = "admin"


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


AdminDep = Annotated[User, Depends(require_roles(get_current_user, ROL_ADMIN))]


# ── Schemas ─────────────────────────────────────────────────────────────────


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: str
    is_active: bool
    auth: dict
    theme: dict
    finances: dict
    sequences_config: dict


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool
    employee_number: str | None = None
    default_workstation_code: str | None = None
    last_login_at: datetime | None = None


class UserCreate(BaseModel):
    email: str
    name: str
    password: str = Field(min_length=4)
    role: str = "operator"
    employee_number: str | None = None
    default_workstation_code: str | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=4)
    employee_number: str | None = None
    default_workstation_code: str | None = None


class SequenceConfig(BaseModel):
    prefix: str
    padding: int = Field(ge=1, le=10)


class SequencesConfig(BaseModel):
    order: SequenceConfig
    lot: SequenceConfig


class SequenceNextOut(BaseModel):
    type: str
    next: str


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role_key: str
    name: str
    permissions: list
    is_system: bool


class RoleUpdate(BaseModel):
    name: str | None = None
    permissions: list[str] | None = None


class WorkstationGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    color: str


class WorkstationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    group_id: uuid.UUID | None = None
    code: str
    name: str
    color: str
    hourly_cost: float
    registration_method: str
    maintenance_interval_hours: int
    maintenance_pre_warning_hours: int
    last_maintenance_reset: datetime | None = None
    accumulated_hours: float
    is_active: bool


class WorkstationCreate(BaseModel):
    code: str
    name: str
    color: str = "#3498db"
    hourly_cost: float = 0
    registration_method: str = "quantity"
    group_id: uuid.UUID | None = None
    maintenance_interval_hours: int = 0
    maintenance_pre_warning_hours: int = 0


class WorkstationUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    hourly_cost: float | None = None
    registration_method: str | None = None
    group_id: uuid.UUID | None = None
    maintenance_interval_hours: int | None = None
    maintenance_pre_warning_hours: int | None = None
    is_active: bool | None = None


# ── Tenant ──────────────────────────────────────────────────────────────────


@router.get("/tenant", response_model=TenantOut)
def get_tenant(db: DbDep, current_user: AdminDep):
    """Config de la propia empresa (spec 07 §3)."""
    tenant = db.get(Tenant, current_user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    return tenant


@router.put("/tenant", response_model=TenantOut)
def update_tenant(body: dict, db: DbDep, current_user: AdminDep):
    """Actualiza name, slug, status, auth, theme, finances (spec 07 §3).

    Acepta un dict parcial: solo se tocan las claves presentes.
    """
    tenant = db.get(Tenant, current_user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    permitidos = {"name", "slug", "status", "auth", "theme", "finances"}
    no_permitidos = set(body) - permitidos
    if no_permitidos:
        raise HTTPException(
            status_code=400,
            detail=f"Campos no editables por esta vía: {sorted(no_permitidos)}",
        )

    if "slug" in body and body["slug"] != tenant.slug:
        nuevo_slug = body["slug"].strip().lower()
        if not nuevo_slug:
            raise HTTPException(status_code=400, detail="slug vacío")
        ocupado = db.scalar(select(Tenant).where(Tenant.slug == nuevo_slug))
        if ocupado is not None:
            raise HTTPException(status_code=409, detail="Ese slug ya lo usa otra empresa")
        tenant.slug = nuevo_slug  # type: ignore[assignment]
        body.pop("slug")

    for campo, valor in body.items():
        setattr(tenant, campo, valor)

    db.commit()
    db.refresh(tenant)
    return tenant


# ── Users ───────────────────────────────────────────────────────────────────


@router.get("/users", response_model=list[UserOut])
def list_users(db: DbDep, current_user: AdminDep):
    """Lista los usuarios del tenant (spec 07 §3)."""
    return list(
        db.scalars(select(User).where(User.tenant_id == current_user.tenant_id).order_by(User.name))
    )


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: DbDep, current_user: AdminDep):
    """Crea un usuario del tenant (spec 07 §3). Email único global."""
    if body.role not in ("operator", "supervisor", "materials", "admin"):
        raise HTTPException(status_code=400, detail=f"Rol inválido: {body.role}")

    existente = db.scalar(select(User).where(User.email == body.email))
    if existente is not None:
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese email")

    if body.default_workstation_code:
        _validar_workstation_code(db, current_user.tenant_id, body.default_workstation_code)

    user = User(
        tenant_id=current_user.tenant_id,
        email=body.email.strip().lower(),
        name=body.name.strip(),
        password_hash=auth_service.hash_password(body.password),
        role=body.role,
        is_active=True,
        employee_number=body.employee_number,
        default_workstation_code=body.default_workstation_code,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserUpdate, db: DbDep, current_user: AdminDep):
    """Edita un usuario: role, is_active, password, employee_number, puesto."""
    user = db.get(User, user_id)
    if user is None or user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if body.role is not None:
        if body.role not in ("operator", "supervisor", "materials", "admin"):
            raise HTTPException(status_code=400, detail=f"Rol inválido: {body.role}")
        user.role = body.role
    if body.name is not None:
        user.name = body.name.strip()
    if body.is_active is not None:
        if user.id == current_user.id and not body.is_active:
            raise HTTPException(status_code=400, detail="No puedes desactivar tu propio usuario")
        user.is_active = body.is_active
    if body.password is not None:
        user.password_hash = auth_service.hash_password(body.password)
    if body.employee_number is not None:
        user.employee_number = body.employee_number
    if body.default_workstation_code is not None:
        if body.default_workstation_code:
            _validar_workstation_code(db, current_user.tenant_id, body.default_workstation_code)
        user.default_workstation_code = body.default_workstation_code

    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", response_model=UserOut)
def deactivate_user(user_id: uuid.UUID, db: DbDep, current_user: AdminDep):
    """Desactiva un usuario (soft delete, spec 07 regla 3)."""
    user = db.get(User, user_id)
    if user is None or user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propio usuario")
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user


# ── Sequences ───────────────────────────────────────────────────────────────


def _sequences_defaults() -> dict:
    return {
        "order": {"prefix": "OP-{MM}{YY}-", "padding": 3},
        "lot": {"prefix": "LT-{DD}{MM}{YY}-", "padding": 3},
    }


@router.get("/sequences", response_model=SequencesConfig)
def get_sequences(db: DbDep, current_user: AdminDep):
    """Config actual de secuencias (prefix/padding por tipo)."""
    tenant = db.get(Tenant, current_user.tenant_id)
    cfg = (tenant.sequences_config or {}) if tenant else {}
    merged = {**_sequences_defaults(), **cfg}
    return SequencesConfig(
        order=SequenceConfig(**merged.get("order", {})),
        lot=SequenceConfig(**merged.get("lot", {})),
    )


@router.put("/sequences", response_model=SequencesConfig)
def update_sequences(body: SequencesConfig, db: DbDep, current_user: AdminDep):
    """Actualiza la config de secuencias del tenant (prefix/padding)."""
    tenant = db.get(Tenant, current_user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    tenant.sequences_config = {"order": body.order.model_dump(), "lot": body.lot.model_dump()}
    db.commit()
    db.refresh(tenant)
    return SequencesConfig(
        order=SequenceConfig(**body.order.model_dump()),
        lot=SequenceConfig(**body.lot.model_dump()),
    )


@router.get("/sequences/next/{sequence_type}", response_model=SequenceNextOut)
def next_sequence_endpoint(sequence_type: str, db: DbDep, current_user: AdminDep):
    """Siguiente número de secuencia SIN consumirlo (peek, spec 07 §3)."""
    if sequence_type not in ("order", "lot"):
        raise HTTPException(status_code=400, detail="Tipo de secuencia inválido (order | lot)")
    try:
        numero = peek_sequence(db, current_user.tenant_id, sequence_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SequenceNextOut(type=sequence_type, next=numero)


# ── Workstations ────────────────────────────────────────────────────────────


@router.get("/workstations", response_model=list[WorkstationOut])
def list_workstations(db: DbDep, current_user: AdminDep):
    """Lista los puestos del tenant junto con sus grupos."""
    return list(
        db.scalars(
            select(Workstation)
            .where(Workstation.tenant_id == current_user.tenant_id)
            .order_by(Workstation.code)
        )
    )


@router.get("/workstations/groups", response_model=list[WorkstationGroupOut])
def list_workstation_groups(db: DbDep, current_user: AdminDep):
    """Lista los grupos de puestos del tenant."""
    return list(
        db.scalars(
            select(WorkstationGroup)
            .where(WorkstationGroup.tenant_id == current_user.tenant_id)
            .order_by(WorkstationGroup.name)
        )
    )


@router.post("/workstations", response_model=WorkstationOut, status_code=201)
def create_workstation(body: WorkstationCreate, db: DbDep, current_user: AdminDep):
    """Crea un puesto de trabajo (spec 07 §3)."""
    if body.registration_method not in ("timer", "quantity", "manual"):
        raise HTTPException(
            status_code=400,
            detail="registration_method inválido (timer | quantity | manual)",
        )
    existente = db.scalar(
        select(Workstation).where(
            Workstation.tenant_id == current_user.tenant_id,
            Workstation.code == body.code,
        )
    )
    if existente is not None:
        raise HTTPException(status_code=409, detail="Ya existe un puesto con ese código")

    if body.group_id is not None:
        _validar_grupo(db, current_user.tenant_id, body.group_id)

    from decimal import Decimal

    ws = Workstation(
        tenant_id=current_user.tenant_id,
        group_id=body.group_id,
        code=body.code.strip().upper(),
        name=body.name.strip(),
        color=body.color,
        hourly_cost=Decimal(str(body.hourly_cost)),
        registration_method=body.registration_method,
        maintenance_interval_hours=body.maintenance_interval_hours,
        maintenance_pre_warning_hours=body.maintenance_pre_warning_hours,
        is_active=True,
    )
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


@router.patch("/workstations/{ws_id}", response_model=WorkstationOut)
def update_workstation(
    ws_id: uuid.UUID, body: WorkstationUpdate, db: DbDep, current_user: AdminDep
):
    """Edita un puesto (spec 07 §3)."""
    from decimal import Decimal

    ws = db.get(Workstation, ws_id)
    if ws is None or ws.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Puesto no encontrado")

    if body.name is not None:
        ws.name = body.name.strip()
    if body.color is not None:
        ws.color = body.color
    if body.hourly_cost is not None:
        ws.hourly_cost = Decimal(str(body.hourly_cost))
    if body.registration_method is not None:
        if body.registration_method not in ("timer", "quantity", "manual"):
            raise HTTPException(
                status_code=400,
                detail="registration_method inválido (timer | quantity | manual)",
            )
        ws.registration_method = body.registration_method
    if body.group_id is not None:
        _validar_grupo(db, current_user.tenant_id, body.group_id)
        ws.group_id = body.group_id
    if body.maintenance_interval_hours is not None:
        ws.maintenance_interval_hours = body.maintenance_interval_hours
    if body.maintenance_pre_warning_hours is not None:
        ws.maintenance_pre_warning_hours = body.maintenance_pre_warning_hours
    if body.is_active is not None:
        ws.is_active = body.is_active

    db.commit()
    db.refresh(ws)
    return ws


@router.delete("/workstations/{ws_id}", response_model=WorkstationOut)
def deactivate_workstation(ws_id: uuid.UUID, db: DbDep, current_user: AdminDep):
    """Desactiva un puesto (soft delete, spec 07 regla 6)."""
    ws = db.get(Workstation, ws_id)
    if ws is None or ws.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Puesto no encontrado")
    ws.is_active = False
    db.commit()
    db.refresh(ws)
    return ws


# ── Roles ───────────────────────────────────────────────────────────────────


@router.get("/roles", response_model=list[RoleOut])
def list_roles(db: DbDep, current_user: AdminDep):
    """Lista los roles del tenant con sus permisos (spec 07 §3)."""
    return list(
        db.scalars(
            select(TenantRole)
            .where(TenantRole.tenant_id == current_user.tenant_id)
            .order_by(TenantRole.role_key)
        )
    )


@router.put("/roles/{role_key}", response_model=RoleOut)
def update_role(role_key: str, body: RoleUpdate, db: DbDep, current_user: AdminDep):
    """Edita un rol CUSTOM (spec 07 regla 4: los del sistema son fijos)."""
    rol = db.scalar(
        select(TenantRole).where(
            TenantRole.tenant_id == current_user.tenant_id,
            TenantRole.role_key == role_key,
        )
    )
    if rol is None:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    if rol.is_system:
        raise HTTPException(
            status_code=400,
            detail="Los roles del sistema (operator/materials/supervisor/admin) "
            "no se pueden editar",
        )

    if body.name is not None:
        rol.name = body.name.strip()
    if body.permissions is not None:
        invalidos = [p for p in body.permissions if p not in PERMISOS_CATALOGO]
        if invalidos:
            raise HTTPException(status_code=400, detail=f"Permisos desconocidos: {invalidos}")
        rol.permissions = body.permissions

    db.commit()
    db.refresh(rol)
    return rol


# ── Helpers ─────────────────────────────────────────────────────────────────


def _validar_workstation_code(db: Session, tenant_id: uuid.UUID, code: str) -> None:
    ws = db.scalar(
        select(Workstation).where(Workstation.tenant_id == tenant_id, Workstation.code == code)
    )
    if ws is None:
        raise HTTPException(
            status_code=400,
            detail=f"El puesto '{code}' no existe en este tenant (regla 7)",
        )


def _validar_grupo(db: Session, tenant_id: uuid.UUID, group_id: uuid.UUID) -> None:
    grupo = db.get(WorkstationGroup, group_id)
    if grupo is None or grupo.tenant_id != tenant_id:
        raise HTTPException(status_code=400, detail="Grupo de puestos no encontrado")
