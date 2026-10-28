"""Paradas de máquina con un toque (fase 3 del rediseño del panel de operario).

El operario toca el motivo (avería, ajustes, cambio de modelo, limpieza,
mantenimiento u otros), el tiempo cuenta solo y al volver a producir la
parada se cierra. Un operario tiene como mucho una parada abierta.

`paradas_en` junta en un solo formato las paradas y las incidencias de una
ventana (recortadas a ella), para que el panel de mando (Turno y Planta) y el
informe de turno las sumen igual.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Incidencia, Parada
from app.models.parada import MOTIVOS_PARADA

ESTADOS_INCIDENCIA_ABIERTA = ("abierta", "en_revision")
TIPOS_INCIDENCIA = {
    "maquina": "avería",
    "material": "falta de material",
    "seguridad": "seguridad",
    "otro": "incidencia",
}


def _utc(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


def parada_dict(p: Parada) -> dict:
    return {
        "id": str(p.id),
        "puesto": p.puesto,
        "motivo": p.motivo,
        "motivo_texto": MOTIVOS_PARADA[p.motivo],
        "nota": p.nota,
        "inicio": _utc(p.inicio).isoformat(),
        "fin": _utc(p.fin).isoformat() if p.fin else None,
    }


def parada_abierta(db: Session, user_id) -> Parada | None:
    return db.scalar(
        select(Parada).where(Parada.operario_id == user_id, Parada.fin.is_(None))
    )


def iniciar_parada(
    db: Session, tenant_id, user_id, *, puesto: str, motivo: str, order_id=None, line_id=None
) -> Parada:
    if motivo not in MOTIVOS_PARADA:
        raise ValueError(f"Motivo de parada no válido: {motivo}")
    if parada_abierta(db, user_id) is not None:
        raise ValueError("Ya tienes una parada en curso: vuelve a producir antes de abrir otra")
    p = Parada(
        tenant_id=tenant_id,
        puesto=puesto,
        operario_id=user_id,
        order_id=order_id,
        line_id=line_id,
        motivo=motivo,
        inicio=datetime.now(UTC),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _propia(db: Session, user_id, parada_id: uuid.UUID) -> Parada:
    p = db.get(Parada, parada_id)
    if p is None or p.operario_id != user_id:
        raise LookupError("Parada no encontrada")
    return p


def terminar_parada(db: Session, user_id, parada_id: uuid.UUID, nota: str | None = None) -> Parada:
    p = _propia(db, user_id, parada_id)
    if p.fin is None:
        p.fin = datetime.now(UTC)
    if nota:
        p.nota = nota
    db.commit()
    db.refresh(p)
    return p


def cambiar_parada(
    db: Session,
    user_id,
    parada_id: uuid.UUID,
    *,
    motivo: str | None = None,
    nota: str | None = None,
) -> Parada:
    p = _propia(db, user_id, parada_id)
    if motivo is not None:
        if motivo not in MOTIVOS_PARADA:
            raise ValueError(f"Motivo de parada no válido: {motivo}")
        p.motivo = motivo
    if nota is not None:
        p.nota = nota
    db.commit()
    db.refresh(p)
    return p


def cerrar_paradas_de(db: Session, user_id) -> None:
    """Al cerrar la jornada o la sesión, una parada abierta termina ahí."""
    p = parada_abierta(db, user_id)
    if p is not None:
        p.fin = datetime.now(UTC)
        db.commit()


def paradas_abiertas_por_puesto(db: Session, tenant_id) -> dict[str, Parada]:
    return {
        p.puesto: p
        for p in db.scalars(
            select(Parada)
            .where(Parada.tenant_id == tenant_id, Parada.fin.is_(None))
            .order_by(Parada.inicio.asc())
        )
    }


def paradas_en(db: Session, tenant_id, desde: datetime, hasta: datetime) -> list[dict]:
    """Paradas e incidencias de la ventana, recortadas a ella.

    Incidencia abierta: desde su creación (o el inicio de la ventana) hasta
    `hasta`; cerrada: su tiempo de parada declarado si se creó en la ventana.
    Parada: su tramo [inicio, fin o `hasta`] recortado a la ventana.
    """
    resultado = []
    for inc in db.scalars(
        select(Incidencia).where(Incidencia.tenant_id == tenant_id, Incidencia.created_at < hasta)
    ):
        creada = _utc(inc.created_at)
        abierta = inc.estado in ESTADOS_INCIDENCIA_ABIERTA
        if abierta:
            minutos = (hasta - max(creada, desde)).total_seconds() / 60
        elif creada >= desde:
            minutos = float(inc.tiempo_parada_min or 0)
        else:
            continue
        if minutos > 0:
            resultado.append(
                {
                    "puesto": inc.puesto,
                    "tipo": inc.tipo,
                    "motivo": TIPOS_INCIDENCIA.get(inc.tipo, "incidencia"),
                    "descripcion": inc.descripcion,
                    "minutos": minutos,
                    "abierta": abierta,
                }
            )
    for p in db.scalars(
        select(Parada).where(Parada.tenant_id == tenant_id, Parada.inicio < hasta)
    ):
        fin = _utc(p.fin) if p.fin else hasta
        minutos = (min(fin, hasta) - max(_utc(p.inicio), desde)).total_seconds() / 60
        if minutos > 0:
            resultado.append(
                {
                    "puesto": p.puesto,
                    "tipo": f"parada_{p.motivo}",
                    "motivo": MOTIVOS_PARADA[p.motivo],
                    "descripcion": p.nota or "",
                    "minutos": minutos,
                    "abierta": p.fin is None,
                }
            )
    return resultado
