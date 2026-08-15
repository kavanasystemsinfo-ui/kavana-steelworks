"""Tests de incidencias de planta (spec 04 §3.3): alta, listado y resolución.

Contrato portado de IncidenciaController.js del legacy:
- nace SIEMPRE en 'abierta' con historial inicial y operario como autor
- si hay una orden activa en la línea, se asocia como order_id
- update: estado -> push al historial; resolución financiera conserva los
  campos previos si no vienen en el request (resolucion_tipo, descripcion,
  tiempo_parada_min, coste) y marca responsable_id
- el OEE consume tiempo_parada_min como downtime (spec 04 regla 8 / spec 03)
"""

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.incidencia import Incidencia
from app.routers import incidencias as inc_router
from app.services.events import broker
from app.services.oee_kpis import calcular_oee
from tests.helpers import make_order, make_order_line


def _override_get_db(db_session):
    def _gen():
        yield db_session

    return _gen


def _crear(
    db_session,
    tenant,
    user,
    linea="LINEA-1",
    descripcion="Atasco en cizalla",
    tipo="maquina",
):
    app.dependency_overrides[inc_router.get_db] = _override_get_db(db_session)
    try:
        client = TestClient(app)
        return client.post(
            "/api/v1/incidencias",
            json={"linea_id": linea, "descripcion": descripcion, "tipo": tipo},
        )
    finally:
        app.dependency_overrides.clear()


def test_crear_incidencia_asocia_orden_activa_y_estado_inicial(db_session, tenant, user):
    orden = make_order(db_session, tenant, numero="OP-INC-001")
    make_order_line(db_session, orden, workstation="LINEA-1")

    r = _crear(db_session, tenant, user)
    assert r.status_code == 201, r.text
    body = r.json()["incidencia"]
    assert body["estado"] == "abierta"
    assert body["order_id"] == str(orden.id)
    assert body["puesto"] == "LINEA-1"
    assert body["operario"]["name"] == user.name

    inc = db_session.query(Incidencia).one()
    assert inc.operario_id == user.id
    assert len(inc.historial) == 1
    assert inc.historial[0].estado == "abierta"

    eventos = broker.get_events(tenant.id)
    assert any(e["tipo"] == "nueva_incidencia" for e in eventos)


def test_crear_incidencia_sin_orden_activa_deja_order_null(db_session, tenant, user):
    r = _crear(db_session, tenant, user, linea="LINEA-99")
    assert r.status_code == 201, r.text
    assert r.json()["incidencia"]["order_id"] is None


def test_crear_incidencia_422_sin_descripcion(db_session, tenant, user):
    app.dependency_overrides[inc_router.get_db] = _override_get_db(db_session)
    try:
        client = TestClient(app)
        r = client.post("/api/v1/incidencias", json={"linea_id": "LINEA-1"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 422


def test_listar_incidencias_orden_desc(db_session, tenant, user):
    from datetime import UTC, datetime, timedelta

    r1 = _crear(db_session, tenant, user, descripcion="Primera")
    primera = db_session.get(Incidencia, uuid.UUID(r1.json()["incidencia"]["id"]))
    primera.created_at = datetime.now(UTC) - timedelta(hours=1)
    _crear(db_session, tenant, user, descripcion="Segunda")
    db_session.commit()

    app.dependency_overrides[inc_router.get_db] = _override_get_db(db_session)
    try:
        client = TestClient(app)
        r = client.get("/api/v1/incidencias")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    incidencias = r.json()["incidencias"]
    assert len(incidencias) == 2
    assert incidencias[0]["descripcion"] == "Segunda"  # createdAt desc


def test_actualizar_estado_anade_historial(db_session, tenant, user):
    _crear(db_session, tenant, user)
    inc = db_session.query(Incidencia).one()

    app.dependency_overrides[inc_router.get_db] = _override_get_db(db_session)
    try:
        client = TestClient(app)
        r = client.patch(
            f"/api/v1/incidencias/{inc.id}",
            json={"estado": "en_revision", "comentario": "revisando"},
        )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    assert r.json()["incidencia"]["estado"] == "en_revision"
    inc = db_session.query(Incidencia).one()
    assert len(inc.historial) == 2
    assert inc.historial[-1].comentario == "revisando"


def test_actualizar_resolucion_financiera(db_session, tenant, user):
    _crear(db_session, tenant, user)
    inc = db_session.query(Incidencia).one()

    app.dependency_overrides[inc_router.get_db] = _override_get_db(db_session)
    try:
        client = TestClient(app)
        r = client.patch(
            f"/api/v1/incidencias/{inc.id}",
            json={
                "estado": "cerrada",
                "resolucion_tipo": "reparacion",
                "resolucion_descripcion": "Cambio de cuchilla",
                "tiempo_parada_min": 30,
                "coste": 120,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    inc = db_session.query(Incidencia).one()
    assert inc.estado == "cerrada"
    assert inc.resolucion_tipo == "reparacion"
    assert float(inc.tiempo_parada_min) == 30
    assert float(inc.coste) == 120
    assert inc.responsable_id == user.id


def test_actualizar_resolucion_conserva_campos_previos(db_session, tenant, user):
    _crear(db_session, tenant, user)
    inc = db_session.query(Incidencia).one()

    app.dependency_overrides[inc_router.get_db] = _override_get_db(db_session)
    try:
        client = TestClient(app)
        client.patch(
            f"/api/v1/incidencias/{inc.id}",
            json={"resolucion_tipo": "ajuste", "tiempo_parada_min": 15},
        )
        r = client.patch(
            f"/api/v1/incidencias/{inc.id}", json={"coste": 50}
        )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    inc = db_session.query(Incidencia).one()
    assert inc.resolucion_tipo == "ajuste"  # conservado
    assert float(inc.tiempo_parada_min) == 15  # conservado
    assert float(inc.coste) == 50


def test_actualizar_incidencia_404(db_session, tenant, user):
    app.dependency_overrides[inc_router.get_db] = _override_get_db(db_session)
    try:
        client = TestClient(app)
        r = client.patch(
            f"/api/v1/incidencias/{uuid.uuid4()}", json={"estado": "resuelta"}
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 404


def test_oee_resta_downtime_de_incidencias(db_session, tenant, user):
    orden = make_order(db_session, tenant, numero="OP-OEE-INC")
    linea = make_order_line(db_session, orden, workstation="LINEA-1")
    linea.real_time = Decimal("300")  # 300 min de sesión
    linea.total_quantity = Decimal("100")
    linea.produced_quantity = Decimal("100")
    db_session.commit()

    base = calcular_oee(db_session, tenant.id)["availability"]

    _crear(db_session, tenant, user)
    inc = db_session.query(Incidencia).one()
    inc.tiempo_parada_min = Decimal("120")
    db_session.commit()

    con_parada = calcular_oee(db_session, tenant.id)["availability"]
    assert con_parada < base
    # (300 min de sesión - 120 de parada) / turno de 480
    assert con_parada == pytest.approx(max(0, (300 - 120) / 480) * 100, abs=0.01)
    assert "total_downtime_min" in calcular_oee(db_session, tenant.id)["raw"]
