"""Router de Supervisor: OEE y KPIs del turno (spec 03)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import SessionLocal

router = APIRouter(prefix="/api/v1/supervisor", tags=["supervisor"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbDep = Annotated[Session, Depends(get_db)]


@router.get("/oee")
def get_oee(db: DbDep, tenant_id: uuid.UUID | None = None):
    """OEE global del turno actual (A × P × Q, clamp a 100)."""
    from app.services.oee_kpis import calcular_oee

    try:
        # TODO(Fase 4): tenant desde el token JWT; demo usa el primer tenant
        if tenant_id is None:
            from app.models import Tenant

            tenant = db.query(Tenant).first()
            if tenant is None:
                return {
                    "availability": 0,
                    "performance": 0,
                    "quality": 100,
                    "oee": 0,
                    "raw": {},
                }
            tenant_id = tenant.id
        return calcular_oee(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/kpis")
def get_kpis(db: DbDep, tenant_id: uuid.UUID | None = None):
    """KPIs financieros: coste real vs estimado, varianzas, merma."""
    from app.services.oee_kpis import calcular_kpis

    try:
        if tenant_id is None:
            from app.models import Tenant

            tenant = db.query(Tenant).first()
            if tenant is None:
                return {
                    "orders_total": 0,
                    "orders_active": 0,
                    "orders_completed": 0,
                    "estimated_cost": 0,
                    "real_cost": 0,
                    "cost_variance": 0,
                    "cost_efficiency": 0,
                    "material_variance": 0,
                    "material_efficiency": 0,
                    "scrap_rate": 0,
                }
            tenant_id = tenant.id
        return calcular_kpis(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
