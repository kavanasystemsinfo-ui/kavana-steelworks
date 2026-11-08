"""Tests TDD para trazabilidad de bobinas (T-044, D-018).

Cubre:
- alta_manual deja origen, creada_por, alta_ubicacion, pendiente_verificacion y emite evento
- verificar: pone false con verificada_por/verificada_en; 403 operario; 404 otro tenant;
  400 recepcion; 400 doble verify
- find_coil por lote: 2 bobinas -> {"bobinas": [...]}, 1 -> ficha legacy, coil_id -> 1
- /stock-items/disponibles incluye origen, pendiente_verificacion, creada_por
- receive_coil recepción normal deja origen='recepcion'
"""

import uuid

from app.models import StockItem, User
from app.services.inventory import find_coil
from app.services.receiving import receive_coil
from tests.helpers import (
    auth_headers,
    authed_client_for,
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
)


def _cliente(db, user):
    from app.main import app
    from app.routers import auth as auth_router
    from app.routers import stock as stock_router

    def _gen():
        yield db

    app.dependency_overrides[stock_router.get_db] = _gen
    app.dependency_overrides[auth_router.get_db] = _gen
    return authed_client_for(db, user)


def test_alta_manual_emite_evento_y_campos(db_session, tenant, user):
    """Alta manual: origen='alta_manual', creada_por_user_id, alta_ubicacion,
    pendiente_verificacion=true, y evento emitido."""
    from app.services.events import broker

    # Limpiar cola de eventos del tenant
    broker._queues[str(tenant.id)].clear()

    material = make_material(db_session, tenant, code="FLEJE-ALTA")
    cliente = _cliente(db_session, user)

    r = cliente.post(
        "/api/v1/stock-items/alta-manual",
        json={
            "material_id": str(material.id),
            "peso_kg": 1200.0,
            "lote": "L-ALTA-001",
            "width_mm": 150,
            "thickness_mm": 2.0,
            "puesto": "LINEA-1",
        },
    )
    assert r.status_code == 200, r.text
    bobina = r.json()

    # Verificar campos en respuesta
    assert bobina["origen"] == "alta_manual"
    assert bobina["pendiente_verificacion"] is True
    assert bobina["creada_por"] == user.name
    assert bobina["coil_id"].startswith("MAN-")

    # Verificar en BD
    stock = db_session.get(StockItem, uuid.UUID(bobina["id"]))
    assert stock.origen == "alta_manual"
    assert stock.creada_por_user_id == user.id
    assert stock.alta_ubicacion == "LINEA-1"
    assert stock.pendiente_verificacion is True

    # Verificar evento emitido
    eventos = broker.get_events(tenant.id)
    assert len(eventos) == 1
    ev = eventos[0]
    assert ev["tipo"] == "alta_manual_bobina"
    assert ev["data"]["coil_id"] == bobina["coil_id"]
    assert ev["data"]["origen"] == "alta_manual"
    assert ev["data"]["creada_por_user_id"] == str(user.id)
    assert ev["data"]["creada_por_nombre"] == user.name
    assert ev["data"]["alta_ubicacion"] == "LINEA-1"
    assert ev["data"]["pendiente_verificacion"] is True


