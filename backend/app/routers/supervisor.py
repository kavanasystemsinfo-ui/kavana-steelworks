"""Router de Supervisor: OEE y KPIs del turno (spec 03)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response
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


@router.get("/costes-ordenes")
def get_costes_ordenes(
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Coste real (material + mano de obra) vs estimado de cada orden."""
    from app.services.costes import costes_por_orden

    return costes_por_orden(db, current_user.tenant_id)


@router.get("/puestos")
def get_puestos(
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Monitor de puestos: orden, bobina, progreso, última actividad, incidencias."""
    from app.services.puestos import estado_puestos

    return estado_puestos(db, current_user.tenant_id)


@router.get("/alertas")
def get_alertas(
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Stock bajo mínimos e incidencias abiertas (misma regla que su detalle)."""
    from app.services.alertas import alertas

    return alertas(db, current_user.tenant_id)


@router.get("/informe-turno")
def get_informe_turno(
    fecha: date,
    turno: str,
    db: DbDep,
    formato: str = "json",
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Informe del turno A/B/C de una fecha (JSON o CSV para Excel)."""
    from app.services.informe_turno import informe_csv, informe_turno

    try:
        informe = informe_turno(db, current_user.tenant_id, fecha, turno.upper())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if formato == "csv":
        nombre = f"informe-turno-{informe['fecha']}-{informe['turno']}.csv"
        return Response(
            content="﻿" + informe_csv(informe),  # BOM: Excel detecta UTF-8
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
        )
    return informe
