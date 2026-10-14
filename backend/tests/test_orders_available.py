"""Tests del endpoint del operario: GET /api/v1/orders/available.

Port del patrón de kavana-manufacturing: el operario no ve el listado global
de órdenes (eso es del supervisor), sino solo las órdenes activas de su
propia estación de trabajo, derivada de default_workstation_code del usuario.

Esto evita el bug que rompía el panel del operario: llamar al listado global
(supervisor-only) devolvía 403, la orden quedaba null y el registro de
producción enviaba order_id nulo.
"""

from app.main import app
from app.models import Order
from app.routers import orders as orders_router
from tests.helpers import (
    authed_client_for,
    make_order,
    make_order_line,
    make_user,
)


def _override_get_db(db_session):
    def _gen():
        yield db_session

    return _gen


def _make_order_estado(db, tenant, numero, estado):
    """make_order siempre crea 'active'; aquí forzamos otro estado."""
    o = make_order(db, tenant, numero=numero)
    o.estado = estado
    db.commit()
    db.refresh(o)
    return o


def test_available_operario_ve_ordenes_activas_de_su_estacion(db_session, tenant):
    o = make_order(db_session, tenant, numero="OP-AV-001")
    make_order_line(db_session, o, workstation="LINEA-1")
    operario = make_user(db_session, tenant, email="op-avail@test.local", role="operator")
    operario.default_workstation_code = "LINEA-1"
    db_session.commit()
    db_session.refresh(operario)

    app.dependency_overrides[orders_router.get_db] = _override_get_db(db_session)
    try:
        client = authed_client_for(db_session, operario)
        r = client.get("/api/v1/orders/available")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    body = r.json()
    assert any(item["numero"] == "OP-AV-001" for item in body)


def test_available_no_incluye_ordenes_de_otra_estacion(db_session, tenant):
    o_mine = make_order(db_session, tenant, numero="OP-AV-MINE")
    make_order_line(db_session, o_mine, workstation="LINEA-1")
    o_other = make_order(db_session, tenant, numero="OP-AV-OTHER")
    make_order_line(db_session, o_other, workstation="LINEA-9")
    operario = make_user(db_session, tenant, email="op-avail2@test.local", role="operator")
    operario.default_workstation_code = "LINEA-1"
    db_session.commit()
    db_session.refresh(operario)

    app.dependency_overrides[orders_router.get_db] = _override_get_db(db_session)
    try:
        client = authed_client_for(db_session, operario)
        r = client.get("/api/v1/orders/available")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    numeros = [item["numero"] for item in r.json()]
    assert "OP-AV-MINE" in numeros
    assert "OP-AV-OTHER" not in numeros


def test_available_excluye_ordenes_completadas(db_session, tenant):
    o = _make_order_estado(db_session, tenant, numero="OP-AV-DONE", estado="completed")
    make_order_line(db_session, o, workstation="LINEA-1")
    operario = make_user(db_session, tenant, email="op-avail3@test.local", role="operator")
    operario.default_workstation_code = "LINEA-1"
    db_session.commit()
    db_session.refresh(operario)

    app.dependency_overrides[orders_router.get_db] = _override_get_db(db_session)
    try:
        client = authed_client_for(db_session, operario)
        r = client.get("/api/v1/orders/available")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    assert all(item["numero"] != "OP-AV-DONE" for item in r.json())


def test_available_excluye_ordenes_de_otro_tenant(db_session, tenant):
    from tests.helpers import make_tenant

    other = make_tenant(db_session, name="Otro Tenant")
    o = make_order(db_session, other, numero="OP-AV-TENANT")
    make_order_line(db_session, o, workstation="LINEA-1")
    operario = make_user(db_session, tenant, email="op-avail4@test.local", role="operator")
    operario.default_workstation_code = "LINEA-1"
    db_session.commit()
    db_session.refresh(operario)

    app.dependency_overrides[orders_router.get_db] = _override_get_db(db_session)
    try:
        client = authed_client_for(db_session, operario)
        r = client.get("/api/v1/orders/available")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    assert all(item["numero"] != "OP-AV-TENANT" for item in r.json())


def test_available_sin_estacion_devuelve_vacio(db_session, tenant):
    o = make_order(db_session, tenant, numero="OP-AV-NOOP")
    make_order_line(db_session, o, workstation="LINEA-1")
    # el operario no tiene default_workstation_code
    operario = make_user(db_session, tenant, email="op-nows@test.local", role="operator")

    app.dependency_overrides[orders_router.get_db] = _override_get_db(db_session)
    try:
        client = authed_client_for(db_session, operario)
        r = client.get("/api/v1/orders/available")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    assert r.json() == []
