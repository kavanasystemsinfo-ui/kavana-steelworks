"""Servicio de sesiones de subida de fotos de incidencias (flujo QR + móvil).

Portado de kavana-manufacturing (IncidenciaUploadsService):
- crear_sesion: TTL 15 min (SESSION_TTL_MINUTES); limpieza lazy de sesiones
  pendientes vencidas antes de crear una nueva
- adjuntar_foto: la subida pública resuelve el tenant desde la propia sesión
  (el móvil va sin token); valida estado pending, TTL y magic bytes
- obtener_sesion / obtener_foto: polling del modal del puesto de trabajo
- finalizar: al crear la incidencia, copia la foto a la incidencia y marca la
  sesión 'used' liberando los bytes temporales
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.incidencia import Incidencia
from app.models.incidencia_upload import IncidenciaUploadSession

SESSION_TTL_MINUTES = 15


class UploadError(Exception):
    """Error de sesión con su código HTTP (404/409/410/400)."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def crear_sesion(
    db: Session, *, tenant_id: uuid.UUID, operario_id: uuid.UUID
) -> IncidenciaUploadSession:
    """Crea una sesión pendiente con TTL; expira las vencidas (lazy).

    También expira sesiones 'uploaded' huérfanas de más de 24 h (por ejemplo
    cuando el operario descarta la foto del modal sin reportar).
    """
    ahora = datetime.now(UTC)
    db.query(IncidenciaUploadSession).filter(
        IncidenciaUploadSession.tenant_id == tenant_id,
        IncidenciaUploadSession.status == "pending",
        IncidenciaUploadSession.expires_at < ahora,
    ).update({IncidenciaUploadSession.status: "expired"}, synchronize_session=False)
    db.query(IncidenciaUploadSession).filter(
        IncidenciaUploadSession.tenant_id == tenant_id,
        IncidenciaUploadSession.status == "uploaded",
        IncidenciaUploadSession.expires_at < ahora - timedelta(hours=24),
    ).update({IncidenciaUploadSession.status: "expired"}, synchronize_session=False)

    sesion = IncidenciaUploadSession(
        tenant_id=tenant_id,
        session_id=uuid.uuid4(),
        created_by=operario_id,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(minutes=SESSION_TTL_MINUTES),
    )
    db.add(sesion)
    db.commit()
    db.refresh(sesion)
    return sesion


def _buscar_por_session_id(db: Session, session_id: uuid.UUID):
    return db.query(IncidenciaUploadSession).filter_by(session_id=session_id).first()


def _caducada(expires_at) -> bool:
    """True si la sesión caducó. SQLite devuelve datetimes naive (sin tz)."""
    if expires_at is None:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at < datetime.now(UTC)


def adjuntar_foto(db: Session, *, session_id: uuid.UUID, buf: bytes) -> dict:
    """Subida pública desde el móvil: valida sesión y guarda la foto."""
    from app.services.photo_validator import validar_foto

    sesion = _buscar_por_session_id(db, session_id)
    if sesion is None:
        raise UploadError("Sesión de subida no encontrada", 404)
    if sesion.status != "pending":
        raise UploadError(
            "La sesión ya no está pendiente (foto subida o incidencia creada)", 409
        )
    if _caducada(sesion.expires_at):
        raise UploadError(
            "La sesión ha caducado. Vuelve a abrir el modal de incidencias.", 410
        )

    validacion = validar_foto(buf)
    if not validacion["ok"]:
        raise UploadError(validacion["reason"], 400)

    sesion.status = "uploaded"
    sesion.photo = buf
    sesion.photo_mime = validacion["mime"]
    sesion.photo_size = validacion["size"]
    db.commit()
    return {"ok": True, "mime": validacion["mime"], "size": validacion["size"]}


def obtener_sesion(
    db: Session, *, tenant_id: uuid.UUID, session_id: uuid.UUID
) -> dict:
    """Estado de la sesión para el polling del modal (con foto como data URL)."""
    sesion = db.query(IncidenciaUploadSession).filter(
        IncidenciaUploadSession.tenant_id == tenant_id,
        IncidenciaUploadSession.session_id == session_id,
    ).first()
    if sesion is None:
        raise UploadError("Sesión de subida no encontrada", 404)

    return _serializar_sesion(sesion)


def obtener_sesion_por_id(db: Session, *, session_id: uuid.UUID) -> dict:
    """Estado de la sesión resolviendo el tenant desde la propia sesión.

    El polling del móvil va sin token (solo conoce el session_id); la sesión
    guarda su tenant_id, así que no hay que adivinar el tenant.
    """
    sesion = _buscar_por_session_id(db, session_id)
    if sesion is None:
        raise UploadError("Sesión de subida no encontrada", 404)
    return _serializar_sesion(sesion)


def _serializar_sesion(sesion) -> dict:
    import base64

    return {
        "session_id": str(sesion.session_id),
        "status": sesion.status,
        "expires_at": sesion.expires_at,
        "has_photo": sesion.photo is not None,
        "incidencia_id": str(sesion.incidencia_id) if sesion.incidencia_id else None,
        "photo_data_url": (
            f"data:{sesion.photo_mime};base64,{base64.b64encode(sesion.photo).decode()}"
            if sesion.photo is not None
            else None
        ),
    }


def obtener_foto(
    db: Session, *, tenant_id: uuid.UUID, session_id: uuid.UUID
) -> tuple[bytes, str]:
    """Bytes de la foto para el preview del modal."""
    sesion = db.query(IncidenciaUploadSession).filter(
        IncidenciaUploadSession.tenant_id == tenant_id,
        IncidenciaUploadSession.session_id == session_id,
        IncidenciaUploadSession.photo.is_not(None),
    ).first()
    if sesion is None:
        raise UploadError("Foto no encontrada", 404)
    return sesion.photo, sesion.photo_mime


def obtener_foto_por_id(db: Session, *, session_id: uuid.UUID) -> tuple[bytes, str]:
    """Bytes de la foto resolviendo el tenant desde la propia sesión (móvil)."""
    sesion = _buscar_por_session_id(db, session_id)
    if sesion is None or sesion.photo is None:
        raise UploadError("Foto no encontrada", 404)
    return sesion.photo, sesion.photo_mime


def finalizar(
    db: Session, *, tenant_id: uuid.UUID, session_id: uuid.UUID, incidencia_id: uuid.UUID
) -> bool:
    """Copia la foto de la sesión a la incidencia y marca la sesión 'used'."""
    sesion = db.query(IncidenciaUploadSession).filter(
        IncidenciaUploadSession.tenant_id == tenant_id,
        IncidenciaUploadSession.session_id == session_id,
    ).first()
    if sesion is None or sesion.status != "uploaded" or sesion.photo is None:
        return False

    incidencia = db.query(Incidencia).filter(
        Incidencia.id == incidencia_id, Incidencia.tenant_id == tenant_id
    ).first()
    if incidencia is None:
        return False

    incidencia.foto_data = sesion.photo
    incidencia.foto_mime = sesion.photo_mime
    incidencia.foto_size = sesion.photo_size

    sesion.status = "used"
    sesion.incidencia_id = incidencia.id
    sesion.photo = None
    sesion.photo_mime = None
    sesion.photo_size = None
    db.commit()
    return True
