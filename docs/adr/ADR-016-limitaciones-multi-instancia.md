# ADR-016: Limitaciones de arquitectura en despliegue multi-instancia

- Estado: Aceptado (con deudas documentadas)
- Fecha: 2026-08-24
- Origen: auditoría externa (CTO adversarial) del 2026-08-24, hallazgos 5 y 6

## Contexto

La auditoría externa señala dos decisiones que son correctas para una demo
single-instance pero que no escalan a producción multi-instancia:

1. **EventBroker en memoria** (`app/services/events.py`): colas y listeners
   viven en el proceso. Con dos réplicas de Fly, un evento publicado en la
   instancia A no llega a los WebSockets conectados a la instancia B.
   El comentario del propio código lo declara: "instancia única por proceso".
2. **Migraciones + seed en el entrypoint** (`docker-entrypoint.sh`): cada
   contenedor ejecuta `alembic upgrade head` y el seed antes de arrancar
   uvicorn. Con dos máquinas arrancando a la vez durante un deploy, ambas
   podrían correr migraciones concurrentemente.

## Decisión

Se aceptan ambas limitaciones para la demo actual (una planta, una instancia,
Fly free) y se DOCUMENTAN como frontera explícita del sistema, con la vía de
escape definida. No se implementan ahora (YAGNI).

### 1. Broker in-memory

- La demo corre con `min_machines_running = 1` y escala manual: una sola
  instancia. En ese escenario el broker es correcto y no hay pérdida.
- Si algún día se escala horizontal, la solución es sustituir el transporte,
  no reescribir el dominio: `EventBroker` ya separa `publish/subscribe/
  consume`, así que basta un backend Redis Pub/Sub o PostgreSQL LISTEN/NOTIFY
  detrás de esa interfaz. Los clientes WebSocket no cambian.

### 2. Migraciones en el entrypoint

- Es un patrón release-migration: aceptable mientras exista una sola
  instancia (Fly arranca la nueva antes de matar la vieja, pero las
  migraciones son idempotentes hacia adelante).
- Vía de escape si se escala: mover `alembic upgrade head` a un release
  command (flyctl release_command) y dejar al entrypoint solo uvicorn. El
  seed es idempotente/reparador y puede quedarse.

## Consecuencias

- Cualquiera que lea este ADR sabe exactamente qué garantías NO tiene el
  sistema hoy: realtime distribuido y arranque multi-instancia seguro.
- Las respuestas de entrevista están en las secciones anteriores: reconocer
  la frontera y nombrar la solución (Redis/NATS/LISTEN-NOTIFY; release
  command) demuestra más conocimiento que fingir que no existe.
- Revisitar este ADR antes de escalar Fly a más de una instancia.
