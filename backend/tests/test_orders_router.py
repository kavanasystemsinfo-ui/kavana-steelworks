"""Tests del router de órdenes: GET /api/v1/orders (listado para el selector de trazabilidad).

Devuelve las órdenes del tenant de la demo (patrón supervisor: primer tenant,
auth por roles pendiente Fase 5) con los campos que necesita la UI, ordenadas
por creación descendente y con límite duro de 50.
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models import Order
from app.routers import orders as orders_router


def _override_get_db(db_session):
    def _gen():
        yield db_session

    return _gen


def _crear_orden(db, tenant, numero="OP-LIST-001", estado="active", cliente="Cliente A"):
    o = Order(
        tenant_id=tenant.id,
        numero=numero,
        estado=estado,
        cliente=cliente,
        fecha_entrega=datetime(2026, 8, 20, tzinfo=UTC),
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def test_list_orders_devuelve_ordenes_del_tenant(db_session, tenant, user):
    o1 = _crear_orden(db_session, tenant, numero="OP-LIST-001")
    o2 = _crear_orden(db_session, tenant, numero="OP-LIST-002", estado="completed")

    app.dependency_overrides[orders_router.get_db] = _override_get_db(db_session)
    try:
        client = TestClient(app)
        r = client.get("/api/v1/orders")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    body = r.json()
    numeros = [o["numero"] for o in body]
    assert "OP-LIST-001" in numeros
    assert "OP-LIST-002" in numeros

    por_id = {o["id"]: o for o in body}
    assert por_id[str(o1.id)]["estado"] == "active"
    assert por_id[str(o1.id)]["cliente"] == "Cliente A"
    assert por_id[str(o1.id)]["fecha_entrega"] is not None
    assert por_id[str(o2.id)]["estado"] == "completed"


def test_list_orders_sin_tenant_devuelve_vacio(db_session):
    app.dependency_overrides[orders_router.get_db] = _override_get_db(db_session)
    try:
        client = TestClient(app)
        r = client.get("/api/v1/orders")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    assert r.json() == []