def test_verificar_bobina_evento_y_roles(db_session, tenant, user):
    """Verificar: pone pendiente_verificacion=false con verificada_por/verificada_en.
    403 operario; 404 otro tenant; 400 recepcion; 400 doble verify."""
    from app.services.events import broker

    # Crear bobina de alta_manual
    material = make_material(db_session, tenant, code="FLEJE-VER")
    bobina = receive_coil(
        db_session,
        tenant.id,
        user.id,
        material_id=material.id,
        lote="L-VER-001",
        coil_id="MAN-VER-001",
        peso=1000.0,
        width_mm=120,
        thickness_mm=1.5,
        coste_real=2.0,
        ubicacion="LINEA-1",
        origen="alta_manual",
        creada_por_user_id=user.id,
    )
    bobina.alta_ubicacion = "LINEA-1"
    bobina.pendiente_verificacion = True
    db_session.commit()
    db_session.refresh(bobina)

    # Limpiar cola
    broker._queues[str(tenant.id)].clear()

    # --- 403: operario no puede verificar ---
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers import auth as auth_router
    from app.routers import stock as stock_router

    def _gen():
        yield db_session

    app.dependency_overrides[stock_router.get_db] = _gen
    app.dependency_overrides[auth_router.get_db] = _gen

    client = TestClient(app)
    client.headers.update(auth_headers(db_session, tenant, role="operator", email="op@test.local"))

    r = client.post(f"/api/v1/stock-items/{bobina.id}/verificar", json={})
    assert r.status_code == 403, r.text

    # --- 404: otro tenant ---
    from tests.helpers import make_tenant
    from tests.helpers import make_user as make_user_helper

    tenant2 = make_tenant(db_session, name="Otro", slug=f"otro-{uuid.uuid4().hex[:8]}")
    email_admin2 = f"admin2-{uuid.uuid4().hex[:8]}@test.local"
    admin2 = make_user_helper(db_session, tenant2, email=email_admin2, role="admin")

    client2 = TestClient(app)
    client2.headers.update(auth_headers(db_session, tenant2, role="admin", email=admin2.email))

    url = f"/api/v1/stock-items/{bobina.id}/verificar"
    r = client2.post(url, json={})
    assert r.status_code == 404, r.text

    # --- 400: bobina de origen 'recepcion' ---
    bobina_recepcion = receive_coil(
        db_session,
        tenant.id,
        user.id,
        material_id=material.id,
        lote="L-REC-001",
        coil_id="REC-001",
        peso=500.0,
        width_mm=100,
        thickness_mm=1.0,
        coste_real=2.0,
        ubicacion="ALMACEN",
        origen="recepcion",
    )
    db_session.commit()

    client.headers.clear()
    client.headers.update(
        auth_headers(db_session, tenant, role="supervisor", email="sup@test.local")
    )
    r = client.post(f"/api/v1/stock-items/{bobina_recepcion.id}/verificar", json={})
    assert r.status_code == 400, r.text
    assert "alta manual" in r.json()["detail"].lower()

    # --- Verificación exitosa con supervisor ---
    broker._queues[str(tenant.id)].clear()

    # Crear supervisor si no existe
    from tests.helpers import make_user as make_user_helper

    supervisor = db_session.query(User).filter(
        User.tenant_id == tenant.id, User.role == "supervisor"
    ).first()
    if not supervisor:
        email_sup = f"supervisor-{uuid.uuid4().hex[:8]}@test.local"
        make_user_helper(db_session, tenant, email=email_sup, role="supervisor")
        supervisor = db_session.query(User).filter(
            User.tenant_id == tenant.id, User.role == "supervisor"
        ).first()

    client.headers.clear()
    headers = auth_headers(
        db_session, tenant, role="supervisor", email=supervisor.email
    )
    client.headers.update(headers)
    r = client.post(f"/api/v1/stock-items/{bobina.id}/verificar", json={})
    assert r.status_code == 200, r.text
    resp = r.json()
    assert resp["success"] is True
    assert "verificada_por" in resp
    assert "verificada_en" in resp

    # Verificar en BD
    db_session.refresh(bobina)
    assert bobina.pendiente_verificacion is False
    assert bobina.verificada_por_user_id is not None
    assert bobina.verificada_en is not None

    # Verificar evento
    eventos = broker.get_events(tenant.id)
    assert len(eventos) == 1
    ev = eventos[0]
    assert ev["tipo"] == "verificacion_alta_manual"
    assert ev["data"]["coil_id"] == bobina.coil_id
    assert ev["data"]["verificada_por_user_id"] is not None
    assert ev["data"]["verificada_por_nombre"] == resp["verificada_por"]

    # --- 400: verificar dos veces ---
    r = client.post(f"/api/v1/stock-items/{bobina.id}/verificar", json={})
    assert r.status_code == 400, r.text
    assert "ya está verificada" in r.json()["detail"].lower()


