"""Gestor de conexiones WebSocket por tenant (ADR-014)."""

import queue
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    """Registro de sockets por tenant con una cola thread-safe por conexión.

    El callback del broker (síncrono, corre en el hilo del publicador) solo
    hace put() en la cola: un socket lento nunca bloquea al publicador. El
    drenado asíncrono lo hace el router con un task por conexión.
    """

    def __init__(self) -> None:
        self._sockets: dict[str, dict[WebSocket, queue.Queue]] = defaultdict(dict)

    def connect(self, tenant_id: str, websocket: WebSocket) -> queue.Queue:
        """Registra el socket y devuelve su cola de eventos."""
        cola: queue.Queue = queue.Queue()
        self._sockets[str(tenant_id)][websocket] = cola
        return cola

    def disconnect(self, tenant_id: str, websocket: WebSocket) -> None:
        """Quita el socket del registro; no-op si ya no estaba."""
        self._sockets.get(str(tenant_id), {}).pop(websocket, None)
