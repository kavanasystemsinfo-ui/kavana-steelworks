"""WebSocket de planta: push de eventos en tiempo real (ADR-014).

Contrato:
- WS /api/v1/ws/events?tenant_id={id}&access_token={jwt}, subprotocolo
  kavana.v1. El token es OBLIGATORIO (auditoría 2026-08-24): sin token o con
  token de otro tenant se cierra 4403; el tenant autorizado sale del JWT.
- Al conectar: hello con el número de pendientes y lote events (cola por
  consume). Después push realtime por callback del broker.
- Heartbeat: ping cada 30 s; sin pong en 60 s se cierra con 1001.
- Cierres: 4404 (tenant inexistente), 4403 (token inválido o de otro tenant).
"""

import asyncio
import json
import logging
import queue
import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.core.database import SessionLocal
from app.models import Tenant
from app.services import auth as auth_service
from app.services.events import broker
from app.services.ws_manager import ConnectionManager

router = APIRouter(tags=["ws"])

PING_INTERVAL_SECONDS = 30
PONG_TIMEOUT_SECONDS = 60  # 2 ciclos de ping sin pong: cierre 1001

logger = logging.getLogger(__name__)
manager = ConnectionManager()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbDep = Annotated[Session, Depends(get_db)]


async def _client_loop(websocket: WebSocket, estado: dict) -> None:
    """Recibe mensajes del cliente: pong mantiene vivo el heartbeat."""
    while True:
        try:
            raw = await websocket.receive_text()
        except Exception:
            # Frame binario o mensaje no textual: responder error y seguir
            # (Starlette 1.6 no autocierra; sin este catch el handler muere
            # y el cliente queda colgado hasta su watchdog)
            await websocket.send_json(
                {"type": "error", "code": "unsupported", "message": "Frame no soportado"}
            )
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            await websocket.send_json(
                {"type": "error", "code": "unsupported", "message": "JSON inválido"}
            )
            continue
        if not isinstance(data, dict) or data.get("type") != "pong":
            await websocket.send_json(
                {
                    "type": "error",
                    "code": "unsupported",
                    "message": "Tipo de mensaje no soportado",
                }
            )
            continue
        estado["last_pong"] = time.monotonic()


async def _drain(websocket: WebSocket, cola: queue.Queue) -> None:
    """Task por conexión: envía cada evento de la cola como mensaje event.

    Poll corto en vez de to_thread(cola.get): la cancelación al desconectar
    no deja un hilo bloqueado en get() hasta el próximo evento del tenant.
    """
    while True:
        try:
            evento = cola.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.05)
            continue
        try:
            await websocket.send_json({"type": "event", "event": evento})
        except Exception:
            logger.warning("Envío WebSocket fallido; se cierra la conexión")
            return


async def _heartbeat(websocket: WebSocket, estado: dict) -> None:
    """Ping periódico; cierra con 1001 si el cliente no responde pong."""
    while True:
        await asyncio.sleep(PING_INTERVAL_SECONDS)
        # >= para cerrar a los 60s reales, no en el tercer ciclo (~90s):
        # el tick de ping ocurre a los 30s y 60s; con > estricto el cierre
        # se retrasa un ciclo entero cuando el delta ronda los 60s
        if time.monotonic() - estado["last_pong"] >= PONG_TIMEOUT_SECONDS:
            await websocket.close(code=1001)
            return
        try:
            await websocket.send_json({"type": "ping"})
        except Exception:
            return


@router.websocket("/api/v1/ws/events")
async def ws_events(
    websocket: WebSocket,
    tenant_id: str,
    access_token: str | None = None,
    db: DbDep = None,
):
    """Valida tenant/token, entrega la cola pendiente y hace push realtime."""
    try:
        tenant_uuid = uuid.UUID(tenant_id)
    except (ValueError, TypeError):
        await websocket.close(code=4404)
        return
    if db.scalar(select(Tenant).where(Tenant.id == tenant_uuid)) is None:
        await websocket.close(code=4404)
        return
    if access_token is None:
        # Auditoría 2026-08-24 (hallazgo 2): el canal autenticado no admite
        # conexiones anónimas. El tenant autorizado sale SIEMPRE del JWT.
        await websocket.close(code=4403)
        return
    payload = auth_service.verify_token(access_token)
    if payload is None or auth_service.is_revoked(db, access_token):
        await websocket.close(code=4403)
        return
    if str(payload.get("tenant_id", "")) != str(tenant_uuid):
        await websocket.close(code=4403)
        return

    subprotocol = (
        "kavana.v1"
        if "kavana.v1" in websocket.headers.get("sec-websocket-protocol", "")
        else None
    )
    await websocket.accept(subprotocol=subprotocol)

    pendientes = broker.consume(str(tenant_uuid))
    await websocket.send_json(
        {"type": "hello", "tenant_id": str(tenant_uuid), "queued": len(pendientes)}
    )
    await websocket.send_json({"type": "events", "events": pendientes})

    cola = manager.connect(str(tenant_uuid), websocket)
    estado = {"last_pong": time.monotonic()}

    def _callback(evento: dict) -> None:
        # put() es no bloqueante: el publicador nunca espera por el socket
        cola.put(evento)

    broker.subscribe(str(tenant_uuid), _callback)

    client_task = asyncio.create_task(_client_loop(websocket, estado))
    drain_task = asyncio.create_task(_drain(websocket, cola))
    ping_task = asyncio.create_task(_heartbeat(websocket, estado))
    tasks = (client_task, drain_task, ping_task)
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if task.cancelled():
                continue
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                logger.warning("Task del WebSocket terminó con error: %s", exc)
    except asyncio.CancelledError:
        # Cierre externo (apagado del servidor o teardown del cliente): la
        # cancelación no debe propagarse sin limpiar la suscripción.
        pass
    finally:
        for task in tasks:
            task.cancel()
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass
        broker.unsubscribe(str(tenant_uuid), _callback)
        manager.disconnect(str(tenant_uuid), websocket)
