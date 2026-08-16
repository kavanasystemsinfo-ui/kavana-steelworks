"""Seguridad HTTP: autenticación de usuarios por JWT (Fase 6, login + roles).

Cada router define su propia dependencia `get_current_user`/`require_roles`
usando su `DbDep` (patrón del proyecto: cada router trae su get_db para que
los tests puedan overriderarlo). Este módulo contiene solo la lógica pura:
extraer el Bearer, validar el JWT, comprobar revocación y cargar el User.
"""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.models import User
from app.services import auth as auth_service


def extraer_bearer(authorization: str | None) -> str | None:
    """Extrae el token de 'Authorization: Bearer <token>'."""
    if not authorization:
        return None
    partes = authorization.split()
    if len(partes) == 2 and partes[0].lower() == "bearer":
        return partes[1]
    return None


def autenticar(db: Session, authorization: str | None) -> User:
    """Valida el Bearer + JWT + revocación y devuelve el User (401 si falla)."""
    token = extraer_bearer(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="Token requerido")

    payload = auth_service.verify_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")

    if auth_service.is_revoked(db, token):
        raise HTTPException(status_code=401, detail="Token revocado")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Token inválido") from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user


def require_roles(get_current_user, *roles: str):
    """Factory de dependencia: exige que el usuario autenticado tenga un rol.

    Recibe la dependencia `get_current_user` del router (que usa su DbDep,
    overriderable en tests). Uso:

        current_user: Annotated[User, Depends(require_roles(get_current_user, "supervisor"))]
    """

    def _check(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail="Rol sin permisos para esta operación",
            )
        return user

    return _check
