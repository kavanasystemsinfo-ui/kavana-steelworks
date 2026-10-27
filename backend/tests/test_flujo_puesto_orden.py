"""Fase pulido de registro de órdenes (port del legacy kavanasystems).

Flujo del operario: seleccionar puesto -> cola de órdenes del puesto ->
preparación (vincular bobina) -> producción. Esto cubre los cimientos del
backend para ese flujo:

- GET /api/v1/admin/workstations legible para el rol operario (hoy 403).
- GET /api/v1/orders/available?workstation=CODE filtra por el puesto pedido
  (validado contra el tenant), sin romper el comportamiento actual por
  default_workstation_code.
- El error de stock insuficiente expresa kilos, no "unidades" (bug de UX
  reportado en la demo).
"""

from datetime import UTC, datetime

import pytest

from app.main import app
from app.routers import admin as admin_router
from app.routers import orders as orders_router
from tests.helpers import (
    authed_client_for,
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
    make_tenant,
    make_user,
)


def _override_get_db(router, db_session):
    def _gen():
        yield db_session

    return _gen


def _make_workstation(db, tenant, code, name=None, is_active=True):
    from app.models import Workstation

    ws = Workstation(
        tenant_id=tenant.id,
        code=code,
        name=name or f"Puesto {code}",
        color="#3498db",
        hourly_cost=45,
        registration_method="quantity",
        is_active=is_active,
    )
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


# ── GET /admin/workstations aislado por tenant ─────────────────────────────


def test_workstations_no_devuelve_puestos_de_otro_tenant(db_session, tenant):
    otro = make_tenant(db_session, name="Otro Tenant WS")
    _make_workstation(db_session, otro, "AJENA-1")
    _make_workstation(db_session, tenant, "PROPIA-1")
    operario = make_user(db_session, tenant, email="op-ws2@test.local", role="operator")

    app.dependency_overrides[admin_router.get_db] = _override_get_db(admin_router, db_session)
    try:
        client = authed_client_for(db_session, operario)
        r = client.get("/api/v1/admin/workstations")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    codes = [w["code"] for w in r.json()]
    assert "PROPIA-1" in codes
    assert "AJENA-1" not in codes


# ── GET /orders/available?workstation=CODE ─────────────────────────────────


def _operario_con_ordenes(db, tenant, email):
    _make_workstation(db, tenant, "LINEA-1")
    _make_workstation(db, tenant, "LINEA-9")
    o1 = make_order(db, tenant, numero="OP-PWS-1")
    make_order_line(db, o1, workstation="LINEA-1")
    o2 = make_order(db, tenant, numero="OP-PWS-2")
    make_order_line(db, o2, workstation="LINEA-9")
    operario = make_user(db, tenant, email=email, role="operator")
    operario.default_workstation_code = "LINEA-1"
    db.commit()
    db.refresh(operario)
    return operario


def test_available_con_workstation_filtra_por_ese_puesto(db_session, tenant):
    operario = _operario_con_ordenes(db_session, tenant, "op-pws1@test.local")

    app.dependency_overrides[orders_router.get_db] = _override_get_db(orders_router, db_session)
    try:
        client = authed_client_for(db_session, operario)
        r = client.get("/api/v1/orders/available?workstation=LINEA-9")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    numeros = [item["numero"] for item in r.json()]
    assert "OP-PWS-2" in numeros
    assert "OP-PWS-1" not in numeros


def test_available_sin_workstation_usa_default_del_usuario(db_session, tenant):
    operario = _operario_con_ordenes(db_session, tenant, "op-pws2@test.local")

    app.dependency_overrides[orders_router.get_db] = _override_get_db(orders_router, db_session)
    try:
        client = authed_client_for(db_session, operario)
        r = client.get("/api/v1/orders/available")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    numeros = [item["numero"] for item in r.json()]
    assert "OP-PWS-1" in numeros
    assert "OP-PWS-2" not in numeros


def test_available_con_workstation_inexistente_devuelve_400(db_session, tenant):
    operario = _operario_con_ordenes(db_session, tenant, "op-pws3@test.local")

    app.dependency_overrides[orders_router.get_db] = _override_get_db(orders_router, db_session)
    try:
        client = authed_client_for(db_session, operario)
        r = client.get("/api/v1/orders/available?workstation=NOEXISTE")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 400, r.text


def test_available_con_workstation_de_otro_tenant_devuelve_400(db_session, tenant):
    otro = make_tenant(db_session, name="Otro Tenant PWS")
    _make_workstation(db_session, otro, "AJENA-2")
    operario = make_user(db_session, tenant, email="op-pws4@test.local", role="operator")

    app.dependency_overrides[orders_router.get_db] = _override_get_db(orders_router, db_session)
    try:
        client = authed_client_for(db_session, operario)
        r = client.get("/api/v1/orders/available?workstation=AJENA-2")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 400, r.text


def test_available_con_workstation_valido_sin_ordenes_devuelve_vacio(db_session, tenant):
    _make_workstation(db_session, tenant, "LINEA-VACIA")
    operario = make_user(db_session, tenant, email="op-pws5@test.local", role="operator")

    app.dependency_overrides[orders_router.get_db] = _override_get_db(orders_router, db_session)
    try:
        client = authed_client_for(db_session, operario)
        r = client.get("/api/v1/orders/available?workstation=LINEA-VACIA")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    assert r.json() == []


# ── Error de stock insuficiente en kilos ───────────────────────────────────


def test_stock_insuficiente_expresa_kilos_no_unidades(db_session, tenant, user):
    material = make_material(db_session, tenant, cost=2.0)
    make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=10,
        lote="POCA-KG",
        fecha_entrada=datetime.now(UTC),
    )
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order)

    from app.services.inventory import consume_stock_fifo

    with pytest.raises(ValueError) as exc:
        consume_stock_fifo(
            db_session,
            tenant.id,
            user.id,
            material_id=material.id,
            cantidad_requerida=50,
            order_id=order.id,
            order_line_id=line.id,
        )

    mensaje = str(exc.value)
    assert "kg" in mensaje
    assert "unidades" not in mensaje
