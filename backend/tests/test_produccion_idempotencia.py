"""Tests TDD de idempotencia y validaciones del registro de producción (T-159).

Contrato (auditoría 20-11, hallazgos H1/H2/H4):
- Mismo client_request_id dos veces = un solo registro, la misma respuesta y
  duplicate: true en la segunda.
- Producir en una orden cancelada (o no active/in_progress) = 400.
- incremental_quantity decimal (2.5) = 422 en el router.
- ocurrido_en en el futuro (> ahora + 5 min) o más viejo de 24 h = 422.
- ocurrido_en llega a production_logs (timestamp del evento).
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.main import app
from app.routers import production as production_router
from tests.helpers import (
    auth_headers,
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
)


@pytest.fixture()
def client(db_session):
    """TestClient con la sesión SQLite del test (patrón test_auth_roles)."""
    from fastapi.testclient import TestClient

    def _gen():
        yield db_session

    app.dependency_overrides[production_router.get_db] = _gen
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(production_router.get_db, None)


def _setup(db, tenant, user, *, peso=800.0, ancho=122.0, espesor=0.5, meters=2.0, total=10.0):
    """Bobina vinculada a la orden + línea (mismo patrón que test_production)."""
    from app.services.inventory import link_coil

    material = make_material(db, tenant, code="ACERO-IDEM", cost=2.0)
    bobina = make_stock_item(
        db,
        tenant,
        material,
        cantidad=peso,
        lote="L-IDEM",
        fecha_entrada=datetime.now(UTC) - timedelta(days=1),
        coste=2.0,
        ancho=ancho,
        espesor=espesor,
    )
    order = make_order(db, tenant, numero="OP-IDEM")
    line = make_order_line(db, order, workstation="LINEA-1", total_quantity=total)
    line.meters_per_piece = Decimal(str(meters))
    db.commit()

    link_coil(db, tenant.id, user.id, stock_item_id=bobina.id, order_id=order.id, line_id=line.id)
    db.refresh(bobina)
    return material, bobina, order, line


def test_mismo_client_request_id_no_duplica(db_session, tenant, user):
    """El mismo client_request_id dos veces = un solo registro y duplicate true."""
    from sqlalchemy import select

    from app.models import ProductionLog
    from app.services.production import record_production

    _, _, order, line = _setup(db_session, tenant, user)
    client_request_id = uuid.uuid4()

    primera = record_production(
        db_session,
        tenant.id,
        user.id,
        order_id=order.id,
        line_id=line.id,
        incremental_quantity=5,
        client_request_id=client_request_id,
    )
    assert primera.get("duplicate") is not True

    segunda = record_production(
        db_session,
        tenant.id,
        user.id,
        order_id=order.id,
        line_id=line.id,
        incremental_quantity=5,
        client_request_id=client_request_id,
    )
    assert segunda["duplicate"] is True
    assert segunda["produced_quantity"] == primera["produced_quantity"]

    # Solo UN evento produce en la traza
    logs = db_session.scalars(
        select(ProductionLog).where(
            ProductionLog.order_id == order.id, ProductionLog.action == "produce"
        )
    ).all()
    assert len(logs) == 1

    db_session.refresh(line)
    assert line.produced_quantity == 5  # no 10


def test_producir_en_orden_cancelada_rechaza(db_session, tenant, user):
    """No se produce en órdenes canceladas (hallazgo H2, R1)."""
    from app.services.production import record_production

    _, _, order, line = _setup(db_session, tenant, user)
    order.estado = "cancelled"
    db_session.commit()

    with pytest.raises(ValueError, match="cancelada"):
        record_production(
            db_session,
            tenant.id,
            user.id,
            order_id=order.id,
            line_id=line.id,
            incremental_quantity=1,
        )


def test_producir_en_orden_draft_rechaza(db_session, tenant, user):
    """ANTES de R1: draft rechazaba. Tras R1: draft PERMITIDO (test mantenido como referencia histórica)."""
    # Este test verifica el comportamiento ANTERIOR a R1.
    # Tras R1, draft SÍ permite producir (ver test_producir_en_orden_draft_permitida).
    import pytest
    pytest.skip("Comportamiento cambiado por R1: draft ahora permitido")


def test_incremental_quantity_decimal_rechazado_en_router(db_session, tenant, user, client):
    """2.5 piezas no se admiten (hallazgo H4): el router responde 422."""
    _, _, order, line = _setup(db_session, tenant, user)
    client.headers.update(auth_headers(db_session, tenant))

    res = client.post(
        "/api/v1/production/record",
        json={
            "order_id": str(order.id),
            "line_id": str(line.id),
            "incremental_quantity": 2.5,
        },
    )
    assert res.status_code == 422


def test_ocurrido_en_futuro_rechazado_en_router(db_session, tenant, user, client):
    """ocurrido_en posterior a ahora + 5 min = 422."""
    _, _, order, line = _setup(db_session, tenant, user)
    client.headers.update(auth_headers(db_session, tenant))

    futuro = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    res = client.post(
        "/api/v1/production/record",
        json={
            "order_id": str(order.id),
            "line_id": str(line.id),
            "incremental_quantity": 1,
            "ocurrido_en": futuro,
        },
    )
    assert res.status_code == 422


def test_ocurrido_en_muy_antiguo_rechazado_en_router(db_session, tenant, user, client):
    """ocurrido_en anterior a ahora - 24 h = 422."""
    _, _, order, line = _setup(db_session, tenant, user)
    client.headers.update(auth_headers(db_session, tenant))

    antiguo = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    res = client.post(
        "/api/v1/production/record",
        json={
            "order_id": str(order.id),
            "line_id": str(line.id),
            "incremental_quantity": 1,
            "ocurrido_en": antiguo,
        },
    )
    assert res.status_code == 422


def test_producir_en_orden_completada_permitida(db_session, tenant, user):
    """Orden completed permite sobreproducción (fin de bobina, decisión de Jorge)."""
    from app.services.production import record_production

    _, _, order, line = _setup(db_session, tenant, user)
    order.estado = "completed"
    db_session.commit()

    # No debe lanzar ValueError; debe registrar la producción
    resp = record_production(
        db_session,
        tenant.id,
        user.id,
        order_id=order.id,
        line_id=line.id,
        incremental_quantity=1,
    )
    assert resp["success"] is True
    assert resp["incremental_quantity"] == 1


def test_producir_en_orden_draft_permitida(db_session, tenant, user):
    """Orden draft permite iniciar producción (cambio R1: solo cancelled se rechaza)."""
    from app.services.production import record_production

    _, _, order, line = _setup(db_session, tenant, user)
    order.estado = "draft"
    db_session.commit()

    resp = record_production(
        db_session,
        tenant.id,
        user.id,
        order_id=order.id,
        line_id=line.id,
        incremental_quantity=1,
    )
    assert resp["success"] is True
    assert resp["incremental_quantity"] == 1


def test_estado_in_progress_no_existe_en_ordenes(db_session, tenant, user):
    """El modelo Order no tiene estado 'in_progress' (es de línea); validación no lo usa."""
    from app.models.order import ESTADOS_ORDEN

    assert "in_progress" not in ESTADOS_ORDEN
    assert ESTADOS_ORDEN == ("draft", "active", "completed", "cancelled")


def test_ocurrido_en_llega_a_production_logs(db_session, tenant, user):
    """La hora de la tablet queda en el timestamp del evento de trazabilidad."""
    from sqlalchemy import select

    from app.models import ProductionLog
    from app.services.production import record_production

    _, _, order, line = _setup(db_session, tenant, user)
    hace_una_hora = datetime.now(UTC) - timedelta(hours=1)

    record_production(
        db_session,
        tenant.id,
        user.id,
        order_id=order.id,
        line_id=line.id,
        incremental_quantity=3,
        ocurrido_en=hace_una_hora,
    )

    log = db_session.scalar(
        select(ProductionLog).where(
            ProductionLog.order_id == order.id, ProductionLog.action == "produce"
        )
    )
    assert log is not None
    ts = log.timestamp if log.timestamp.tzinfo else log.timestamp.replace(tzinfo=UTC)
    assert abs((ts - hace_una_hora).total_seconds()) < 2


def test_respuesta_duplicada_via_router_lleva_duplicate_true(db_session, tenant, user, client):
    """Vía HTTP: la segunda llamada con el mismo id devuelve duplicate true."""
    _, _, order, line = _setup(db_session, tenant, user)
    client.headers.update(auth_headers(db_session, tenant))

    body = {
        "order_id": str(order.id),
        "line_id": str(line.id),
        "incremental_quantity": 4,
        "client_request_id": str(uuid.uuid4()),
    }
    r1 = client.post("/api/v1/production/record", json=body)
    assert r1.status_code == 200
    assert r1.json().get("duplicate") is not True

    r2 = client.post("/api/v1/production/record", json=body)
    assert r2.status_code == 200
    assert r2.json()["duplicate"] is True
    assert r2.json()["produced_quantity"] == r1.json()["produced_quantity"]
