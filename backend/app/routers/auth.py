"""Router de autenticación: login y logout."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services import auth as auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbDep = Annotated[Session, Depends(get_db)]


class LoginRequest(BaseModel):
    tenant_id: uuid.UUID | None = None
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: DbDep):
    """Autentica y devuelve JWT de 8 horas (un turno).

    Si el usuario pertenece a un solo tenant, tenant_id es opcional.
    """
    if body.tenant_id is None:
        user = auth_service.find_user_by_email(db, body.email)
        if user is None:
            raise HTTPException(status_code=401, detail="Credenciales incorrectas")
        tenant_id = user.tenant_id
    else:
        tenant_id = body.tenant_id

    try:
        token = auth_service.login(db, tenant_id, body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return LoginResponse(access_token=token)


class DemoLoginRequest(BaseModel):
    role: str


# Rate limit en memoria para demo-login (20 req/min/IP)
# En Fly 1 réplica basta; si se escala, migrar a Redis.
from collections import defaultdict
import time

_demo_login_attempts = defaultdict(list)
DEMO_LOGIN_WINDOW = 60  # segundos
DEMO_LOGIN_MAX = 20


def _check_demo_login_rate_limit(ip: str) -> None:
    now = time.time()
    recent = [t for t in _demo_login_attempts[ip] if now - t < DEMO_LOGIN_WINDOW]
    if len(recent) >= DEMO_LOGIN_MAX:
        raise HTTPException(status_code=429, detail="Demasiados intentos de demo-login. Espera un momento.")
    recent.append(now)
    _demo_login_attempts[ip] = recent


def _get_client_ip(authorization: str | None, x_forwarded_for: str | None) -> str:
    # En Fly.io la IP real viene en X-Forwarded-For
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    # Fallback: no bloqueamos si no hay IP
    return "unknown"


@router.post("/demo-login", response_model=LoginResponse)
def demo_login(
    body: DemoLoginRequest,
    db: DbDep,
    authorization: str | None = Header(None),
    x_forwarded_for: str | None = Header(None),
):
    """Demo login por rol — solo si DEMO_LOGIN_ENABLED=true.
    Devuelve el mismo JWT que el login normal, usando usuarios demo ya sembrados.
    """
    import os

    if os.getenv("DEMO_LOGIN_ENABLED") != "true":
        raise HTTPException(status_code=404, detail="Not found")

    # Rate limit por IP
    ip = _get_client_ip(authorization, x_forwarded_for)
    if ip != "unknown":
        _check_demo_login_rate_limit(ip)

    # Roles permitidos (lista cerrada, igual que en seed_demo)
    # Mapa: role (clave API) -> email prefix en seed
    ROLE_TO_EMAIL = {
        "operator": "operario",
        "supervisor": "supervisor",
        "materials": "materias",
        "admin": "admin",
    }
    allowed_roles = set(ROLE_TO_EMAIL.keys())
    if body.role not in allowed_roles:
        raise HTTPException(status_code=400, detail="Rol no permitido para demo")

    # Buscar tenant demo (slug "demo" o "demo-aceros")
    tenant = auth_service.buscar_tenant_demo(db)
    if tenant is None:
        raise HTTPException(status_code=400, detail="Tenant demo no configurado")

    # Buscar usuario demo por email/rol
    email_prefix = ROLE_TO_EMAIL[body.role]
    email = f"{email_prefix}@demo.local"
    user = auth_service.find_user_by_email_in_tenant(db, tenant.id, email)
    if user is None:
        raise HTTPException(status_code=400, detail="Usuario demo no encontrado para ese rol")

    # Verificar contraseña (siempre 'kavana' en seed)
    if not auth_service.verify_password("kavana", user.password_hash):
        raise HTTPException(status_code=400, detail="Credenciales demo inválidas")

    # Generar token igual que login normal
    token = auth_service.login(db, tenant.id, user.email, "kavana")
    return LoginResponse(access_token=token)


def _extraer_bearer(authorization: str | None) -> str | None:
    """Extrae el token de 'Authorization: Bearer <token>'."""
    if not authorization:
        return None
    partes = authorization.split()
    if len(partes) == 2 and partes[0].lower() == "bearer":
        return partes[1]
    return None


@router.post("/logout", status_code=204)
def logout(authorization: Annotated[str | None, Header()] = None, db: DbDep = None):
    """Revoca el token server-side (Bearer en header Authorization)."""
    token = _extraer_bearer(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="Token requerido")
    from app.services.medicion import MedicionPendiente

    try:
        auth_service.logout(db, token)
    except MedicionPendiente as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return None


@router.post("/close-shift")
def close_shift(authorization: Annotated[str | None, Header()] = None, db: DbDep = None):
    """Cierra el turno activo: total_hours y turno A/B/C (spec 02 3.11)."""
    token = _extraer_bearer(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="Token requerido")
    from app.services.medicion import MedicionPendiente

    try:
        return auth_service.close_shift(db, token)
    except MedicionPendiente as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
