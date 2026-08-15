"""Servicio de trazabilidad ISO 9001 (spec 04 §3.1, portado de TraceabilityService.js).

Contrato del legacy:
- log_event crea un ProductionLog inmutable y es BEST-EFFORT: si el guardado
  falla, registra el error y lo traga (DLQ en sistemas reales). La
  trazabilidad nunca debe romper el flujo de planta.
- get_order_trace devuelve la serie temporal completa de una orden (asc).
- get_last_active_session_start: start/resume sin pause/finish/stopped
  posterior = sesión activa.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import ProductionLog
from app.models.traceability import ACCIONES_TRACE

logger = logging.getLogger(__name__)


def _acciones_validas() -> set[str]:
    return set(ACCIONES_TRACE)


def log_event(
    db: Session,
    *,
    tenant_id,
    order_id,
    line_id,
    operator_id,
    action: str,
    quantity: float | int = 0,
    timestamp: datetime | None = None,
    metadata: dict | None = None,
    shift: str | None = None,
) -> ProductionLog | None:
    """Registra un evento de producción inmutable (best-effort).

    Nunca lanza: si la persistencia falla, se loguea el error y se devuelve
    None (el flujo de planta continúa).
    """
    if action not in _acciones_validas():
        raise ValueError(
            f"Acción de trazabilidad inválida: {action!r}. Válidas: {sorted(_acciones_validas())}"
        )

    log = ProductionLog(
        tenant_id=tenant_id,
        order_id=order_id,
        line_id=line_id,
        operator_id=operator_id,
        timestamp=timestamp or datetime.now(UTC),
        action=action,
        quantity=quantity,
        metadata_=metadata or {},
        shift=shift,
    )
    try:
        db.add(log)
        db.commit()
        db.refresh(log)
        return log
    except Exception:
        # Best-effort (spec: DLQ en un sistema real); no romper el flujo
        logger.exception("❌ Critical Error in Traceability: fallo al guardar log %s", action)
        db.rollback()
        return None


def get_order_trace(db: Session, tenant_id, order_id) -> list[ProductionLog]:
    """Serie temporal completa de eventos de una orden (timestamp asc)."""
    return list(
        db.scalars(
            select(ProductionLog)
            .options(joinedload(ProductionLog.operator))
            .where(ProductionLog.tenant_id == tenant_id, ProductionLog.order_id == order_id)
            .order_by(ProductionLog.timestamp.asc())
        )
    )


def get_last_active_session_start(
    db: Session, tenant_id, order_id, line_id, operator_id
) -> ProductionLog | None:
    """Último start/resume sin stop posterior (sesión lógica activa).

    Devuelve None si la sesión ya cerró (hay pause/finish/stopped posterior).
    """
    last_start = db.scalars(
        select(ProductionLog)
        .where(
            ProductionLog.tenant_id == tenant_id,
            ProductionLog.order_id == order_id,
            ProductionLog.line_id == line_id,
            ProductionLog.operator_id == operator_id,
            ProductionLog.action.in_(["start", "resume"]),
        )
        .order_by(ProductionLog.timestamp.desc())
        .limit(1)
    ).first()

    if last_start is None:
        return None

    later_stop = db.scalars(
        select(ProductionLog)
        .where(
            ProductionLog.tenant_id == tenant_id,
            ProductionLog.order_id == order_id,
            ProductionLog.line_id == line_id,
            ProductionLog.operator_id == operator_id,
            ProductionLog.action.in_(["pause", "finish", "stopped"]),
            ProductionLog.timestamp > last_start.timestamp,
        )
        .limit(1)
    ).first()

    if later_stop is not None:
        return None
    return last_start
