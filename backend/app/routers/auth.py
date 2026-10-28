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
