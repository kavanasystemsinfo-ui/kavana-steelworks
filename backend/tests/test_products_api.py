"""Tests TDD de la API del catálogo de productos y su BOM (Fase A2).

Puerta para que la UI admin gestione el catálogo (crear producto, definir su
lista de materiales y piezas) y para que el form de órdenes del supervisor
pueda referenciar productos existentes.
"""

from decimal import Decimal

from app.main import app
from app.models import ManufacturingModel, Order, OrderLine, Product, ProductComponent
from app.routers import products as products_router
from tests.helpers import authed_client_for, make_material, make_tenant, make_user


def _override_get_db(db_session):
    def _gen():
        yield db_session

    return _gen


def _client(db_session, tenant, role="admin"):
    user = make_user(db_session, tenant, email=f"{role}-products@test.local", role=role)
    app.dependency_overrides[products_router.get_db] = _override_get_db(db_session)
    return authed_client_for(db_session, user), user


def _workstation(db_session, tenant, code="LINEA-1"):
    from app.models import Workstation

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


def _modelo(db_session, tenant, code="MONTANTE-P50"):
    m = ManufacturingModel(tenant_id=tenant.id, code=code, name=f"Pieza {code}")
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    return m


def test_get_lista_con_componentes(db_session, tenant):
    producto = Product(tenant_id=tenant.id, code="EST-PORTICO", name="Portico P50")
    modelo = _modelo(db_session, tenant)
    mat = make_material(db_session, tenant, code="TORN-08")
    db_session.add(producto)
    db_session.flush()
    producto.components.append(
        ProductComponent(
            manufacturing_model_id=modelo.id, quantity=Decimal("2"), unit="uds", position=1
        )
    )
    producto.components.append(
        ProductComponent(material_id=mat.id, quantity=Decimal("4"), unit="uds", position=2)
    )
    db_session.commit()

    client, _ = _client(db_session, tenant, role="supervisor")

    r = client.get("/api/v1/products")

    assert r.status_code == 200, r.text
    item = next(p for p in r.json() if p["code"] == "EST-PORTICO")
    assert item["name"] == "Portico P50"
    assert len(item["components"]) == 2
    refs = {(c["manufacturing_model_id"] is not None, c["material_id"] is not None)
            for c in item["components"]}
    assert refs == {(True, False), (False, True)}


def test_operario_no_ve_catalogo(db_session, tenant):
    client, _ = _client(db_session, tenant, role="operator")

    r = client.get("/api/v1/products")

    assert r.status_code == 403, r.text


def test_post_crea_producto_con_bom(db_session, tenant):
    modelo = _modelo(db_session, tenant)
    mat = make_material(db_session, tenant, code="MALLA-01")
    client, _ = _client(db_session, tenant)

    r = client.post(
        "/api/v1/products",
        json={
            "code": "EST-2X3",
            "name": "Estanteria 2x3",
            "description": "Dos vanos",
            "components": [
                {"manufacturing_model_id": str(modelo.id), "quantity": 4, "unit": "uds"},
                {"material_id": str(mat.id), "quantity": 1, "unit": "kgs"},
            ],
        },
    )

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["code"] == "EST-2X3"
    assert body["is_active"] is True
    assert len(body["components"]) == 2
    assert body["components"][0]["position"] in (1, 2)


def test_post_code_duplicado_409(db_session, tenant):
    client, _ = _client(db_session, tenant)
    payload = {"code": "EST-DUP", "name": "Uno"}
    assert client.post("/api/v1/products", json=payload).status_code == 201

    r = client.post("/api/v1/products", json={**payload, "name": "Otro"})

    assert r.status_code == 409, r.text


def test_post_componente_con_ambas_referencias_400(db_session, tenant):
    modelo = _modelo(db_session, tenant)
    mat = make_material(db_session, tenant, code="AMBOS-01")
    client, _ = _client(db_session, tenant)

    r = client.post(
        "/api/v1/products",
        json={
            "code": "EST-AMBOS",
            "name": "Invalido",
            "components": [
                {
                    "manufacturing_model_id": str(modelo.id),
                    "material_id": str(mat.id),
                    "quantity": 1,
                    "unit": "uds",
                }
            ],
        },
    )

    assert r.status_code == 400, r.text


def test_post_componente_sin_referencias_400(db_session, tenant):
    client, _ = _client(db_session, tenant)

    r = client.post(
        "/api/v1/products",
        json={
            "code": "EST-VACIO",
            "name": "Invalido",
            "components": [{"quantity": 1, "unit": "uds"}],
        },
    )

    assert r.status_code == 400, r.text


def test_post_modelo_de_otro_tenant_400(db_session, tenant):
    otro = make_tenant(db_session, name="Otro")
    ajeno = _modelo(db_session, otro, code="AJENO-PIEZA")
    client, _ = _client(db_session, tenant)

    r = client.post(
        "/api/v1/products",
        json={
            "code": "EST-AJENA",
            "name": "No valida",
            "components": [{"manufacturing_model_id": str(ajeno.id), "quantity": 1}],
        },
    )

    assert r.status_code == 400, r.text


def test_put_edita_y_reemplaza_componentes(db_session, tenant):
    modelo = _modelo(db_session, tenant)
    producto = Product(tenant_id=tenant.id, code="EST-VIEJO", name="Viejo")
    db_session.add(producto)
    db_session.commit()
    db_session.refresh(producto)

    client, _ = _client(db_session, tenant)
    r = client.put(
        f"/api/v1/products/{producto.id}",
        json={
            "name": "Renombrado",
            "components": [
                {"manufacturing_model_id": str(modelo.id), "quantity": 8, "unit": "uds"}
            ],
        },
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Renombrado"
    assert body["code"] == "EST-VIEJO"
    assert len(body["components"]) == 1
    assert body["components"][0]["quantity"] == 8


def test_delete_producto_libre(db_session, tenant):
    producto = Product(tenant_id=tenant.id, code="EST-LIBRE", name="Libre")
    db_session.add(producto)
    db_session.commit()

    client, _ = _client(db_session, tenant)

    r = client.delete(f"/api/v1/products/{producto.id}")

    assert r.status_code == 204, r.text
    assert client.get(f"/api/v1/products/{producto.id}").status_code == 404


def test_delete_producto_referenciado_409(db_session, tenant):
    _workstation(db_session, tenant)
    producto = Product(tenant_id=tenant.id, code="EST-USADA", name="Usada")
    db_session.add(producto)
    db_session.flush()
    orden = Order(tenant_id=tenant.id, numero="OP-USO-1", estado="active")
    db_session.add(orden)
    db_session.flush()
    db_session.add(
        OrderLine(
            order_id=orden.id,
            linea_numero=1,
            product_id=producto.id,
            workstation_id="LINEA-1",
            estado="pending",
            total_quantity=10,
        )
    )
    db_session.commit()

    client, _ = _client(db_session, tenant)

    r = client.delete(f"/api/v1/products/{producto.id}")

    assert r.status_code == 409, r.text


def test_get_por_id_con_componentes(db_session, tenant):
    producto = Product(tenant_id=tenant.id, code="EST-DETALLE", name="Detalle")
    db_session.add(producto)
    db_session.commit()

    client, _ = _client(db_session, tenant)

    r = client.get(f"/api/v1/products/{producto.id}")

    assert r.status_code == 200, r.text
    assert r.json()["code"] == "EST-DETALLE"
