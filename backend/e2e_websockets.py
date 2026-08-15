"""E2E de WebSockets de planta contra PostgreSQL real (ADR-014).

Cubre el contrato completo con BD real:
1. Conexión básica: hello con tenant y lote events vacío.
2. Entrega de cola pendiente: publicar antes de conectar, llega en events.
3. Push realtime: publicar con el cliente conectado, llega por event.
4. Fan-out: dos clientes del mismo tenant reciben ambos el evento.
5. Tenant aislado: el evento de otro tenant no se cuela en la cola.
6. Cierre 4404 para tenant inexistente.
7. Cierre 4403 para token de otro tenant.

Se ejecuta con: uv run python e2e_websockets.py
"""

import subprocess
import uuid

# 1) Password en runtime (nunca literal, quirk de secrets)
pw = (
    subprocess.check_output(
        "docker inspect kavana-busroad-pg-test --format "
        "'{{range .Config.Env}}{{println .}}{{end}}'",
        shell=True,
    )
    .decode()
    .split("POSTGRES_PASSWORD=")[1]
    .split("\n")[0]
)
import os  # noqa: E402

os.environ["STEELWORKS_DATABASE_URL"] = (
    f"postgresql+psycopg://kavana:{pw}@localhost:5436/kavana_steelworks_mig"
)

from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Tenant, User  # noqa: E402
from app.routers import ws as ws_router  # noqa: E402
from app.services.auth import hash_password, login  # noqa: E402
from app.services.events import broker  # noqa: E402

print("1/7 drop_all + create_all")
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)

db = SessionLocal()
try:
    print("2/7 seed tenant y usuario")
    tenant = Tenant(name="E2E WebSockets")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    user = User(
        tenant_id=tenant.id,
        email="e2e.ws@test.local",
        name="Operario WS",
        password_hash=hash_password("demo-pass"),
        role="operator",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    otro_tenant = Tenant(name="E2E Otro")
    db.add(otro_tenant)
    db.commit()
    db.refresh(otro_tenant)
    otro_user = User(
        tenant_id=otro_tenant.id,
        email="sup.otro@test.local",
        name="Sup Otro",
        password_hash=hash_password("clave123"),
        role="operator",
    )
    db.add(otro_user)
    db.commit()
    db.refresh(otro_user)

    token = login(db, tenant.id, user.email, "demo-pass")
    assert token is not None, "login falló en el E2E"
    token_otro = login(db, otro_tenant.id, otro_user.email, "clave123")
    assert token_otro is not None, "login del otro tenant falló"

    def _override_get_db():
        def _gen():
            yield db

        return _gen

    app.dependency_overrides[ws_router.get_db] = _override_get_db()
    client = TestClient(app)

    url = f"/api/v1/ws/events?tenant_id={tenant.id}"

    print("3/7 conexión básica: hello con lote vacío")
    with client.websocket_connect(url, subprotocols=["kavana.v1"]) as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello", hello
        assert hello["tenant_id"] == str(tenant.id), hello
        assert hello["queued"] == 0, hello
        lote = ws.receive_json()
        assert lote["type"] == "events" and lote["events"] == [], lote

    print("4/7 cola pendiente: publicar antes de conectar llega en events")
    broker.publish(tenant_id=tenant.id, tipo="kpi", data={"v": 1})
    with client.websocket_connect(url, subprotocols=["kavana.v1"]) as ws:
        hello = ws.receive_json()
        assert hello["queued"] == 1, hello
        lote = ws.receive_json()
        assert lote["type"] == "events" and len(lote["events"]) == 1, lote
        assert lote["events"][0]["tipo"] == "kpi", lote

    print("5/7 push realtime: publicar con cliente conectado llega por event")
    with client.websocket_connect(url, subprotocols=["kavana.v1"]) as ws:
        ws.receive_json()  # hello
        ws.receive_json()  # events vacío
        broker.publish(tenant_id=tenant.id, tipo="downtime", data={"min": 5})
        evento = ws.receive_json()
        assert evento["type"] == "event", evento
        assert evento["event"]["tipo"] == "downtime", evento

    print("6/7 fan-out: dos clientes del mismo tenant reciben ambos")
    with client.websocket_connect(url, subprotocols=["kavana.v1"]) as ws1:
        ws1.receive_json()
        ws1.receive_json()
        with client.websocket_connect(url, subprotocols=["kavana.v1"]) as ws2:
            ws2.receive_json()
            ws2.receive_json()
            broker.publish(tenant_id=tenant.id, tipo="consumo_fifo", data={"kg": 10})
            e1 = ws1.receive_json()
            e2 = ws2.receive_json()
            assert e1["type"] == "event" and e2["type"] == "event", (e1, e2)
            assert e1["event"]["id"] == e2["event"]["id"], (e1, e2)

    print("7/7 cierres: 4404 tenant inexistente, 4403 token de otro tenant")
    try:
        with client.websocket_connect(f"/api/v1/ws/events?tenant_id={uuid.uuid4()}"):
            pass
        raise AssertionError("debería haber cerrado 4404")
    except WebSocketDisconnect as exc:
        assert exc.code == 4404, exc.code
        print("    4404 OK (tenant inexistente)")

    url_token_otro = f"{url}&access_token={token_otro}"
    try:
        with client.websocket_connect(url_token_otro, subprotocols=["kavana.v1"]):
            pass
        raise AssertionError("debería haber cerrado 4403")
    except WebSocketDisconnect as exc:
        assert exc.code == 4403, exc.code
        print("    4403 OK (token de otro tenant)")

    # Aislamiento: el evento del otro tenant no entra en la cola de este
    print("   aislamiento: publicar en otro tenant no contamina la cola")
    with client.websocket_connect(url, subprotocols=["kavana.v1"]) as ws:
        ws.receive_json()  # hello
        lote = ws.receive_json()
        # El lote puede traer eventos previos (la cola del broker persiste
        # como memoria de reconexión por diseño, ADR-014): se descartan.
        broker.consume(tenant.id)  # vaciar cola del broker para el resto
        broker.publish(tenant_id=otro_tenant.id, tipo="kpi", data={"v": 9})
        # Sin sleep: un evento cruzado llegaría como event inesperado; el
        # siguiente mensaje del cliente de tenant A es el push de abajo.
        broker.publish(tenant_id=tenant.id, tipo="kpi", data={"v": 10})
        evento = ws.receive_json()
        assert evento["type"] == "event", evento
        assert evento["event"]["data"] == {"v": 10}, evento
        print("    aislamiento OK (solo llega el evento del propio tenant)")

    print("\n✅ E2E WEBSOCKETS 7/7 PASADO")
finally:
    app.dependency_overrides.clear()
    db.close()
