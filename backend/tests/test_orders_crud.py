"""Tests TDD del CRUD de órdenes y su máquina de estados (Fase A1).

Puerta al ciclo completo de la demo: crear un trabajo desde la UI, lanzarlo,
completarlo o descartarlo. Referencia de alcance: kavana-manufacturing
(POST /orders, PUT, DELETE, /orders/:id/transition).
"""

from datetime import UTC, datetime, timedelta

from app.main import app
from app.models import ManufacturingModel, Workstation
from app.routers import orders as orders_router
from tests.helpers import authed_client_for, make_tenant, make_user


def _override_get_db(db_session):
    def _gen():
        yield db_session

    return _gen


def _client(db_session, tenant, role="supervisor"):
    user = make_user(db_session, tenant, email=f"{role}-orders@test.local", role=role)
    app.dependency_overrides[orders_router.get_db] = _override_get_db(db_session)
    return authed_client_for(db_session, user), user


def _workstation(db_session, tenant, code="LINEA-1"):
    ws = Workstation(
        tenant_id=tenant.id,
        code=code,
        name=f"Puesto {code}",
        color="#3498db",
        hourly_cost=45,
        registration_method="quantity",
        is_active=True,
    )
    db_session.add(ws)
    db_session.commit()
    db_session.refresh(ws)
    return ws


def _payload(ws_code="LINEA-1", **extra):
    body = {
        "cliente": "Ferreteria Norte S.L.",
        "fecha_entrega": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        "notas": "Pedido de prueba",
        "lines": [
            {
                "workstation_id": ws_code,
                "total_quantity": 50,
                "meters_per_piece": 2.5,
            }
        ],
    }
    body.update(extra)
    return body


def test_supervisor_crea_orden_con_linea(db_session, tenant):
    _workstation(db_session, tenant)
    client, _ = _client(db_session, tenant)

    r = client.post("/api/v1/orders", json=_payload())

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["numero"].startswith("OP-")
    assert body["estado"] == "draft"
    assert body["cliente"] == "Ferreteria Norte S.L."
    assert len(body["lines"]) == 1
    assert body["lines"][0]["workstation_id"] == "LINEA-1"
    assert body["lines"][0]["estado"] == "pending"
    assert body["lines"][0]["total_quantity"] == 50


def test_numero_de_orden_autoincrementa(db_session, tenant):
    _workstation(db_session, tenant)
    client, _ = _client(db_session, tenant)

    r1 = client.post("/api/v1/orders", json=_payload())
    r2 = client.post("/api/v1/orders", json=_payload())

    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["numero"] != r2.json()["numero"]


def test_crear_directamente_activa(db_session, tenant):
    _workstation(db_session, tenant)
    client, _ = _client(db_session, tenant)

    r = client.post("/api/v1/orders", json=_payload(estado_inicial="active"))

    assert r.status_code == 201, r.text
    assert r.json()["estado"] == "active"


def test_crear_con_modelo_y_producto_declarados(db_session, tenant):
    from app.models import Product

    _workstation(db_session, tenant)
    modelo = ManufacturingModel(tenant_id=tenant.id, code="MONTANTE-P50", name="Montante")
    producto = Product(tenant_id=tenant.id, code="EST-PORTICO", name="Portico")
    db_session.add_all([modelo, producto])
    db_session.commit()

    client, _ = _client(db_session, tenant)
    payload = _payload(lines=[{
        "workstation_id": "LINEA-1",
        "total_quantity": 40,
        "modelo_id": str(modelo.id),
        "product_id": str(producto.id),
    }])

    r = client.post("/api/v1/orders", json=payload)

    assert r.status_code == 201, r.text
    linea = r.json()["lines"][0]
    assert linea["modelo_id"] == str(modelo.id)
    assert linea["product_id"] == str(producto.id)


def test_crear_rechaza_workstation_inexistente(db_session, tenant):
    client, _ = _client(db_session, tenant)

    r = client.post("/api/v1/orders", json=_payload(ws_code="NO-EXISTE"))

    assert r.status_code == 400, r.text
    assert "NO-EXISTE" in r.json()["detail"]


