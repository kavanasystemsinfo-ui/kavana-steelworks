"""Router de Supervisor: OEE y KPIs del turno (spec 03)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import autenticar, require_roles
from app.models import User

router = APIRouter(prefix="/api/v1/supervisor", tags=["supervisor"])


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


@router.get("/oee")
def get_oee(
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """OEE global del turno actual (A × P × Q, clamp a 100)."""
    from app.services.oee_kpis import calcular_oee

    try:
        return calcular_oee(db, current_user.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/kpis")
def get_kpis(
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """KPIs financieros: coste real vs estimado, varianzas, merma."""
    from app.services.oee_kpis import calcular_kpis

    try:
        return calcular_kpis(db, current_user.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
