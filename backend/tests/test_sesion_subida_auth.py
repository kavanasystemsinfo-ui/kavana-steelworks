"""T-033 H1/H2: estado y foto de sesión de subida exigen token y tenant (auditoría T-029)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import incidencias as inc_router
from tests.helpers import make_tenant, make_user

PNG_DEMO = b"\x89PNG\r\n\x1a\n" + b"data-de-prueba"


def _override(db_session):
    def _gen():
        yield db_session

    return _gen


@pytest.fixture()
def otra(db_session):
    return make_tenant(db_session, name="Otra Empresa")


# ── H1/H2: sesiones de subida de fotos sin auth y sin tenant ──────────────


def _sesion_de(db_session, tenant, user):
    from app.services.incidencia_uploads import adjuntar_foto, crear_sesion

    sesion = crear_sesion(db_session, tenant_id=tenant.id, operario_id=user.id)
    adjuntar_foto(db_session, session_id=sesion.session_id, buf=PNG_DEMO)
    return sesion


def test_h1_estado_de_sesion_exige_token(db_session, tenant, user):
    """El estado de una sesión (y su foto en data URL) no puede ser público."""
    sesion = _sesion_de(db_session, tenant, user)
    app.dependency_overrides[inc_router.get_db] = _override(db_session)
    try:
        anonimo = TestClient(app)  # sin Authorization
        r = anonimo.get(f"/api/v1/incidencias/upload-session/{sesion.session_id}")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code in (401, 403), (
        f"sin token devolvió {r.status_code}: {r.text[:200]}"
    )


def test_h1_foto_de_sesion_exige_token(db_session, tenant, user):
    sesion = _sesion_de(db_session, tenant, user)
    app.dependency_overrides[inc_router.get_db] = _override(db_session)
    try:
        anonimo = TestClient(app)
        r = anonimo.get(f"/api/v1/incidencias/upload-session/{sesion.session_id}/photo")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code in (401, 403), (
        f"la foto se sirve sin token (HTTP {r.status_code}, {len(r.content)} bytes)"
    )


def test_h2_sesion_de_otra_empresa_da_404(db_session, tenant, user, otra):
    """Un token válido de la empresa A no puede leer la sesión de la empresa B."""
    from tests.helpers import authed_client_for

    user_b = make_user(db_session, otra, email="op-b@test.local", role="operator")
    sesion_b = _sesion_de(db_session, otra, user_b)

    app.dependency_overrides[inc_router.get_db] = _override(db_session)
    try:
        client_a = authed_client_for(db_session, user)
        r = client_a.get(f"/api/v1/incidencias/upload-session/{sesion_b.session_id}")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 404, (
        f"token de otra empresa leyó la sesión: HTTP {r.status_code} {r.text[:200]}"
    )

def test_h1_foto_sin_token_devuelve_401_y_no_bytes(db_session, tenant, user):
    """GET /photo sin token devuelve 401/403, sin bytes de la foto y content-type no image/*."""
    from app.services.incidencia_uploads import adjuntar_foto, crear_sesion

    sesion = crear_sesion(db_session, tenant_id=tenant.id, operario_id=user.id)
    adjuntar_foto(db_session, session_id=sesion.session_id, buf=PNG_DEMO)

    app.dependency_overrides[inc_router.get_db] = _override(db_session)
    try:
        anonimo = TestClient(app)  # sin Authorization
        r = anonimo.get(f"/api/v1/incidencias/upload-session/{sesion.session_id}/photo")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code in (401, 403), (
        f"sin token devolvió {r.status_code}: {r.text[:200]}"
    )
    # El cuerpo NO debe contener los bytes de la foto
    assert r.content != PNG_DEMO, "el cuerpo contiene los bytes de la foto"
    assert len(r.content) == 0 or PNG_DEMO not in r.content, "foto filtrada en respuesta sin token"
    # Content-Type no debe ser image/*
    content_type = r.headers.get("content-type", "")
    assert not content_type.startswith("image/"), (
        f"content-type es image/* ({content_type}) sin token"
    )