def test_crear_rechaza_modelo_de_otro_tenant(db_session, tenant):
    _workstation(db_session, tenant)
    otro = make_tenant(db_session, name="Otro")
    ajeno = ManufacturingModel(tenant_id=otro.id, code="AJENO", name="Ajeno")
    db_session.add(ajeno)
    db_session.commit()

    client, _ = _client(db_session, tenant)
    payload = _payload(lines=[{
        "workstation_id": "LINEA-1",
        "total_quantity": 10,
        "modelo_id": str(ajeno.id),
    }])

    r = client.post("/api/v1/orders", json=payload)

    assert r.status_code == 400, r.text


def test_crear_sin_lineas_rechazado(db_session, tenant):
    _workstation(db_session, tenant)
    client, _ = _client(db_session, tenant)

    r = client.post("/api/v1/orders", json={**_payload(), "lines": []})

    assert r.status_code == 422, r.text


def test_operario_no_puede_crear_ordenes(db_session, tenant):
    _workstation(db_session, tenant)
    client, _ = _client(db_session, tenant, role="operator")

    r = client.post("/api/v1/orders", json=_payload())

    assert r.status_code == 403, r.text


def test_transicion_draft_a_active(db_session, tenant):
    _workstation(db_session, tenant)
    client, _ = _client(db_session, tenant)
    orden = client.post("/api/v1/orders", json=_payload()).json()

    r = client.post(f"/api/v1/orders/{orden['id']}/transition", json={"to": "active"})

    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "active"


def test_transicion_a_completed_cierra_lineas(db_session, tenant):
    _workstation(db_session, tenant)
    client, _ = _client(db_session, tenant)
    orden = client.post("/api/v1/orders", json=_payload()).json()
    client.post(f"/api/v1/orders/{orden['id']}/transition", json={"to": "active"})

    r = client.post(f"/api/v1/orders/{orden['id']}/transition", json={"to": "completed"})

    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "completed"
    detalle = client.get(f"/api/v1/orders/{orden['id']}").json()
    assert all(ln["estado"] == "completed" for ln in detalle["lines"])


def test_transicion_ilegal_devuelve_409(db_session, tenant):
    _workstation(db_session, tenant)
    client, _ = _client(db_session, tenant)
    orden = client.post("/api/v1/orders", json=_payload()).json()
    client.post(f"/api/v1/orders/{orden['id']}/transition", json={"to": "active"})
    client.post(f"/api/v1/orders/{orden['id']}/transition", json={"to": "completed"})

    r = client.post(f"/api/v1/orders/{orden['id']}/transition", json={"to": "active"})

    assert r.status_code == 409, r.text


def test_transicion_cancelar_desde_active(db_session, tenant):
    _workstation(db_session, tenant)
    client, _ = _client(db_session, tenant)
    orden = client.post("/api/v1/orders", json=_payload(estado_inicial="active")).json()

    r = client.post(f"/api/v1/orders/{orden['id']}/transition", json={"to": "cancelled"})

    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "cancelled"


def test_transicion_destino_invalido_400(db_session, tenant):
    _workstation(db_session, tenant)
    client, _ = _client(db_session, tenant)
    orden = client.post("/api/v1/orders", json=_payload()).json()

    r = client.post(f"/api/v1/orders/{orden['id']}/transition", json={"to": "borrador"})

    assert r.status_code == 400, r.text


def test_editar_cabecera_de_orden(db_session, tenant):
    _workstation(db_session, tenant)
    client, _ = _client(db_session, tenant)
    orden = client.post("/api/v1/orders", json=_payload()).json()

    r = client.put(
        f"/api/v1/orders/{orden['id']}",
        json={"cliente": "Almacenes Duero S.A.", "notas": "Reprogramada"},
    )

    assert r.status_code == 200, r.text
    assert r.json()["cliente"] == "Almacenes Duero S.A."
    assert r.json()["notas"] == "Reprogramada"


def test_eliminar_orden_draft(db_session, tenant):
    _workstation(db_session, tenant)
    client, _ = _client(db_session, tenant)
    orden = client.post("/api/v1/orders", json=_payload()).json()

    r = client.delete(f"/api/v1/orders/{orden['id']}")

    assert r.status_code == 204, r.text
    assert client.get(f"/api/v1/orders/{orden['id']}").status_code == 404


def test_eliminar_orden_no_draft_rechazado(db_session, tenant):
    _workstation(db_session, tenant)
    client, _ = _client(db_session, tenant)
    orden = client.post("/api/v1/orders", json=_payload(estado_inicial="active")).json()

    r = client.delete(f"/api/v1/orders/{orden['id']}")

    assert r.status_code == 409, r.text
