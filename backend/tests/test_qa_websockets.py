"""Tests QA independientes (ingeniero QA) del WebSocket de planta (ADR-014).

Cubren casos que la suite original (test_websockets.py) no cubre:
fan-out a varios clientes del mismo tenant, orden sin duplicados con cola
pendiente, callback roto con cliente real conectado, desconexión brusca a
media conexión, orden de validación 4404/4403, token expirado/revocado,
timing real del cierre 1001, mensajes inválidos (JSON roto, frame binario)
y la ventana consume -> subscribe (evento perdido para la conexión actual).

Estos tests NO arreglan nada: documentan el comportamiento observado.
"""

import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from app.main import app
from app.models import User
from app.routers import ws as ws_router
from app.services import auth as auth_service
from app.services.auth import hash_password, login
from app.services.events import EventBroker, broker


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
    return ws_client.websocket_connect(_url(tenant_id, token), subprotocols=subprotocols)


def _espera_hasta(pred, timeout=2.0):
    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        if pred():
            return
        time.sleep(0.02)
    raise AssertionError(f"condición no alcanzada en {timeout} s")


def _crear_usuario(db_session, tenant, email, password="clave123"):
    u = User(
        tenant_id=tenant.id,
        email=email,
        name="QA User",
        password_hash=hash_password(password),
        role="operator",
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


# ---------------------------------------------------------------------------
# Contrato: ruta y fallback REST
# ---------------------------------------------------------------------------


def _todas_las_rutas(routes):
    for r in routes:
        if getattr(r, "routes", None):  # Router anidado
            yield from _todas_las_rutas(r.routes)
        elif hasattr(r, "original_router"):  # _IncludedRouter (FastAPI 0.141)
            yield from _todas_las_rutas(r.original_router.routes)
        elif hasattr(r, "path"):
            yield r.path


def test_qa_ruta_registrada_exacta():
    rutas = list(_todas_las_rutas(app.routes))
    assert "/api/v1/ws/events" in rutas


def test_qa_endpoint_rest_de_polling_sigue_funcionando(db_session, tenant, ws_client):
    broker.publish(tenant_id=tenant.id, tipo="consumo_fifo", data={"kg": 5})
    r = ws_client.get(f"/api/v1/events/{tenant.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["events"][0]["data"]["kg"] == 5


# ---------------------------------------------------------------------------
# Fan-out: varios clientes del mismo tenant
# ---------------------------------------------------------------------------


def test_qa_fanout_dos_clientes_mismo_tenant(db_session, tenant, ws_client):
    """El contrato pide fan-out a TODOS los suscriptores del tenant."""
    with _conectar(ws_client, tenant.id) as ws_a, _conectar(ws_client, tenant.id) as ws_b:
        ws_a.receive_json()  # hello
        ws_a.receive_json()  # events []
        ws_b.receive_json()
        ws_b.receive_json()

        broker.publish(tenant_id=tenant.id, tipo="consumo_fifo", data={"kg": 30})
        broker.publish(tenant_id=tenant.id, tipo="downtime", data={"min": 15})
        broker.publish(tenant_id=tenant.id, tipo="kpi", data={"oee": 90})

        recibidos_a = [ws_a.receive_json() for _ in range(3)]
        recibidos_b = [ws_b.receive_json() for _ in range(3)]

    tipos_a = [m["event"]["tipo"] for m in recibidos_a]
    tipos_b = [m["event"]["tipo"] for m in recibidos_b]
    assert tipos_a == ["consumo_fifo", "downtime", "kpi"]
    assert tipos_b == ["consumo_fifo", "downtime", "kpi"]
    ids_a = [m["event"]["id"] for m in recibidos_a]
    ids_b = [m["event"]["id"] for m in recibidos_b]
    assert ids_a == ids_b  # mismos eventos, sin duplicados por cliente


def test_qa_lote_inicial_y_push_sin_duplicados_por_cliente(db_session, tenant, ws_client):
    """Un cliente nuevo recibe el espejo de la cola; los conectados no lo
    reciben dos veces (push ya entregado)."""
    with _conectar(ws_client, tenant.id) as ws_a:
        ws_a.receive_json()  # hello
        ws_a.receive_json()  # events []

        broker.publish(tenant_id=tenant.id, tipo="consumo_fifo", data={"kg": 1})
        broker.publish(tenant_id=tenant.id, tipo="downtime", data={"min": 2})
        e1 = ws_a.receive_json()["event"]
        e2 = ws_a.receive_json()["event"]

        with _conectar(ws_client, tenant.id) as ws_b:
            hello_b = ws_b.receive_json()
            lote_b = ws_b.receive_json()
            assert hello_b["queued"] == 2
            assert [ev["id"] for ev in lote_b["events"]] == [e1["id"], e2["id"]]

            broker.publish(tenant_id=tenant.id, tipo="kpi", data={"oee": 77})
            e3_a = ws_a.receive_json()["event"]
            e3_b = ws_b.receive_json()["event"]

    assert e3_a["id"] == e3_b["id"]
    # A no recibió duplicados: solo e1, e2 por push y e3 por push
    assert len({e1["id"], e2["id"], e3_a["id"]}) == 3


def test_qa_un_cliente_caido_no_afecta_al_otro(db_session, tenant, ws_client):
    with _conectar(ws_client, tenant.id) as ws_a:
        ws_a.receive_json()
        ws_a.receive_json()
        with _conectar(ws_client, tenant.id) as ws_b:
            ws_b.receive_json()
            ws_b.receive_json()
            ws_b.close()  # B se va bruscamente
            broker.publish(tenant_id=tenant.id, tipo="kpi", data={"oee": 80})
            msg = ws_a.receive_json()
    assert msg["type"] == "event"
    assert msg["event"]["data"]["oee"] == 80


# ---------------------------------------------------------------------------
# Orden y duplicados
# ---------------------------------------------------------------------------


def test_qa_orden_fifo_lote_inicial(db_session, tenant, ws_client):
    broker.publish(tenant_id=tenant.id, tipo="consumo_fifo", data={"seq": 1})
    broker.publish(tenant_id=tenant.id, tipo="consumo_fifo", data={"seq": 2})
    broker.publish(tenant_id=tenant.id, tipo="consumo_fifo", data={"seq": 3})

    with _conectar(ws_client, tenant.id) as ws:
        hello = ws.receive_json()
        lote = ws.receive_json()

    assert hello["queued"] == 3
    assert [ev["data"]["seq"] for ev in lote["events"]] == [1, 2, 3]


def test_qa_rafaga_sin_perdidas_ni_duplicados(db_session, tenant, ws_client):
    with _conectar(ws_client, tenant.id) as ws:
        ws.receive_json()
        ws.receive_json()

        for i in range(5):
            broker.publish(tenant_id=tenant.id, tipo="consumo_fifo", data={"seq": i})
        recibidos = [ws.receive_json() for _ in range(5)]

    seqs = [m["event"]["data"]["seq"] for m in recibidos]
    ids = [m["event"]["id"] for m in recibidos]
    assert seqs == [0, 1, 2, 3, 4]  # FIFO
    assert len(set(ids)) == 5  # sin duplicados


# ---------------------------------------------------------------------------
# Robustez del broker con el cliente conectado
# ---------------------------------------------------------------------------


def test_qa_callback_roto_no_impide_el_push_al_cliente_ws(db_session, tenant, ws_client):
    """Best-effort integrado: un callback roto no tapa el push a un cliente
    real conectado en el mismo tenant."""

    def _roto(evento):
        raise RuntimeError("callback roto")

    broker.subscribe(tenant.id, _roto)
    try:
        with _conectar(ws_client, tenant.id) as ws:
            ws.receive_json()
            ws.receive_json()
            broker.publish(tenant_id=tenant.id, tipo="kpi", data={"oee": 91})
            msg = ws.receive_json()
        assert msg["type"] == "event"
        assert msg["event"]["data"]["oee"] == 91
    finally:
        broker.unsubscribe(tenant.id, _roto)


def test_qa_desconexion_brusca_a_media_conexion_limpia_sin_excepcion(
    db_session, tenant, ws_client
):
    """El cliente se va a media conexión (sin leer los eventos pendientes):
    la suscripción se limpia y el publish posterior no revienta."""
    with _conectar(ws_client, tenant.id) as ws:
        ws.receive_json()  # hello
        ws.receive_json()  # events []
        broker.publish(tenant_id=tenant.id, tipo="consumo_fifo", data={"kg": 1})
        broker.publish(tenant_id=tenant.id, tipo="consumo_fifo", data={"kg": 2})
        broker.publish(tenant_id=tenant.id, tipo="consumo_fifo", data={"kg": 3})
        ws.close()  # cierre brusco sin leer la ráfaga

    _espera_hasta(lambda: len(broker._listeners.get(str(tenant.id), ())) == 0)

    broker.publish(tenant_id=tenant.id, tipo="downtime", data={"min": 9})

    with _conectar(ws_client, tenant.id) as ws2:
        hello = ws2.receive_json()
        lote = ws2.receive_json()
    assert hello["queued"] == 4
    assert [ev["tipo"] for ev in lote["events"]] == [
        "consumo_fifo",
        "consumo_fifo",
        "consumo_fifo",
        "downtime",
    ]
    assert [ev["data"]["kg"] for ev in lote["events"][:3]] == [1, 2, 3]
    assert lote["events"][3]["data"]["min"] == 9


def test_qa_evento_publicado_en_ventana_consume_subscribe_no_llega(
    db_session, tenant, ws_client, monkeypatch
):
    """Ventana entre consume() y subscribe(): un evento publicado ahí no llega
    ni en el lote inicial ni como push; queda en la cola para la siguiente
    conexión. El ADR promete 'uno publicado después [de conectar], por event'."""
    real_subscribe = broker.subscribe
    publicado: dict = {}

    def subscribe_con_publish_previo(tenant_id, callback):
        publicado["evento"] = broker.publish(
            tenant_id=tenant_id, tipo="downtime", data={"min": 1}
        )
        real_subscribe(tenant_id, callback)

    monkeypatch.setattr(broker, "subscribe", subscribe_con_publish_previo)

    with _conectar(ws_client, tenant.id) as ws:
        hello = ws.receive_json()
        lote = ws.receive_json()

    assert hello["queued"] == 0
    assert lote["events"] == []
    # el evento quedó encolado, pero esta conexión no lo vio
    assert broker.get_events(tenant.id) == [publicado["evento"]]


# ---------------------------------------------------------------------------
# Validación de tenant y token
# ---------------------------------------------------------------------------


def test_qa_tenant_inexistente_con_token_valido_cierra_4404(db_session, tenant, ws_client):
    """Orden de validación del contrato: primero el tenant, luego el token.
    Un token válido no salva a un tenant que no existe."""
    _crear_usuario(db_session, tenant, "qa@ord.local")
    token = login(db_session, tenant.id, "qa@ord.local", "clave123")
    assert token

    with pytest.raises(WebSocketDisconnect) as exc:
        with _conectar(ws_client, uuid.uuid4(), token=token):
            pass
    assert exc.value.code == 4404


def test_qa_token_expirado_cierra_4403(db_session, tenant, ws_client):
    _crear_usuario(db_session, tenant, "qa@exp.local")
    settings = get_settings()
    payload = {
        "sub": str(uuid.uuid4()),
        "tenant_id": str(tenant.id),
        "role": "operator",
        "exp": datetime.now(UTC) - timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    with pytest.raises(WebSocketDisconnect) as exc:
        with _conectar(ws_client, tenant.id, token=token):
            pass
    assert exc.value.code == 4403


def test_qa_token_revocado_cierra_4403(db_session, tenant, ws_client):
    _crear_usuario(db_session, tenant, "qa@rev.local")
    token = login(db_session, tenant.id, "qa@rev.local", "clave123")
    auth_service.logout(db_session, token)

    with pytest.raises(WebSocketDisconnect) as exc:
        with _conectar(ws_client, tenant.id, token=token):
            pass
    assert exc.value.code == 4403


# ---------------------------------------------------------------------------
# Heartbeat y protocolo
# ---------------------------------------------------------------------------


def test_qa_heartbeat_cierra_1001_en_el_tercer_ciclo_sin_pong(
    db_session, tenant, ws_client, monkeypatch
):
    """Con 30 s/60 s reales el cierre cae en el 3er ciclo (~90 s), no en los
    60 s que documenta el ADR: la comparación es estricta (>) y solo se
    evalúa en el tick de ping."""
    monkeypatch.setattr(ws_router, "PING_INTERVAL_SECONDS", 0.1)
    monkeypatch.setattr(ws_router, "PONG_TIMEOUT_SECONDS", 0.25)

    pings = 0
    with pytest.raises(WebSocketDisconnect) as exc:
        with _conectar(ws_client, tenant.id) as ws:
            ws.receive_json()  # hello
            ws.receive_json()  # events []
            while True:
                msg = ws.receive_json()
                assert msg["type"] == "ping"
                pings += 1

    assert exc.value.code == 1001
    assert pings == 2  # ping en ciclo 1 y 2; cierre en el ciclo 3


def test_qa_json_invalido_no_mata_la_conexion(db_session, tenant, ws_client):
    with _conectar(ws_client, tenant.id) as ws:
        ws.receive_json()
        ws.receive_json()

        ws.send_text("esto no es json")
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "unsupported"

        broker.publish(tenant_id=tenant.id, tipo="downtime", data={"min": 5})
        msg = ws.receive_json()
    assert msg["type"] == "event"


def test_qa_mensaje_json_no_objeto_no_mata_la_conexion(db_session, tenant, ws_client):
    with _conectar(ws_client, tenant.id) as ws:
        ws.receive_json()
        ws.receive_json()

        ws.send_text("[1, 2, 3]")
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "unsupported"

        broker.publish(tenant_id=tenant.id, tipo="kpi", data={"oee": 1})
        msg = ws.receive_json()
    assert msg["type"] == "event"


def _recibe_con_timeout(ws, timeout=2.0):
    """Recibe un mensaje con tope; None si no llega nada (conexión colgada)."""
    resultado: dict = {}

    def _hilo():
        try:
            resultado["msg"] = ws.receive_json()
        except Exception as e:  # noqa: BLE001 - QA: cualquier salida vale
            resultado["exc"] = e

    h = threading.Thread(target=_hilo, daemon=True)
    h.start()
    h.join(timeout)
    if h.is_alive():
        return None
    return resultado.get("msg") or resultado.get("exc")


def test_qa_frame_binario_recibe_error_y_conexion_sigue_viva(
    db_session, tenant, ws_client
):
    """Fix F1 (2026-08-15, orquestador): un frame binario debe responder
    error 'unsupported' y mantener la conexión viva, no matar el handler.
    El contrato (ADR-014) exige error + seguir para mensajes no soportados."""
    with _conectar(ws_client, tenant.id) as ws:
        ws.receive_json()  # hello
        ws.receive_json()  # events []
        ws.send_bytes(b"\x00\x01")
        err = _recibe_con_timeout(ws)
        assert err is not None, "no se recibió error tras frame binario"
        assert err["type"] == "error" and err["code"] == "unsupported", err
        # la conexión sigue viva: un pong posterior no revienta
        ws.send_json({"type": "pong"})
        ws.send_bytes(b"\x00\x02")
        err2 = _recibe_con_timeout(ws)
        assert err2 is not None, "no se recibió segundo error tras frame binario"
        assert err2["type"] == "error", err2
    _espera_hasta(lambda: len(broker._listeners.get(str(tenant.id), ())) == 0)


def test_qa_subprotocolo_distinto_se_acepta_sin_subprotocolo(db_session, tenant, ws_client):
    """El servidor solo devuelve kavana.v1 si viene en la cabecera; si el
    cliente pide otro subprotocolo, se acepta sin subprotocolo."""
    with _conectar(ws_client, tenant.id, subprotocols=["otro.v2"]) as ws:
        hello = ws.receive_json()
    assert hello["type"] == "hello"
    assert ws.accepted_subprotocol is None


# ---------------------------------------------------------------------------
# Broker: límites y deduplicación de listeners
# ---------------------------------------------------------------------------


def test_qa_broker_limite_200_descarta_los_mas_viejos():
    b = EventBroker(max_events=200)
    for i in range(205):
        b.publish(tenant_id="T", tipo="kpi", data={"seq": i})
    cola = b.get_events("T")
    assert len(cola) == 200
    assert cola[0]["data"]["seq"] == 5
    assert cola[-1]["data"]["seq"] == 204


def test_qa_broker_subscribe_mismo_callback_no_duplica_notificacion():
    b = EventBroker()
    recibidos = []
    b.subscribe("T", recibidos.append)
    b.subscribe("T", recibidos.append)  # set: idempotente
    b.publish(tenant_id="T", tipo="kpi", data={})
    assert len(recibidos) == 1
