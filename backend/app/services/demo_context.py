"""Helpers de contexto de la demo: tenant y operario por defecto.

La demo pública no tiene auth (JWT por roles pendiente Fase 5); los servicios
resuelven el primer tenant y el operario de la demo, igual que los routers de
supervisor. Extraído de quality.py para reutilizarlo en incidencias sin
duplicar la lógica (patrón _system_user de receiving.py).
"""

import uuid

from sqlalchemy.orm import Session


def resolver_tenant(db: Session):
    """Primer tenant (patrón demo)."""
    from app.models import Tenant

    return db.query(Tenant).order_by(Tenant.created_at).first()


def resolver_operario(db: Session, tenant_id) -> uuid.UUID:
    """Operario de la demo (primer user del tenant); fallback al usuario system."""
    from app.models import User
    from app.services.receiving import _system_user

    operario = (
        db.query(User)
        .filter(User.tenant_id == tenant_id, User.role == "operator")
        .order_by(User.created_at)
        .first()
    )
    if operario is not None:
        return operario.id
    return _system_user(db, tenant_id)
