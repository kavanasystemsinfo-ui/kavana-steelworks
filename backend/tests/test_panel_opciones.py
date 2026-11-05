"""Opciones del panel: los euros están desactivados salvo que la empresa los active."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import supervisor as supervisor_router
from tests.helpers import auth_headers

URL = "/api/v1/supervisor/panel/opciones"


@pytest.fixture()
def panel(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[supervisor_router.get_db] = _override_get_db

    def _cliente(tenant, role="supervisor"):
        client = TestClient(app)
        client.headers.update(auth_headers(db_session, tenant, role=role))
        return client

    yield _cliente
    app.dependency_overrides.clear()


def test_por_defecto_los_costes_en_euros_estan_desactivados(db_session, tenant, panel):
    r = panel(tenant).get(URL)
    assert r.status_code == 200
    assert r.json() == {"mostrar_costes": False}


def test_la_empresa_puede_activar_los_costes(db_session, tenant, panel):
    tenant.finances = {**(tenant.finances or {}), "mostrar_costes": True}
    db_session.commit()
    assert panel(tenant).get(URL).json() == {"mostrar_costes": True}


def test_solo_el_supervisor_lee_las_opciones(db_session, tenant, panel):
    assert panel(tenant, role="operator").get(URL).status_code == 403
    assert TestClient(app).get(URL).status_code == 401
