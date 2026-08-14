"""Servicio de autenticación (spec 05, sección 2.4/2.5).

Contrato del v2:
- JWT de 8 horas = un turno estándar de fábrica.
- Logout con revocación server-side (lista negra RevokedToken).
- Un operario tiene un solo turno activo a la vez (UserShift).
- Passwords con bcrypt (passlib).
"""

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import RevokedToken, User, UserShift

settings = get_settings()


def hash_password(password: str) -> str:
    """Hash bcrypt. bcrypt limita a 72 bytes: trunca antes de hashear."""
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], password_hash.encode())
    except ValueError:
        return False


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def login(db: Session, tenant_id: uuid.UUID, email: str, password: str) -> str:
    """Autentica y devuelve un JWT de 8 horas. Crea el turno activo."""
    user = db.scalar(select(User).where(User.tenant_id == tenant_id, User.email == email))
    if user is None or not verify_password(password, user.password_hash):
        raise ValueError("Credenciales incorrectas")
    if not user.is_active:
        raise ValueError("Usuario inactivo")

    ahora = datetime.now(UTC)
    exp = ahora + timedelta(hours=settings.jwt_expire_hours)
    payload = {
        "sub": str(user.id),
        "tenant_id": str(tenant_id),
        "role": user.role,
        "exp": exp,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    # Turno: un solo activo por operario (cierra el anterior si existía)
    turno_activo = db.scalar(
        select(UserShift).where(UserShift.operator_id == user.id, UserShift.status == "active")
    )
    if turno_activo is not None:
        turno_activo.status = "completed"
        turno_activo.logout_time = ahora
    db.add(
        UserShift(
            tenant_id=tenant_id,
            operator_id=user.id,
            login_time=ahora,
            status="active",
        )
    )
    db.commit()
    return token


def verify_token(token: str) -> dict | None:
    """Valida el token. None si es inválido, expirado o revocado."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    return payload


def is_revoked(db: Session, token: str) -> bool:
    return db.scalar(select(RevokedToken).where(RevokedToken.token == token)) is not None


def logout(db: Session, token: str) -> None:
    """Revoca el token en la lista negra server-side."""
    payload = verify_token(token)
    if payload is None:
        return
    exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
    db.add(
        RevokedToken(
            token=token,
            expires_at=exp,
            revoked_at=datetime.now(UTC),
        )
    )
    # Cierra el turno activo del usuario
    user_id = uuid.UUID(payload["sub"])
    turno = db.scalar(
        select(UserShift).where(UserShift.operator_id == user_id, UserShift.status == "active")
    )
    if turno is not None:
        turno.status = "completed"
        turno.logout_time = datetime.now(UTC)
    db.commit()
