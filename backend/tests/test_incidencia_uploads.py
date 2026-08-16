"""Tests del flujo QR + móvil de fotos de incidencias (spec 04 §3.3.2).

Portado de kavana-manufacturing (IncidenciaUploadsService):
- crear sesión con TTL 15 min (status pending); limpieza lazy de vencidas
- subida pública con session_id como credencial de un solo uso (magic bytes)
- al crear la incidencia con photo_session_id, la foto se copia a la
  incidencia y la sesión pasa a 'used'
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models import Incidencia
from app.models.incidencia_upload import IncidenciaUploadSession
from app.routers import incidencias as inc_router
from tests.helpers import make_order, make_order_line

PNG_DEMO = b"\x89PNG\r\n\x1a\n" + b"data-de-prueba"


def _override_get_db(db_session):
    def _gen():
        yield db_session

    return _gen


def _crear_sesion(db_session, tenant, user) -> dict:
    app.dependency_overrides[inc_router.get_db] = _override_get_db(db_session)
    try:
        client = TestClient(app)
        return client.post("/api/v1/incidencias/upload-session").json()
    finally:
        app.dependency_overrides.clear()


def _subir_movil(db_session, session_id: str, buf: bytes = PNG_DEMO, filename: str = "foto.png"):
    app.dependency_overrides[inc_router.get_db] = _override_get_db(db_session)
    try:
        client = TestClient(app)
        return client.post(
            f"/api/v1/incidencias/upload-mobile/{session_id}",
            files={"foto": (filename, buf, "image/png")},
        )
    finally:
        app.dependency_overrides.clear()


def test_crear_sesion_devuelve_pending_con_ttl(db_session, tenant, user):
    body = _crear_sesion(db_session, tenant, user)
    assert body["status"] == "pending"
    assert body["has_photo"] is False
    expira = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=UTC)  # SQLite/Pydantic pierde la tz
    assert expira > datetime.now(UTC)


def test_subida_movil_y_polling_con_data_url(db_session, tenant, user):
    sesion = _crear_sesion(db_session, tenant, user)
    sid = sesion["session_id"]

    r = _subir_movil(db_session, sid)
    assert r.status_code == 200, r.text

    app.dependency_overrides[inc_router.get_db] = _override_get_db(db_session)
    try:
        client = TestClient(app)
        r2 = client.get(f"/api/v1/incidencias/upload-session/{sid}")
    finally:
        app.dependency_overrides.clear()

    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["status"] == "uploaded"
    assert body["has_photo"] is True
    assert body["photo_data_url"].startswith("data:image/png;base64,")


def test_subida_movil_sesion_inexistente_404(db_session, tenant, user):
    r = _subir_movil(db_session, str(uuid.uuid4()))
    assert r.status_code == 404


def test_subida_movil_sesion_caducada_410(db_session, tenant, user):
    sesion = _crear_sesion(db_session, tenant, user)
    fila = db_session.query(IncidenciaUploadSession).filter_by(
        session_id=uuid.UUID(sesion["session_id"])
    ).one()
    fila.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    r = _subir_movil(db_session, sesion["session_id"])
    assert r.status_code == 410


def test_subida_movil_foto_invalida_400(db_session, tenant, user):
    sesion = _crear_sesion(db_session, tenant, user)
    r = _subir_movil(
        db_session, sesion["session_id"], buf=b"esto no es una imagen", filename="nota.txt"
    )
    assert r.status_code == 400
    assert "imágenes" in r.json()["detail"]


def test_crear_incidencia_con_foto_copia_y_marca_used(db_session, tenant, user):
    orden = make_order(db_session, tenant, numero="OP-INC-FOTO")
    make_order_line(db_session, orden, workstation="LINEA-1")
    sesion = _crear_sesion(db_session, tenant, user)
    assert _subir_movil(db_session, sesion["session_id"]).status_code == 200

    app.dependency_overrides[inc_router.get_db] = _override_get_db(db_session)
    try:
        client = TestClient(app)
        r = client.post(
            "/api/v1/incidencias",
            json={
                "linea_id": "LINEA-1",
                "descripcion": "Incidencia con evidencia",
                "tipo": "maquina",
                "photo_session_id": sesion["session_id"],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 201, r.text
    inc = db_session.query(Incidencia).one()
    assert inc.foto_data == PNG_DEMO
    assert inc.foto_mime == "image/png"
    assert inc.foto_size == len(PNG_DEMO)

    fila = db_session.query(IncidenciaUploadSession).filter_by(
        session_id=uuid.UUID(sesion["session_id"])
    ).one()
    assert fila.status == "used"
    assert fila.incidencia_id == inc.id
    assert fila.photo is None  # la foto temporal se libera


def test_crear_incidencia_con_sesion_pendiente_no_falla(db_session, tenant, user):
    orden = make_order(db_session, tenant, numero="OP-INC-SIN-FOTO")
    make_order_line(db_session, orden, workstation="LINEA-1")
    sesion = _crear_sesion(db_session, tenant, user)

    app.dependency_overrides[inc_router.get_db] = _override_get_db(db_session)
    try:
        client = TestClient(app)
        r = client.post(
            "/api/v1/incidencias",
            json={
                "linea_id": "LINEA-1",
                "descripcion": "Sin foto",
                "tipo": "otro",
                "photo_session_id": sesion["session_id"],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 201, r.text
    inc = db_session.query(Incidencia).one()
    assert inc.foto_data is None


async def test_leer_foto_limitada_aborta_si_supera_limite():
    import io

    import pytest
    from fastapi import HTTPException
    from starlette.datastructures import UploadFile

    from app.routers.incidencias import _leer_foto_limitada

    f = UploadFile(io.BytesIO(b"x" * 100), filename="foto.png")
    with pytest.raises(HTTPException) as exc:
        await _leer_foto_limitada(f, max_bytes=50)
    assert exc.value.status_code == 413


async def test_leer_foto_limitada_acepta_dentro_del_limite():
    import io

    from starlette.datastructures import UploadFile

    from app.routers.incidencias import _leer_foto_limitada

    f = UploadFile(io.BytesIO(b"x" * 30), filename="foto.png")
    buf = await _leer_foto_limitada(f, max_bytes=50)
    assert buf == b"x" * 30
