"""Router de autenticación: login y logout."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
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


@router.post("/logout", status_code=204)
def logout(token: str, db: DbDep):
    """Revoca el token server-side."""
    auth_service.logout(db, token)
    return None
