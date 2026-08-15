"""Servicio de incidencias de planta (spec 04 §3.3).

Portado de IncidenciaController.js del legacy:
- una incidencia nace SIEMPRE en 'abierta' con historial inicial
- si hay una orden activa en la línea (workstation_id), se asocia
- update: estado -> push al historial; resolución financiera conserva los
  campos previos si el request no los trae (contrato del objeto embebido)
- responsable_id = quien resuelve; publish de eventos por tenant (broker)
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.incidencia import ESTADOS_INCIDENCIA, Incidencia, IncidenciaHistorial
from app.models.order import Order, OrderLine
from app.services.demo_context import resolver_operario, resolver_tenant
from app.services.events import broker
from app.services.incidencia_uploads import UploadError

LIMITE_INCIDENCIAS = 50  # spec 04: límite duro de listado


def _resolver_orden_activa(db: Session, tenant_id, linea_id) -> Order | None:
    """Orden activa de la línea (la más reciente), como el legacy."""
    return db.scalar(
        select(Order)
        .join(OrderLine, OrderLine.order_id == Order.id)
        .where(
            Order.tenant_id == tenant_id,
            Order.estado == "active",
            OrderLine.workstation_id == linea_id,
        )
        .order_by(Order.created_at.desc())
    )


def crear_incidencia(
    db: Session,
    *,
    tenant_id: uuid.UUID | None,
    operario_id: uuid.UUID | None,
    linea_id: str,
    descripcion: str,
    tipo: str = "otro",
    foto: str | None = None,
    photo_session_id: str | None = None,
) -> Incidencia:
    """Crea una incidencia en estado 'abierta' con su historial inicial.

    Si `photo_session_id` apunta a una sesión QR con foto 'uploaded', la
    foto se copia a la incidencia y la sesión pasa a 'used' (finalize).
    """
    from app.services.incidencia_uploads import finalizar as finalizar_foto

    if tenant_id is None:
        tenant = resolver_tenant(db)
        if tenant is None:
            raise ValueError("No hay tenant configurado")
        tenant_id = tenant.id
    if operario_id is None:
        operario_id = resolver_operario(db, tenant_id)

    if tipo not in ("maquina", "material", "seguridad", "otro"):
        raise ValueError("Tipo de incidencia no válido")

    orden = _resolver_orden_activa(db, tenant_id, linea_id)
    incidencia = Incidencia(
        tenant_id=tenant_id,
        order_id=orden.id if orden is not None else None,
        linea_id=linea_id,
        puesto=linea_id or "",
        operario_id=operario_id,
        descripcion=descripcion,
        tipo=tipo,
        foto=foto,
        estado="abierta",
    )
    db.add(incidencia)
    db.flush()
    db.add(
        IncidenciaHistorial(
            incidencia_id=incidencia.id,
            estado="abierta",
            usuario_id=operario_id,
            comentario="Incidencia creada",
        )
    )

    broker.publish(
        tenant_id=tenant_id,
        tipo="nueva_incidencia",
        data={"id": str(incidencia.id), "estado": "abierta", "tipo": tipo},
    )

    db.commit()
    db.refresh(incidencia)

    # Adjuntar la foto de la sesión QR si llegó (no bloquea: sin foto, la
    # incidencia se crea igual; la sesión pendiente caduca sola).
    if photo_session_id:
        try:
            finalizar_foto(
                db,
                tenant_id=tenant_id,
                session_id=uuid.UUID(photo_session_id),
                incidencia_id=incidencia.id,
            )
        except (ValueError, TypeError):
            db.rollback()
            db.refresh(incidencia)

    return incidencia


def listar_incidencias(
    db: Session, tenant_id: uuid.UUID, limit: int = LIMITE_INCIDENCIAS
) -> list[Incidencia]:
    """Incidencias del tenant, createdAt desc, límite duro (spec 04)."""
    return (
        db.query(Incidencia)
        .filter(Incidencia.tenant_id == tenant_id)
        .order_by(Incidencia.created_at.desc(), Incidencia.id.desc())
        .limit(min(limit, LIMITE_INCIDENCIAS))
        .all()
    )


def actualizar_incidencia(
    db: Session,
    *,
    incidencia_id: uuid.UUID,
    tenant_id: uuid.UUID,
    usuario_id: uuid.UUID,
    estado: str | None = None,
    comentario: str | None = None,
    resolucion_tipo: str | None = None,
    resolucion_descripcion: str | None = None,
    tiempo_parada: Decimal | None = None,
    coste: Decimal | None = None,
) -> Incidencia:
    """Cambia estado y/o resolución; conserva los campos previos no enviados."""
    incidencia = db.query(Incidencia).filter(
        Incidencia.id == incidencia_id,
        Incidencia.tenant_id == tenant_id,
    ).first()
    if incidencia is None:
        raise ValueError("Incidencia no encontrada")

    if estado is not None:
        if estado not in ESTADOS_INCIDENCIA:
            raise ValueError("Estado de incidencia no válido")
        incidencia.estado = estado
        db.add(
            IncidenciaHistorial(
                incidencia_id=incidencia.id,
                estado=estado,
                usuario_id=usuario_id,
                comentario=comentario or f"Estado cambiado a {estado}",
            )
        )

    hay_resolucion = any(
        v is not None
        for v in (resolucion_tipo, resolucion_descripcion, tiempo_parada, coste)
    )
    if hay_resolucion:
        if resolucion_tipo is not None:
            incidencia.resolucion_tipo = resolucion_tipo
        if resolucion_descripcion is not None:
            incidencia.resolucion_descripcion = resolucion_descripcion
        if tiempo_parada is not None:
            incidencia.tiempo_parada_min = tiempo_parada
        if coste is not None:
            incidencia.coste = coste
        incidencia.responsable_id = usuario_id

    broker.publish(
        tenant_id=tenant_id,
        tipo="incidencia_actualizada",
        data={"id": str(incidencia.id), "estado": incidencia.estado},
    )

    db.commit()
    db.refresh(incidencia)
    return incidencia


def subir_foto(
    db: Session, *, incidencia_id: uuid.UUID, tenant_id: uuid.UUID, buf: bytes
) -> Incidencia:
    """Valida por magic bytes y guarda la foto como BYTEA (patrón manufacturing).

    La foto es la evidencia de la incidencia y vive en PostgreSQL; sin
    servicios externos (el legacy usaba Cloudinary, no portado).
    """
    from app.services.photo_validator import validar_foto

    incidencia = (
        db.query(Incidencia)
        .filter(Incidencia.id == incidencia_id, Incidencia.tenant_id == tenant_id)
        .first()
    )
    if incidencia is None:
        raise UploadError("Incidencia no encontrada", 404)

    validacion = validar_foto(buf)
    if not validacion["ok"]:
        raise UploadError(validacion["reason"], 400)

    incidencia.foto_data = buf
    incidencia.foto_mime = validacion["mime"]
    incidencia.foto_size = validacion["size"]
    db.commit()
    db.refresh(incidencia)
    return incidencia
