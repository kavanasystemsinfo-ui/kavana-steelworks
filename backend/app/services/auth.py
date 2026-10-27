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
from app.models import RevokedToken, Tenant, User, UserShift
from app.services.shifts import horas_de_turno, turno_desde

settings = get_settings()

SLUGS_DEMO = ("demo", "demo-aceros")


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
    tenant = db.get(Tenant, tenant_id)
    payload = {
        "sub": str(user.id),
        "tenant_id": str(tenant_id),
        "role": user.role,
        # La interfaz marca "DATOS DE DEMO" para no presentar datos ficticios
        # como reales (slugs de buscar_tenant_demo en seed_demo)
        "demo": tenant is not None and tenant.slug in SLUGS_DEMO,
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
        turno_activo.total_hours = horas_de_turno(turno_activo.login_time, ahora)
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
    """Revoca el token en la lista negra server-side (idempotente)."""
    payload = verify_token(token)
    if payload is None:
        return
    if is_revoked(db, token):
        return  # ya revocado: evita IntegrityError por unique(token)
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
        turno.logout_time = datetime.now(UTC)
        turno.status = "completed"
        turno.total_hours = horas_de_turno(turno.login_time, turno.logout_time)
    db.commit()


def close_shift(db: Session, token: str) -> dict:
    """Cierra el turno activo con total_hours y turno A/B/C (spec 02 3.11)."""
    payload = verify_token(token)
    if payload is None or is_revoked(db, token):
        raise ValueError("Token inválido")
    user_id = uuid.UUID(payload["sub"])
    turno = db.scalar(
        select(UserShift).where(
            UserShift.operator_id == user_id,
            UserShift.status == "active",
        )
    )
    if turno is None:
        raise LookupError("No hay turno activo para cerrar")
    ahora = datetime.now(UTC)
    turno.logout_time = ahora
    turno.status = "completed"
    turno.total_hours = horas_de_turno(turno.login_time, ahora)
    db.commit()
    db.refresh(turno)
    return {
        "success": True,
        "status": turno.status,
        "total_hours": float(turno.total_hours),
        "turno": turno_desde(turno.login_time),
        "logout_time": turno.logout_time.isoformat(),
    }
