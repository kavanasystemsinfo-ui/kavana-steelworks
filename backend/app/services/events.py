"""Broker de eventos de planta en memoria (spec 05, sección 2.6).

Patrón del v2: eventos en tiempo real (Socket.IO) con cola anti-spam.
Este broker es el core sin infraestructura: en producción se conecta a
WebSockets; la cola por tenant evita perder eventos entre reconexiones.

Eventos típicos: consumo_fifo, stock_deficit, downtime, incidencias, kpi.
"""

import logging
import threading
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


class EventBroker:
    """Cola por tenant con límite (FIFO, descarta los más viejos) y listeners."""

    def __init__(self, max_events: int = 200) -> None:
        self.max_events = max_events
        self._queues: dict[str, deque] = defaultdict(deque)
        self._listeners: dict[str, set] = defaultdict(set)
        # publish/consume corren en hilos distintos (threadpool REST vs loop WS)
        self._lock = threading.Lock()

    def publish(self, *, tenant_id, tipo: str, data: dict) -> dict:
        """Publica un evento en el canal del tenant y notifica a los listeners."""
        evento = {
            "id": str(uuid.uuid4()),
            "tipo": tipo,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        tenant = str(tenant_id)
        with self._lock:
            cola = self._queues[tenant]
            cola.append(evento)
            while len(cola) > self.max_events:
                cola.popleft()
        self._notify(tenant, evento)
        return evento

    def get_events(self, tenant_id) -> list[dict]:
        """Devuelve los eventos pendientes del tenant (sin consumirlos)."""
        with self._lock:
            return list(self._queues.get(str(tenant_id), []))

    def consume(self, tenant_id) -> list[dict]:
        """Devuelve y vacía la cola del tenant (entrega por WebSocket)."""
        tenant = str(tenant_id)
        with self._lock:
            cola = self._queues.get(tenant)
            if cola is None:
                return []
            eventos = list(cola)
            cola.clear()
            return eventos

    def subscribe(self, tenant_id, callback) -> None:
        """Registra un callback que se llamará con cada evento publicado."""
        with self._lock:
            self._listeners[str(tenant_id)].add(callback)

    def unsubscribe(self, tenant_id, callback) -> None:
        """Quita un callback; no-op si no estaba registrado."""
        with self._lock:
            self._listeners.get(str(tenant_id), set()).discard(callback)

    def _notify(self, tenant: str, evento: dict) -> None:
        """Fan-out best-effort: un callback roto no rompe el publish (DLQ)."""
        with self._lock:
            callbacks = list(self._listeners.get(tenant, ()))
        for callback in callbacks:
            try:
                callback(evento)
            except Exception:
                logger.exception(
                    "Callback de eventos falló para tenant %s; el publish continúa", tenant
                )


# Instancia única por proceso (singleton ligero)
broker = EventBroker()
