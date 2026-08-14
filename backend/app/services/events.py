"""Broker de eventos de planta en memoria (spec 05, sección 2.6).

Patrón del v2: eventos en tiempo real (Socket.IO) con cola anti-spam.
Este broker es el core sin infraestructura: en producción se conecta a
WebSockets; la cola por tenant evita perder eventos entre reconexiones.

Eventos típicos: consumo_fifo, stock_deficit, downtime, incidencias, kpi.
"""

import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime


class EventBroker:
    """Cola por tenant con límite (FIFO, descarta los más viejos)."""

    def __init__(self, max_events: int = 200) -> None:
        self.max_events = max_events
        self._queues: dict[str, deque] = defaultdict(deque)

    def publish(self, *, tenant_id, tipo: str, data: dict) -> dict:
        """Publica un evento en el canal del tenant."""
        evento = {
            "id": str(uuid.uuid4()),
            "tipo": tipo,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        cola = self._queues[str(tenant_id)]
        cola.append(evento)
        while len(cola) > self.max_events:
            cola.popleft()
        return evento

    def get_events(self, tenant_id) -> list[dict]:
        """Devuelve los eventos pendientes del tenant (sin consumirlos)."""
        return list(self._queues.get(str(tenant_id), []))

    def consume(self, tenant_id) -> list[dict]:
        """Devuelve y vacía la cola del tenant (entrega por WebSocket)."""
        cola = self._queues.get(str(tenant_id))
        if cola is None:
            return []
        eventos = list(cola)
        cola.clear()
        return eventos


# Instancia única por proceso (singleton ligero)
broker = EventBroker()
