"""Router de incidencias de planta (spec 04 §3.3): alta, listado y resolución.

Alta desde el operario (puesto + descripción + tipo), listado para el
Supervisor y actualización con cierre financiero (tiempo de parada en
minutos y coste en euros, conservando campos previos no enviados).
"""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import SessionLocal

router = APIRouter(prefix="/api/v1/incidencias", tags=["incidencias"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbDep = Annotated[Session, Depends(get_db)]


class IncidenciaIn(BaseModel):
    linea_id: str
    descripcion: str
    tipo: str = "otro"
    foto: str | None = None


class IncidenciaUpdate(BaseModel):
    estado: str | None = None
    comentario: str | None = None
    resolucion_tipo: str | None = None
    resolucion_descripcion: str | None = None
    tiempo_parada_min: Decimal | None = None
    coste: Decimal | None = None


@router.post("", status_code=201)
def crear_incidencia(body: IncidenciaIn, db: DbDep):
    """Reporta una incidencia desde el puesto (operario)."""
    from app.services.incidencias import crear_incidencia as service

    try:
        incidencia = service(
            db,
            tenant_id=None,  # TODO: tenant desde el token JWT
            operario_id=None,  # TODO: user desde el token JWT (se resuelve)
            linea_id=body.linea_id,
            descripcion=body.descripcion,
            tipo=body.tipo,
            foto=body.foto,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "msg": "Incidencia registrada", "incidencia": _out(incidencia)}


@router.get("")
def listar_incidencias(db: DbDep, limit: int = 50):
    """Incidencias del tenant para el Supervisor (desc, límite 50)."""
    from app.models import Tenant
    from app.services.incidencias import listar_incidencias as service

    tenant = db.query(Tenant).order_by(Tenant.created_at).first()
    if tenant is None:
        return {"success": True, "incidencias": []}
    incidencias = service(db, tenant.id, limit=limit)
    return {"success": True, "incidencias": [_out(i) for i in incidencias]}


@router.patch("/{incidencia_id}")
def actualizar_incidencia(incidencia_id: uuid.UUID, body: IncidenciaUpdate, db: DbDep):
    """Cambia estado y/o resolución financiera (Supervisor)."""
    from app.services.demo_context import resolver_operario, resolver_tenant
    from app.services.incidencias import actualizar_incidencia as service

    tenant = resolver_tenant(db)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")
    operario_id = resolver_operario(db, tenant.id)

    try:
        incidencia = service(
            db,
            incidencia_id=incidencia_id,
            tenant_id=tenant.id,
            usuario_id=operario_id,
            estado=body.estado,
            comentario=body.comentario,
            resolucion_tipo=body.resolucion_tipo,
            resolucion_descripcion=body.resolucion_descripcion,
            tiempo_parada=body.tiempo_parada_min,
            coste=body.coste,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "msg": "Incidencia actualizada", "incidencia": _out(incidencia)}


def _out(i) -> dict:
    """Serialización explícita (mismo patrón que trace.py)."""
    return {
        "id": i.id,
        "order_id": i.order_id,
        "linea_id": i.linea_id,
        "puesto": i.puesto,
        "descripcion": i.descripcion,
        "tipo": i.tipo,
        "foto": i.foto,
        "estado": i.estado,
        "resolucion_tipo": i.resolucion_tipo,
        "resolucion_descripcion": i.resolucion_descripcion,
        "tiempo_parada_min": i.tiempo_parada_min,
        "coste": i.coste,
        "created_at": i.created_at,
        "operario": (
            {"id": i.operario.id, "name": i.operario.name}
            if i.operario is not None
            else None
        ),
        "responsable": (
            {"id": i.responsable.id, "name": i.responsable.name}
            if i.responsable is not None
            else None
        ),
        "historial": [
            {
                "estado": h.estado,
                "timestamp": h.timestamp,
                "comentario": h.comentario,
                "usuario": h.usuario.name if h.usuario is not None else None,
            }
            for h in i.historial
        ],
    }