def test_find_coil_por_lote_formato(db_session, tenant, user):
    """find_coil por lote: 2 bobinas -> {'bobinas': [...]}, 1 -> ficha legacy, coil_id -> 1."""
    material = make_material(db_session, tenant, code="FLEJE-LOTE")

    # 2 bobinas mismo lote
    make_stock_item(
        db_session, tenant, material, cantidad=100.0, lote="LOTE-MULTI",
        coil_id="COIL-1", ancho=120, espesor=1.0
    )
    make_stock_item(
        db_session, tenant, material, cantidad=200.0, lote="LOTE-MULTI",
        coil_id="COIL-2", ancho=120, espesor=1.0
    )
    db_session.commit()

    # Por lote -> lista bajo clave "bobinas"
    resultado = find_coil(db_session, tenant.id, lote="LOTE-MULTI")
    assert isinstance(resultado, dict)
    assert "bobinas" in resultado
    assert len(resultado["bobinas"]) == 2
    coil_ids = {b["coil_id"] for b in resultado["bobinas"]}
    assert coil_ids == {"COIL-1", "COIL-2"}

    # 1 bobina solo -> formato legacy (dict directo, no {"bobinas": [...]})
    make_stock_item(
        db_session, tenant, material, cantidad=150.0, lote="LOTE-SOLO",
        coil_id="COIL-SOLO", ancho=100, espesor=0.5
    )
    db_session.commit()

    resultado = find_coil(db_session, tenant.id, lote="LOTE-SOLO")
    assert isinstance(resultado, dict)
    assert "bobinas" not in resultado
    assert resultado["coil_id"] == "COIL-SOLO"
    assert resultado["lote"] == "LOTE-SOLO"
    assert "origen" in resultado
    assert "pendiente_verificacion" in resultado
    assert "creada_por" in resultado

    # Por coil_id -> 1 bobina (formato legacy)
    resultado = find_coil(db_session, tenant.id, coil_id="COIL-1")
    assert isinstance(resultado, dict)
    assert "bobinas" not in resultado
    assert resultado["coil_id"] == "COIL-1"


def test_disponibles_incluye_nuevos_campos(db_session, tenant, user):
    """GET /stock-items/disponibles incluye origen, pendiente_verificacion, creada_por."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers import auth as auth_router
    from app.routers import stock as stock_router

    material = make_material(db_session, tenant, code="FLEJE-DISP")
    bobina = make_stock_item(
        db_session, tenant, material, cantidad=500.0, lote="L-DISP",
        coil_id="COIL-DISP", ancho=150, espesor=2.0, ubicacion="LINEA-1"
    )
    bobina.origen = "recepcion"
    bobina.creada_por_user_id = user.id
    bobina.pendiente_verificacion = False
    db_session.commit()

    order = make_order(db_session, tenant, numero="OP-DISP")
    line = make_order_line(
        db_session, order, workstation="LINEA-1", total_quantity=10.0, material=material
    )
    db_session.commit()

    def _gen():
        yield db_session

    app.dependency_overrides[stock_router.get_db] = _gen
    app.dependency_overrides[auth_router.get_db] = _gen

    client = TestClient(app)
    client.headers.update(auth_headers(db_session, tenant, role="operator", email="op@test.local"))

    r = client.get(f"/api/v1/stock-items/disponibles?line_id={line.id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) >= 1
    item = data[0]
    assert "origen" in item
    assert "pendiente_verificacion" in item
    assert "creada_por" in item
    assert item["origen"] == "recepcion"
    assert item["pendiente_verificacion"] is False
    assert item["creada_por"] == user.name


def test_receive_coil_recepcion_normal(db_session, tenant, user):
    """receive_coil recepción normal: origen='recepcion', evento recepcion_material."""
    from app.services.events import broker

    broker._queues[str(tenant.id)].clear()

    material = make_material(db_session, tenant, code="FLEJE-REC")

    bobina = receive_coil(
        db_session,
        tenant.id,
        user.id,
        material_id=material.id,
        lote="L-REC-NORMAL",
        coil_id="REC-NORMAL-1",
        peso=800.0,
        width_mm=200,
        thickness_mm=3.0,
        coste_real=2.5,
        ubicacion="ALMACEN",
        origen="recepcion",
    )

    assert bobina.origen == "recepcion"
    assert bobina.pendiente_verificacion is False
    assert bobina.creada_por_user_id == user.id  # por defecto user_id

    # Verificar evento recepcion_material (no alta_manual_bobina)
    eventos = broker.get_events(tenant.id)
    assert len(eventos) == 1
    ev = eventos[0]
    assert ev["tipo"] == "recepcion_material"
    assert ev["data"]["coil_id"] == "REC-NORMAL-1"
    assert "origen" not in ev["data"]  # el evento de recepción no lleva origen