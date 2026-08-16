"""Router de incidencias de planta (spec 04 §3.3): alta, listado y resolución.

Alta desde el operario (puesto + descripción + tipo), listado para el
Supervisor y actualización con cierre financiero (tiempo de parada en
minutos y coste en euros, conservando campos previos no enviados).
"""

import base64
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import autenticar, require_roles
from app.models import User
from app.services.photo_validator import MAX_FOTO_BYTES

router = APIRouter(prefix="/api/v1/incidencias", tags=["incidencias"])

# Rate limit de subida de fotos por IP (patrón kavana-manufacturing): ventana
# deslizante de 20 subidas cada 10 minutos. El endpoint de subida acepta
# binario de la demo pública; sin límite sería un agujero de almacenamiento.
MAX_SUBIDAS_VENTANA = 20
VENTANA_SUBIDA_SEGUNDOS = 10 * 60
_upload_attempts: dict[str, list[float]] = {}


def _podar_ips_vencidas(ahora: float) -> None:
    """Elimina IPs sin actividad reciente (evita que el dict crezca sin fin)."""
    vencidas = [
        ip
        for ip, intentos in _upload_attempts.items()
        if not any(ahora - t < VENTANA_SUBIDA_SEGUNDOS for t in intentos)
    ]
    for ip in vencidas:
        del _upload_attempts[ip]


def _enforce_upload_rate_limit(ip: str) -> None:
    ahora = time.time()
    _podar_ips_vencidas(ahora)
    recientes = [t for t in _upload_attempts.get(ip, []) if ahora - t < VENTANA_SUBIDA_SEGUNDOS]
    if len(recientes) >= MAX_SUBIDAS_VENTANA:
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos de subida. Inténtalo de nuevo más tarde.",
        )
    recientes.append(ahora)
    _upload_attempts[ip] = recientes


async def _leer_foto_limitada(foto: UploadFile, max_bytes: int = MAX_FOTO_BYTES) -> bytes:
    """Lee la subida en chunks y aborta si supera el límite (evita cargar el
    cuerpo completo en memoria antes de validar el tamaño)."""
    buf = bytearray()
    while True:
        chunk = await foto.read(1024 * 1024)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"La imagen supera el tamaño máximo de {max_bytes // (1024 * 1024)}MB",
            )
    return bytes(buf)


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


class IncidenciaIn(BaseModel):
    linea_id: str = Field(max_length=255)
    descripcion: str = Field(max_length=2000)
    tipo: str = "otro"
    foto: str | None = Field(default=None, max_length=15_000_000)
    photo_session_id: str | None = Field(default=None, max_length=64)  # sesión QR + móvil


class IncidenciaUpdate(BaseModel):
    estado: str | None = None
    comentario: str | None = Field(default=None, max_length=2000)
    resolucion_tipo: str | None = Field(default=None, max_length=64)
    resolucion_descripcion: str | None = Field(default=None, max_length=2000)
    tiempo_parada_min: Decimal | None = Field(default=None, ge=0)
    coste: Decimal | None = Field(default=None, ge=0)


class UploadSessionOut(BaseModel):
    session_id: str
    status: str
    expires_at: datetime
    has_photo: bool
    incidencia_id: str | None = None


@router.post("/upload-session", response_model=UploadSessionOut)
def crear_sesion_subida(
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator", "supervisor", "admin")),
    ] = None,
):
    """Crea una sesión QR de subida para el operario (TTL 15 min)."""
    from app.services.incidencia_uploads import crear_sesion as service

    tenant = current_user.tenant_id
    operario_id = current_user.id

    sesion = service(db, tenant_id=tenant, operario_id=operario_id)
    return UploadSessionOut(
        session_id=str(sesion.session_id),
        status=sesion.status,
        expires_at=sesion.expires_at,
        has_photo=False,
        incidencia_id=None,
    )


@router.post("/upload-mobile/{session_id}")
async def subir_foto_movil(
    session_id: uuid.UUID,
    request: Request,
    foto: Annotated[UploadFile, File()],
    db: DbDep = None,
):
    """Subida PÚBLICA desde el móvil: el session_id es la credencial de un solo uso.

    El tenant se resuelve desde la propia sesión (el móvil va sin token);
    valida estado pending, TTL y magic bytes. Rate limit por IP.
    """
    from app.services.incidencia_uploads import UploadError, adjuntar_foto

    _enforce_upload_rate_limit(request.client.host if request.client else "unknown")

    buf = await _leer_foto_limitada(foto)
    try:
        return adjuntar_foto(db, session_id=session_id, buf=buf)
    except UploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/upload-session/{session_id}")
