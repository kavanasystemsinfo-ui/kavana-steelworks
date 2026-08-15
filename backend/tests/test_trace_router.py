"""Tests del router de trazabilidad (spec 04 §3.1): GET /api/v1/trace/orders/{id}.

La traza es la serie temporal completa de eventos de una orden. El endpoint
es de solo lectura (los ProductionLog son inmutables).
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.routers import trace as trace_router
from app.services import traceability
from tests.helpers import make_order, make_order_line


def _poblar_traza(db, tenant, user, orden):
    linea = make_order_line(db, orden, total_quantity=100, linea_numero=1)
    base = datetime(2026, 8, 15, 8, 0, tzinfo=UTC)
    for i, action in enumerate(["start", "produce", "finish"]):
        traceability.log_event(
            db,
            tenant_id=tenant.id,
            order_id=orden.id,
            line_id=linea.id,
            operator_id=user.id,
            action=action,
            quantity=10 if action == "produce" else 0,
            timestamp=base.replace(minute=i),
        )
    return linea


def test_get_order_trace_devuelve_serie_ordenada(db_session, tenant, user):
    orden = make_order(db_session, tenant, numero="OP-TRAZA")
    _poblar_traza(db_session, tenant, user, orden)

    def _override_get_db():
        yield db_session

    app.dependency_overrides[trace_router.get_db] = _override_get_db
    try:
        client = TestClient(app)
        r = client.get(f"/api/v1/trace/orders/{orden.id}")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    body = r.json()
    assert [e["action"] for e in body] == ["start", "produce", "finish"]
    produce = next(e for e in body if e["action"] == "produce")
    assert produce["quantity"] == "10.000"
    assert produce["operator"]["id"] == str(user.id)
    assert produce["operator"]["name"] == user.name
    assert produce["metadata"] is not None or "metadata" in produce


def test_get_order_trace_404_si_orden_no_existe(db_session):
    import uuid

    def _override_get_db():
        yield db_session

    app.dependency_overrides[trace_router.get_db] = _override_get_db
    try:
        client = TestClient(app)
        r = client.get(f"/api/v1/trace/orders/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 404
