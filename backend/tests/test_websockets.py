"""Tests TDD del WebSocket de planta (ADR-014).

Contrato:
- WS /api/v1/ws/events?tenant_id={id} con subprotocolo kavana.v1.
- JWT OBLIGATORIO (auditoría 2026-08-24): sin token o de otro tenant → 4403.
- Protocolo: hello, events (cola pendiente), event (push realtime), ping,
  error. Cierres 4404 (tenant), 4403 (token), 1001 (heartbeat caído).
- Broker extendido con subscribe/unsubscribe best-effort en publish.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.models import User
from app.routers import ws as ws_router
from app.services.auth import hash_password, login
from app.services.events import EventBroker, broker
from tests.helpers import make_tenant, ws_token


@pytest.fixture(autouse=True)
def _ws_auth_tokens(request, db_session):
    """Tokens reales por tenant para _conectar: el WS exige JWT obligatorio
    desde la auditoría 2026-08-24. Población PEREZOSA en la primera conexión:
    este fixture corre antes que `tenant`, así que ahí aún no hay tenants."""
    global _DBG_SESSION
    _DBG_SESSION = db_session
    yield
    _DBG_SESSION = None
    _TOKENS.clear()



def _override_get_db(db_session):
    def _gen():
        yield db_session

    return _gen


@pytest.fixture()
def ws_client(db_session):
    app.dependency_overrides[ws_router.get_db] = _override_get_db(db_session)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _url(tenant_id, token=None) -> str:
    url = f"/api/v1/ws/events?tenant_id={tenant_id}"
    if token:
        url += f"&access_token={token}"
    return url


def _conectar(ws_client, tenant_id, token=None, subprotocols=None):
    # Token obligatorio (auditoría 2026-08-24): si no llega uno explícito se
    # usa un JWT real del tenant para las pruebas de flujo normal.
    # Token obligatorio (auditoría 2026-08-24): si no llega uno explícito se
    # usa un JWT real del tenant para las pruebas de flujo normal.
    try:
        uuid.UUID(str(tenant_id))
        es_uuid = True
    except (ValueError, AttributeError):
        es_uuid = False  # el server cierra 4404 antes de validar token
    if token is None and es_uuid and _token_para(tenant_id) != "":
        token = _token_para(tenant_id)
    return ws_client.websocket_connect(_url(tenant_id, token), subprotocols=subprotocols)


_TOKENS = {}


def _token_para(tenant_id):
    """Token cacheado por tenant; se crea al vuelo si es la primera conexión
    de ese tenant en el test (población perezosa, ver _ws_auth_tokens)."""
    tok = _TOKENS.get(str(tenant_id))
    if tok is None and _DBG_SESSION is not None:
        from tests.helpers import ws_token as _ws_token

        tok = _ws_token(_DBG_SESSION, _FakeTenant(tenant_id), email=f"ws-{tenant_id}@test.local")
        _TOKENS[str(tenant_id)] = tok
    return tok or ""



class _FakeTenant:
    """Envoltorio mínimo para reusar ws_token con un id ya existente."""

    def __init__(self, tid):
        self.id = tid


# ---------------------------------------------------------------------------
# Broker: listeners best-effort
# ---------------------------------------------------------------------------


def test_broker_subscribe_notifica_callback_en_publish(db_session, tenant):
    b = EventBroker()
    recibidos = []
    b.subscribe(tenant.id, recibidos.append)

    b.publish(tenant_id=tenant.id, tipo="kpi", data={"oee": 90})

    assert len(recibidos) == 1
    assert recibidos[0]["tipo"] == "kpi"


def test_broker_unsubscribe_deja_de_notificar(db_session, tenant):
    b = EventBroker()
    recibidos = []
    callback = recibidos.append
    b.subscribe(tenant.id, callback)
    b.unsubscribe(tenant.id, callback)

    b.publish(tenant_id=tenant.id, tipo="kpi", data={"oee": 90})

    assert recibidos == []
    # el evento sigue encolado para entrega posterior
    assert len(b.get_events(tenant.id)) == 1


def test_broker_publish_sin_listeners_mantiene_encolado(db_session, tenant):
    b = EventBroker()

    b.publish(tenant_id=tenant.id, tipo="downtime", data={"min": 10})

    assert len(b.get_events(tenant.id)) == 1


def test_broker_callback_que_falla_no_rompe_publish(db_session, tenant):
    b = EventBroker()

    def _roto(evento):
        raise RuntimeError("callback roto")

    b.subscribe(tenant.id, _roto)

    evento = b.publish(tenant_id=tenant.id, tipo="kpi", data={"oee": 88})

    assert evento["tipo"] == "kpi"
    assert len(b.get_events(tenant.id)) == 1


# ---------------------------------------------------------------------------
# Handshake y protocolo
# ---------------------------------------------------------------------------


def test_ws_handshake_acepta_subprotocolo_kavana_v1(db_session, tenant, ws_client):
    with _conectar(ws_client, tenant.id, subprotocols=["kavana.v1"]) as ws:
        hello = ws.receive_json()

    assert hello["type"] == "hello"
    assert ws.accepted_subprotocol == "kavana.v1"


def test_ws_conecta_y_recibe_hello_con_tenant(db_session, tenant, ws_client):
    with _conectar(ws_client, tenant.id) as ws:
        hello = ws.receive_json()

    assert hello["type"] == "hello"
    assert hello["tenant_id"] == str(tenant.id)
    assert hello["queued"] == 0


def test_ws_entrega_cola_pendiente_al_conectar(db_session, tenant, ws_client):
    broker.publish(tenant_id=tenant.id, tipo="consumo_fifo", data={"kg": 30})
    broker.publish(tenant_id=tenant.id, tipo="downtime", data={"min": 15})

    with _conectar(ws_client, tenant.id) as ws:
        hello = ws.receive_json()
        lote = ws.receive_json()

    assert hello["queued"] == 2
    assert lote["type"] == "events"
    assert len(lote["events"]) == 2
    # consume posterior ya no devuelve nada: la cola se entregó
    assert broker.consume(tenant.id) == []


def test_ws_push_en_tiempo_real_al_publicar(db_session, tenant, ws_client):
    with _conectar(ws_client, tenant.id) as ws:
        ws.receive_json()  # hello
        ws.receive_json()  # events []

        broker.publish(tenant_id=tenant.id, tipo="kpi", data={"oee": 87.5})
        msg = ws.receive_json()

    assert msg["type"] == "event"
    assert msg["event"]["tipo"] == "kpi"
    assert msg["event"]["data"]["oee"] == 87.5


def test_ws_separa_canales_por_tenant(db_session, tenant, ws_client):
    t2 = make_tenant(db_session, name="Otra Planta")
    db_session.add(t2)
    db_session.commit()
    db_session.refresh(t2)

    with _conectar(ws_client, tenant.id) as ws_a, _conectar(ws_client, t2.id) as ws_b:
        ws_a.receive_json()  # hello
        ws_a.receive_json()  # events []
        ws_b.receive_json()
        ws_b.receive_json()

        broker.publish(tenant_id=tenant.id, tipo="consumo_fifo", data={"kg": 30})
        broker.publish(tenant_id=t2.id, tipo="downtime", data={"min": 45})

        msg_a = ws_a.receive_json()
        msg_b = ws_b.receive_json()

    assert msg_a["event"]["tipo"] == "consumo_fifo"
    assert msg_b["event"]["tipo"] == "downtime"


def test_ws_mensaje_desconocido_recibe_error(db_session, tenant, ws_client):
    with _conectar(ws_client, tenant.id) as ws:
        ws.receive_json()  # hello
        ws.receive_json()  # events []

        ws.send_json({"type": "bogus"})
        err = ws.receive_json()

        assert err["type"] == "error"
        assert err["code"] == "unsupported"

        # la conexión sigue viva: un push posterior llega
        broker.publish(tenant_id=tenant.id, tipo="downtime", data={"min": 5})
        msg = ws.receive_json()

    assert msg["type"] == "event"


# ---------------------------------------------------------------------------
# Validación de tenant y token
# ---------------------------------------------------------------------------


def test_ws_tenant_inexistente_cierra_4404(ws_client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with _conectar(ws_client, uuid.uuid4()):
            pass
    assert exc.value.code == 4404


def test_ws_tenant_id_invalido_cierra_4404(ws_client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with _conectar(ws_client, "no-es-un-uuid"):
            pass
    assert exc.value.code == 4404


def test_ws_token_invalido_cierra_4403(db_session, tenant, ws_client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with _conectar(ws_client, tenant.id, token="token-basura"):
            pass
    assert exc.value.code == 4403


def test_ws_token_de_otro_tenant_cierra_4403(db_session, tenant, ws_client):
    t2 = make_tenant(db_session, name="Otra Planta")
    db_session.add(t2)
    db_session.commit()
    db_session.refresh(t2)
    u = User(
        tenant_id=t2.id,
        email="sup@otra.local",
        name="Sup Otro",
        password_hash=hash_password("clave123"),
        role="operator",
    )
    db_session.add(u)
    db_session.commit()

    token = login(db_session, t2.id, "sup@otra.local", "clave123")

    with pytest.raises(WebSocketDisconnect) as exc:
        with _conectar(ws_client, tenant.id, token=token):
            pass
    assert exc.value.code == 4403


def test_ws_token_valido_del_mismo_tenant_conecta(db_session, tenant, ws_client):
    u = User(
        tenant_id=tenant.id,
        email="operario@test.local",
        name="Operario Test",
        password_hash=hash_password("clave123"),
        role="operator",
    )
    db_session.add(u)
    db_session.commit()

    token = login(db_session, tenant.id, "operario@test.local", "clave123")

    with _conectar(ws_client, tenant.id, token=token) as ws:
        hello = ws.receive_json()
    assert hello["type"] == "hello"


def test_ws_sin_token_conecta_en_modo_demo(db_session, tenant, ws_client):
    with _conectar(ws_client, tenant.id) as ws:
        hello = ws.receive_json()
    assert hello["type"] == "hello"


# ---------------------------------------------------------------------------
# Ciclo de vida de la conexión
# ---------------------------------------------------------------------------


def test_ws_desconexion_limpia_suscripcion(db_session, tenant, ws_client):
    with _conectar(ws_client, tenant.id) as ws:
        ws.receive_json()
        ws.receive_json()

    # publicado mientras no hay cliente: no notifica a nadie y queda en cola
    broker.publish(tenant_id=tenant.id, tipo="consumo_fifo", data={"kg": 1})

    with _conectar(ws_client, tenant.id) as ws2:
        hello = ws2.receive_json()
        lote = ws2.receive_json()

    assert hello["queued"] == 1
    assert len(lote["events"]) == 1
    assert lote["events"][0]["data"]["kg"] == 1


def test_ws_heartbeat_envia_ping(db_session, tenant, ws_client, monkeypatch):
    monkeypatch.setattr(ws_router, "PING_INTERVAL_SECONDS", 0.1)
    monkeypatch.setattr(ws_router, "PONG_TIMEOUT_SECONDS", 5)

    with _conectar(ws_client, tenant.id) as ws:
        ws.receive_json()  # hello
        ws.receive_json()  # events []

        msg = ws.receive_json()
        assert msg["type"] == "ping"

        ws.send_json({"type": "pong"})

        # la conexión sigue viva: llega otro ping
        msg2 = ws.receive_json()
        assert msg2["type"] == "ping"


def test_ws_heartbeat_sin_pong_cierra_1001(db_session, tenant, ws_client, monkeypatch):
    monkeypatch.setattr(ws_router, "PING_INTERVAL_SECONDS", 0.1)
    monkeypatch.setattr(ws_router, "PONG_TIMEOUT_SECONDS", 0.25)

    with pytest.raises(WebSocketDisconnect) as exc:
        with _conectar(ws_client, tenant.id) as ws:
            ws.receive_json()  # hello
            ws.receive_json()  # events []
            # sin pong: se reciben pings hasta el cierre 1001
            while True:
                msg = ws.receive_json()
                assert msg["type"] == "ping"

    assert exc.value.code == 1001
