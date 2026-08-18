"""Servicio de secuencias automáticas (spec 07 §2.3).

Portado de Sequence.js del v2 con una mejora de concurrencia: el incremento
usa SELECT ... FOR UPDATE (el $inc de MongoDB no garantiza que dos peticiones
no lean el mismo número).

El prefix se resuelve con la fecha: {MM} mes, {YY} año, {DD} día. El contador
vivo vive en la tabla `sequences` (una fila por tenant+tipo+prefix); la
config (prefix/padding por tipo) viene de `tenants.sequences_config`.
"""

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Sequence, Tenant

_PLACEHOLDER = re.compile(r"\{([A-Za-z]+)\}")


def _resolver_prefix(template: str, ahora: datetime) -> str:
    """Sustituye {MM} {YY} {DD} por la fecha actual. Tokens desconocidos se
    dejan tal cual (p.ej. prefijos estáticos 'OP-FIJO-')."""

    def _token(m: re.Match) -> str:
        key = m.group(1)
        if key == "MM":
            return f"{ahora.month:02d}"
        if key == "YY":
            return f"{ahora.year % 100:02d}"
        if key == "DD":
            return f"{ahora.day:02d}"
        return m.group(0)

    return _PLACEHOLDER.sub(_token, template)


def _config(db: Session, tenant_id: uuid.UUID, tipo: str) -> tuple[str, int]:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ValueError("Tenant no encontrado")
    cfg = (tenant.sequences_config or {}).get(tipo) or {}
    prefix = cfg.get("prefix") or {"order": "OP-{MM}{YY}-", "lot": "LT-{DD}{MM}{YY}-"}[tipo]
    padding = int(cfg.get("padding") or 3)
    return prefix, padding


def next_sequence(db: Session, tenant_id: uuid.UUID, tipo: str) -> str:
    """Devuelve el siguiente número de secuencia y lo consume.

    Atómico en PostgreSQL (SELECT ... FOR UPDATE); en SQLite (tests) la fila
    se bloquea por el unique constraint. Nunca repite número.
    """
    if tipo not in ("order", "lot"):
        raise ValueError(f"Tipo de secuencia inválido: {tipo}")

    ahora = datetime.now(UTC)
    template, padding = _config(db, tenant_id, tipo)
    prefix = _resolver_prefix(template, ahora)

    # Bloquea la fila si existe (SELECT FOR UPDATE en PG: dos peticiones
    # concurrentes serializan aquí). Si no existe, la crea dentro de un
    # savepoint: si otro hilo la creó primero, el IntegrityError del unique
    # constraint revierte solo el savepoint y el SELECT posterior la ve.
    fila = db.scalar(
        select(Sequence)
        .where(
            Sequence.tenant_id == tenant_id,
            Sequence.sequence_type == tipo,
            Sequence.prefix == prefix,
        )
        .with_for_update()
    )
    if fila is None:
        try:
            with db.begin_nested():
                fila = Sequence(
                    tenant_id=tenant_id,
                    sequence_type=tipo,
                    prefix=prefix,
                    padding=padding,
                    next_number=1,
                )
                db.add(fila)
                db.flush()
        except IntegrityError:
            # Otro hilo insertó la fila: recargar con FOR UPDATE (espera su commit)
            fila = db.scalar(
                select(Sequence)
                .where(
                    Sequence.tenant_id == tenant_id,
                    Sequence.sequence_type == tipo,
                    Sequence.prefix == prefix,
                )
                .with_for_update()
            )
            assert fila is not None, "Fila de secuencia desapareció tras el conflicto"

    numero = fila.next_number
    fila.next_number = numero + 1
    fila.padding = padding
    db.flush()
    db.commit()
    return f"{prefix}{numero:0{padding}d}"


def peek_sequence(db: Session, tenant_id: uuid.UUID, tipo: str) -> str:
    """Devuelve el siguiente número de secuencia SIN consumirlo (spec 07).

    Permite al admin ver el próximo número antes de emitir una orden/lote.
    Si todavía no existe fila para tenant+tipo+prefix, devuelve el 001.
    """
    if tipo not in ("order", "lot"):
        raise ValueError(f"Tipo de secuencia inválido: {tipo}")

    ahora = datetime.now(UTC)
    template, padding = _config(db, tenant_id, tipo)
    prefix = _resolver_prefix(template, ahora)

    fila = db.scalar(
        select(Sequence).where(
            Sequence.tenant_id == tenant_id,
            Sequence.sequence_type == tipo,
            Sequence.prefix == prefix,
        )
    )
    numero = fila.next_number if fila is not None else 1
    return f"{prefix}{numero:0{padding}d}"
