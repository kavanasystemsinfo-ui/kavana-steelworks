"""Tests del contrato de auth por roles (Fase 6, login + roles demo).

Matriz de permisos de la demo:
- operario (operator): escaneo, vincular, fin de bobina, retirar, producción,
  autocontroles, crear incidencia y subir foto.
- materias (materials): recepción e inventario (POST /stock-items, GET listas).
- supervisor (supervisor): OEE/KPIs, trazabilidad, órdenes, gestión de
  incidencias (listar/resolver), y también puede operar (demo).
- admin: acceso total (hereda supervisor).
- Público sin token: login, subida de foto del móvil y estado de sesión.
- 401 sin token válido; 403 con rol sin permiso.
"""

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.routers import (
    auth as auth_router,
)
from app.routers import (
    incidencias as incidencias_router,
)
from app.routers import (
    orders as orders_router,
)
from app.routers import (
    production as production_router,
)
from app.routers import (
    quality as quality_router,
)
from app.routers import (
    stock as stock_router,
)
from app.routers import (
    supervisor as supervisor_router,
)
from app.routers import (
    trace as trace_router,
)
from tests.helpers import auth_headers


def _override_get_db(db_session):
    def _gen():
        yield db_session

    return _gen


def _override_all(db_session):
    gen = _override_get_db(db_session)
    app.dependency_overrides[auth_router.get_db] = gen
    app.dependency_overrides[stock_router.get_db] = gen
    app.dependency_overrides[production_router.get_db] = gen
    app.dependency_overrides[quality_router.get_db] = gen
    app.dependency_overrides[supervisor_router.get_db] = gen
    app.dependency_overrides[orders_router.get_db] = gen
    app.dependency_overrides[trace_router.get_db] = gen
    app.dependency_overrides[incidencias_router.get_db] = gen


def _client(db_session, headers=None):
    _override_all(db_session)
    c = TestClient(app)
    if headers:
        c.headers.update(headers)
    return c


# ── 401: sin token o token inválido ────────────────────────────────

def test_endpoint_protegido_sin_token_devuelve_401(db_session, tenant, user):
    client = _client(db_session)
    r = client.get("/api/v1/orders")
    assert r.status_code == 401, r.text
    assert "token" in r.json()["detail"].lower()


def test_endpoint_protegido_token_invalido_devuelve_401(db_session, tenant, user):
    client = _client(db_session, {"Authorization": "Bearer token-falso"})
    r = client.get("/api/v1/stock-items/materials")
    assert r.status_code == 401, r.text


def test_login_es_publico(db_session, tenant, user):
    from tests.helpers import make_user

    make_user(db_session, tenant, email="login@test.local", role="operator")
    client = _client(db_session)
    r = client.post("/api/v1/auth/login", json={"email": "login@test.local", "password": "kavana"})
    assert r.status_code == 200, r.text
    assert "access_token" in r.json()


# ── 403: rol sin permiso ───────────────────────────────────────────

def test_operario_no_puede_ver_oee(db_session, tenant, user):
    client = _client(db_session, auth_headers(db_session, tenant, role="operator"))
    r = client.get("/api/v1/supervisor/oee")
    assert r.status_code == 403, r.text


def test_operario_no_puede_recibir_bobinas(db_session, tenant, user):
    client = _client(db_session, auth_headers(db_session, tenant, role="operator"))
    r = client.post("/api/v1/stock-items", json={})
    assert r.status_code == 403, r.text


def test_materias_no_puede_registrar_produccion(db_session, tenant, user):
    client = _client(db_session, auth_headers(db_session, tenant, role="materials"))
    r = client.post("/api/v1/production/record", json={})
    assert r.status_code == 403, r.text


def test_materias_no_puede_gestionar_incidencias(db_session, tenant, user):
    client = _client(db_session, auth_headers(db_session, tenant, role="materials"))
    r = client.get("/api/v1/incidencias")
    assert r.status_code == 403, r.text


# ── 200: rol correcto ──────────────────────────────────────────────

def test_supervisor_puede_ver_oee(db_session, tenant, user):
    client = _client(db_session, auth_headers(db_session, tenant, role="supervisor"))
    r = client.get("/api/v1/supervisor/oee")
    assert r.status_code == 200, r.text


def test_materias_puede_listar_inventario(db_session, tenant, user):
    client = _client(db_session, auth_headers(db_session, tenant, role="materials"))
    r = client.get("/api/v1/stock-items")
    assert r.status_code == 200, r.text


def test_operario_puede_listar_materiales(db_session, tenant, user):
    client = _client(db_session, auth_headers(db_session, tenant, role="operator"))
    r = client.get("/api/v1/stock-items/materials")
    assert r.status_code == 200, r.text


def test_admin_hereda_supervisor(db_session, tenant, user):
    client = _client(db_session, auth_headers(db_session, tenant, role="admin"))
    r = client.get("/api/v1/supervisor/oee")
    assert r.status_code == 200, r.text
    r2 = client.get("/api/v1/orders")
    assert r2.status_code == 200, r2.text


# ── Público móvil ──────────────────────────────────────────────────

def test_subida_movil_sigue_siendo_publica(db_session, tenant, user):
    from datetime import UTC, datetime, timedelta

    from app.models import IncidenciaUploadSession

    sesion = IncidenciaUploadSession(
        tenant_id=tenant.id,
        session_id=uuid.uuid4(),
        created_by=user.id,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )
    db_session.add(sesion)
    db_session.commit()

    client = _client(db_session)  # sin token
    r = client.get(f"/api/v1/incidencias/upload-session/{sesion.session_id}")
    assert r.status_code == 200, r.text
