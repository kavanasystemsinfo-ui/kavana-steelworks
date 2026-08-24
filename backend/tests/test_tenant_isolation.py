"""Tests de autorización cross-tenant (auditoría externa 2026-08-24, hallazgos 1-2).

Contrato nuevo (P0):
- GET /api/v1/events/{tenant_id}: el tenant AUTORIZADO sale del JWT, nunca del
  path. Un usuario del tenant A que pide eventos del tenant B recibe 403.
- WS /api/v1/ws/events: access_token OBLIGATORIO. Sin token → 4403. Token de
  otro tenant → 4403 (ya existía, se mantiene como regresión).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app, get_db as main_get_db
from app.services.auth import login
from tests.helpers import make_tenant, make_user


def _override_get_db(db_session):
    def _gen():
        yield db_session

    return _gen


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[main_get_db] = _override_get_db(db_session)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_events_tenant_ajeno_cierra_403(db_session, tenant, client):
    """Hallazgo 1: autenticar() no basta; falta autorizar el recurso."""
    make_user(db_session, tenant, email="a@test.local", role="operator")
    t2 = make_tenant(db_session, name="Otra Planta")
    db_session.add(t2)
    db_session.commit()

    token = login(db_session, tenant.id, "a@test.local", "kavana")

    r = client.get(
        f"/api/v1/events/{t2.id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 403


def test_events_tenant_propio_sigue_funcionando(db_session, tenant, client):
    make_user(db_session, tenant, email="b@test.local", role="operator")
    token = login(db_session, tenant.id, "b@test.local", "kavana")

    r = client.get(
        f"/api/v1/events/{tenant.id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    assert r.json()["tenant_id"] == str(tenant.id)


def test_ws_sin_token_cierra_4403(db_session, tenant):
    """Hallazgo 2: el canal autenticado no admite conexiones anónimas."""
    from tests.test_websockets import ws_client  # noqa: F401  (fixture compartida)

    # reutilizamos la infraestructura directamente para no duplicar fixtures
    app.dependency_overrides[ws_router_get_db] = _override_get_db(db_session)
    try:
        c = TestClient(app)
        with pytest.raises(WebSocketDisconnect) as exc:
            with c.websocket_connect(f"/api/v1/ws/events?tenant_id={tenant.id}"):
                pass
        assert exc.value.code == 4403
    finally:
        app.dependency_overrides.clear()


# import tardío para evitar ciclo con test_websockets
from app.routers import ws as _ws  # noqa: E402

ws_router_get_db = _ws.get_db