def estado_sesion_subida(session_id: uuid.UUID, db: DbDep):
    """Estado de la sesión para el polling del modal (incluye foto data URL)."""
    from app.services.incidencia_uploads import UploadError, obtener_sesion_por_id

    try:
        return obtener_sesion_por_id(db, session_id=session_id)
    except UploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/upload-session/{session_id}/photo")
def foto_sesion_subida(session_id: uuid.UUID, db: DbDep):
    """Bytes de la foto para el preview del modal."""
    from fastapi import Response

    from app.services.incidencia_uploads import UploadError, obtener_foto_por_id

    try:
        buf, mime = obtener_foto_por_id(db, session_id=session_id)
    except UploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(content=buf, media_type=mime, headers={"Cache-Control": "private, max-age=300"})


@router.post("", status_code=201)
def crear_incidencia(
    body: IncidenciaIn,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator", "supervisor", "admin")),
    ] = None,
):
    """Reporta una incidencia desde el puesto (operario)."""
    from app.services.incidencias import crear_incidencia as service

    try:
        incidencia = service(
            db,
            tenant_id=current_user.tenant_id,
            operario_id=current_user.id,
            linea_id=body.linea_id,
            descripcion=body.descripcion,
            tipo=body.tipo,
            foto=body.foto,
            photo_session_id=body.photo_session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "msg": "Incidencia registrada", "incidencia": _out(incidencia)}


@router.get("")
def listar_incidencias(
    db: DbDep,
    limit: int = 50,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Incidencias del tenant para el Supervisor (desc, límite 50)."""
    from app.services.incidencias import listar_incidencias as service

    incidencias = service(db, current_user.tenant_id, limit=limit)
    return {"success": True, "incidencias": [_out(i) for i in incidencias]}


@router.patch("/{incidencia_id}")
def actualizar_incidencia(
    incidencia_id: uuid.UUID,
    body: IncidenciaUpdate,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Cambia estado y/o resolución financiera (Supervisor)."""
    from app.services.incidencias import actualizar_incidencia as service

    try:
        incidencia = service(
            db,
            incidencia_id=incidencia_id,
            tenant_id=current_user.tenant_id,
            usuario_id=current_user.id,
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


@router.post("/{incidencia_id}/foto")
async def subir_foto_incidencia(
    incidencia_id: uuid.UUID,
    request: Request,
    foto: Annotated[UploadFile, File()],
    db: DbDep = None,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator", "supervisor", "admin")),
    ] = None,
):
    """Adjunta la foto de la incidencia (BYTEA, validación por magic bytes).

    Patrón de kavana-manufacturing: sin Cloudinary ni servicios externos,
    la evidencia vive en PostgreSQL. Rate limit por IP (20 subidas / 10 min).
    """
    from app.services.incidencia_uploads import UploadError
    from app.services.incidencias import subir_foto as service

    _enforce_upload_rate_limit(request.client.host if request.client else "unknown")

    buf = await _leer_foto_limitada(foto)
    try:
        incidencia = service(
            db, incidencia_id=incidencia_id, tenant_id=current_user.tenant_id, buf=buf
        )
    except UploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {
        "success": True,
        "msg": "Foto adjuntada",
        "incidencia": _out(incidencia),
    }


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
        "foto_data_url": (
            f"data:{i.foto_mime};base64,{base64.b64encode(i.foto_data).decode()}"
            if i.foto_data is not None
            else None
        ),
        "foto_size": i.foto_size,
        "estado": i.estado,
        "resolucion_tipo": i.resolucion_tipo,
        "resolucion_descripcion": i.resolucion_descripcion,
        "tiempo_parada_min": i.tiempo_parada_min,
        "coste": i.coste,
        "created_at": i.created_at,
        "operario": (
            {"id": i.operario.id, "name": i.operario.name} if i.operario is not None else None
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
