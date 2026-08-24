# ADR-014: WebSockets de planta con el broker de eventos en memoria

Estado: Aceptado
Fecha: 2026-08-15
Autor: Jorge Adán (KAVANA Systems)
Patrón de referencia: spec 05 sección 2.6 (eventos en tiempo real, patrón Socket.IO del v2 con cola anti-spam)

## Contexto

El frontend recibe hoy los eventos de planta por POLLING: OperarioPage consulta
`GET /api/v1/events/{tenant_id}` cada 5 segundos y muestra las últimas 3
alertas. El backend ya tiene el core del sistema de eventos listo en
`app/services/events.py` (clase `EventBroker`): cola FIFO por tenant con límite
de 200 eventos, métodos `publish`, `get_events` y `consume`, y un singleton
`broker` importado en `main.py`. El propio docstring del broker dice que está
diseñado para conectarse a WebSockets en producción.

Hechos observados:

- El broker NO tiene listeners: `publish` solo encola. No hay forma de que un
  cliente conectado se entere de un evento nuevo sin volver a preguntar.
- La app es multi-tenant: `tenant_id` identifica la planta y es la clave de
  partición de la cola.
- El evento tiene forma estable: `{id, tipo, data, timestamp}` con `timestamp`
  ISO 8601 UTC. Tipos típicos: `consumo_fifo`, `stock_deficit`, `downtime`,
  `incidencias`, `kpi`, `quality_check`.
- La demo es pública sin login (decisión de Jorge: seed con password_hash
  `!demo`). El backend tiene JWT de 8 h (un turno, spec 05 sección 2.6 del
  modelo de sesión) pero los routers de planta no exigen auth hoy.
- SupervisorPage NO consume eventos por polling; solo refresca OEE/KPIs cada
  10 s por REST. El push de WebSockets le aportaría refresco inmediato de
  `kpi` e `incidencias`.
- Despliegue actual: backend en Fly.io (un solo proceso, una máquina),
  frontend en Vercel con rewrites `/api/*` hacia Fly.

Problema que resuelve: latencia de hasta 5 s en las alertas de planta, requests
vacíos constantes, y un mecanismo de transporte que no aprovecha el broker ya
construido para push (spec 05 2.6).

## Decisión

Añadir un endpoint WebSocket nativo de FastAPI/Starlette que se apoya en el
broker existente, extendido con un mecanismo mínimo de listeners, y un hook
React `usePlantEvents` que lo consume en el frontend. El polling se mantiene
como fallback REST, pero deja de ser el camino principal.

Decisiones concretas:

1. **Endpoint**: `WS /api/v1/ws/events?tenant_id={id}` con subprotocolo
   `kavana.v1`. El tenant se identifica por query param (el navegador no puede
   fijar headers en el handshake de WebSocket). El subprotocolo se usa para
   versionar el formato de mensajes, no para identidad.
2. **Autenticación obligatoria (enmienda 2026-08-24)**: originalmente el token
   era opcional (modo demo público). La auditoría externa del 2026-08-24 lo
   marcó P0: un socket sin token podía leer eventos de cualquier tenant.
   Desde la enmienda, `?access_token={jwt}` es OBLIGATORIO: sin token o con
   token de otro tenant se cierra con 4403, y el tenant autorizado sale del
   JWT (el del query se valida solo contra él). El token por query param
   queda en logs de proxy; se documenta como compromiso aceptado, con la
   alternativa de subprotocolo para producción futura.
3. **Protocolo**: JSON de ida y vuelta, siempre con campo `type`. El servidor
   entrega la cola pendiente al conectar (con `consume`) y hace push en tiempo
   real en `publish` vía listeners.
4. **Integración con el broker**: extender `EventBroker` con
   `subscribe(tenant_id, callback)` y `unsubscribe(tenant_id, callback)`,
   llamados en `publish` de forma best-effort (un callback que falle no rompe
   el publish). Un `ConnectionManager` nuevo mantiene el registro de sockets
   por tenant y entrega a cada conexión a través de una cola thread-safe,
   desacoplada de la velocidad del publicador.
5. **Reconexiones**: la cola FIFO del broker es la memoria de reconexión
   (at-most-once, ver Consecuencias). El hook frontend reconecta con backoff
   exponencial + jitter y heartbeat de aplicación.
6. **Escalado**: se documenta la limitación del broker en memoria (un solo
   proceso) y la vía futura con Redis pub/sub. NO se implementa nada de eso
   ahora (YAGNI: una planta, una máquina en la demo).
7. **Frontend**: nuevo hook `usePlantEvents` que reemplaza el `setInterval`
   de OperarioPage. `api.getEvents` y el endpoint REST se conservan como
   fallback.

## Diseño del contrato

### Endpoint y autenticación

- Ruta: `WS /api/v1/ws/events` (el polling `GET /api/v1/events/{tenant_id}`
  sigue intacto; el subárbol `/ws` separa el transporte).
- Query params: `tenant_id` y `access_token` (ambos obligatorios desde la
  enmienda 2026-08-24).
- Handshake: el cliente manda `Sec-WebSocket-Protocol: kavana.v1`; el servidor
  responde 101 con `kavana.v1`. Si el cliente no manda subprotocolo, se acepta
  igual (compatibilidad) pero el servidor responde sin subprotocolo.
- Validación al conectar:
  1. `tenant_id` vacío o formato inválido → cierre 4404.
  2. El tenant no existe en BD (una consulta a `tenants`) → cierre 4404.
  3. `access_token` presente pero inválido, expirado o con `tenant_id`
     distinto del query → cierre 4403.
  4. Sin `access_token` → modo demo, se acepta.
- Códigos de cierre propios: 4404 (tenant no encontrado), 4403 (token
  inválido o tenant del token no coincide), 1001 (heartbeat caído, lo cierra
  el servidor y el cliente reconecta).

### Protocolo de mensajes (JSON)

Servidor → cliente:

| type | Contenido | Cuándo |
|---|---|---|
| `hello` | `{type, tenant_id, queued}` | Al aceptar la conexión. `queued` es el número de eventos pendientes que se entregarán a continuación. |
| `events` | `{type, events: [Evento, ...]}` | Inmediatamente después de `hello`, con la cola pendiente obtenida por `consume` (puede ser `[]`). El cliente reemplaza su lista con este lote. |
| `event` | `{type, event: Evento}` | Push en tiempo real: cada evento publicado mientras el cliente está conectado. El cliente hace append. |
| `ping` | `{type}` | Cada 30 s. El cliente debe responder `pong`. Si el servidor no recibe `pong` en 2 ciclos (60 s), cierra con 1001. |
| `error` | `{type, code, message}` | Ante un mensaje del cliente no soportado. |

Cliente → servidor:

| type | Contenido | Cuándo |
|---|---|---|
| `pong` | `{type}` | Respuesta a cada `ping`. |
| (cualquier otro) | - | El servidor responde `error` con `code: "unsupported"` y sigue. |

Formato de `Evento` (el mismo del broker, sin cambios):

```json
{"id": "uuid4", "tipo": "consumo_fifo", "data": {"kg": 30}, "timestamp": "2026-08-15T10:00:00Z"}
```

Ejemplo de secuencia de conexión:

1. Cliente: handshake `WS /api/v1/ws/events?tenant_id=...` + subprotocolo `kavana.v1`.
2. Servidor: `{"type":"hello","tenant_id":"...","queued":2}`
3. Servidor: `{"type":"events","events":[{...},{...}]}` (los 2 pendientes)
4. Servidor (al publicarse un evento nuevo): `{"type":"event","event":{...}}`
5. Servidor (cada 30 s): `{"type":"ping"}` → Cliente: `{"type":"pong"}`

### Integración con el broker existente

El broker actual no puede notificar: `publish` solo encola. Se decide
extenderlo con el mínimo cambio compatible:

- Nuevos métodos en `EventBroker`:
  - `subscribe(tenant_id, callback)` y `unsubscribe(tenant_id, callback)`,
    con registro `dict[str, set[callable]]`.
  - En `publish`, después de encolar y aplicar el límite de 200, iterar los
    callbacks del tenant y llamarlos con `(evento)` dentro de try/except.
    Best-effort: un callback que falle se loguea y no rompe el publish
    (mismo espíritu que la auditoría de 4 capas, spec 05 3.5).
  - Sin listeners, `publish` se comporta exactamente igual que hoy: los 3
    tests existentes de `test_events.py` siguen pasando sin cambios.
- Nuevo `ConnectionManager` (`app/services/ws_manager.py`):
  - `connect(tenant_id, ws)` / `disconnect(tenant_id, ws)`: registro de
    sockets por tenant.
  - Cada conexión tiene una `queue.Queue` (thread-safe de stdlib). El
    callback del broker (síncrono, puede ejecutarse desde un hilo del
    threadpool de FastAPI si el publicador es un endpoint `def`) hace
    `cola.put(evento)`, que nunca bloquea al publicador.
  - El handler WS corre un task asyncio por conexión que drena la cola con
    `await asyncio.to_thread(cola.get)` y envía
    `{"type":"event","event":evento}`. Un socket lento no bloquea al
    publicador; si el envío falla, se cierra la conexión y se desuscribe.
  - Al conectar: `pendientes = broker.consume(tenant_id)` y envío del lote
    `events`; después `broker.subscribe(...)`. Al desconectar: `disconnect` +
    `unsubscribe`.
- Orden de entrega garantizado: un evento publicado antes de conectar se
  entrega en el lote inicial; uno publicado después, por `event`. La cola del
  broker no se toca mientras hay conexión (el push es espejo de la cola, no
  consumo), así que un fallo de envío no pierde el evento: sigue en la cola y
  se entrega en la siguiente reconexión. Sin duplicados en el caso normal.

### Reconexiones

- **Servidor**: al detectar un socket caído (error de send o fin de receive),
  el handler sale, `disconnect` limpia el registro y `unsubscribe` quita el
  callback. Los eventos que se publiquen mientras no hay cliente siguen
  entrando en la cola FIFO del tenant (límite 200, descarta los más viejos) y
  se entregan al reconectar con `consume`.
- **Cliente (hook)**: reconexión automática con backoff exponencial + jitter:
  1 s, 2 s, 4 s, 8 s, 16 s, tope 30 s, con jitter ±30 % para evitar
  sincronización de reintentos entre paneles. Reintento indefinido mientras la
  página esté abierta (un panel de planta no debe morir). Reconexión inmediata
  al dispararse el evento `online` del navegador. El backoff se resetea al
  recibir `hello`.
- **Heartbeat**: `ping` del servidor cada 30 s, `pong` del cliente. Detección
  de half-open connections (proxies que matan sockets sin avisar): si el
  servidor no recibe `pong` en 60 s cierra con 1001 y el hook reconecta.
- **Garantía honesta**: la entrega es at-most-once por conexión. Si el cliente
  se cae entre `consume` y el envío del lote, ese lote se pierde para esa
  conexión (los eventos son efímeros de planta; los datos de negocio viven en
  PostgreSQL: Kardex, ProductionLog, incidencias). Exactly-once exigiría ack
  por mensaje y no se justifica para alertas de planta.

### Escalado y límites

- **Limitación actual (explícita)**: el broker es en memoria y por proceso.
  Con un solo proceso (Fly.io, una máquina) el diseño funciona completo:
  todos los endpoints y todos los sockets comparten el mismo singleton.
- **Qué se rompe al escalar**: con N instancias, un cliente conectado a la
  instancia A no recibe los eventos publicados por un request que cayó en la
  instancia B (el fan-out y la cola son locales). El polling no tenía este
  problema; el WebSocket sí.
- **Vía futura (NO se implementa en este ADR)**: Redis Pub/Sub. Canal por
  tenant `kavana:events:{tenant_id}`. El callback de `publish` pasa a
  publicar en Redis en lugar de fan-out local; cada instancia se suscribe solo
  a los canales de los tenants con clientes conectados y hace fan-out local.
  Alternativa con garantías más fuertes: Redis Streams (consumidores por
  grupo, at-least-once). Consideración abierta para esa fase: con pub/sub la
  cola por tenant debe centralizarse en Redis (lista por tenant) o el evento
  debe encolarse localmente en cada instancia vía el canal, porque hoy la cola
  vive solo donde se publica.
- **Nota de despliegue**: Vercel reenvía upgrades de WebSocket en rewrites
  `/api/*` según su documentación; hay que verificarlo en el deploy real. Si
  el rewrite no reenvía el upgrade, el hook debe apuntar a
  `VITE_WS_URL` directo a Fly (`wss://steelworks-api.fly.dev`). CORS no aplica
  al handshake de WebSocket, pero el origen se puede validar igualmente si se
  quiere restringir.

### Contrato frontend: hook usePlantEvents

Archivo nuevo: `frontend/src/hooks/usePlantEvents.ts`.

```ts
interface UsePlantEvents {
  conectar(tenantId: string): void
  desconectar(): void
  eventos: EventData[]                 // últimos maxEventos (default 50), el más reciente al final
  ultimoEvento: EventData | null
  estado: 'desconectado' | 'conectando' | 'conectado' | 'reconectando'
  error: string | null
}

function usePlantEvents(options?: {
  maxEventos?: number        // default 50
  autoReconnect?: boolean    // default true
  backoffBaseMs?: number     // default 1000
  heartbeatMs?: number       // default 30000
}): UsePlantEvents
```

Comportamiento interno:

- `conectar(tenantId)`: cierra el socket anterior si existe y abre
  `new WebSocket(url, 'kavana.v1')` con
  `url = (VITE_WS_URL ?? derivado de location) + '/api/v1/ws/events?tenant_id=' + tenantId`.
  Estado `conectando`; al recibir `hello` pasa a `conectado`.
- `onmessage`: `events` → reemplaza `eventos`; `event` → append truncando a
  `maxEventos`; `ping` → envía `{"type":"pong"}`; `error` → setError.
- `onclose`: si `autoReconnect`, estado `reconectando` y programa el backoff
  (exponencial + jitter, tope 30 s); escucha `window.online` para reconectar
  al instante. `desconectar()` cancela timers, cierra el socket y limpia.
- Cleanup al desmontar (React 19 StrictMode monta dos veces en dev: el hook
  debe ser idempotente y el cleanup debe cerrar socket y timers).

Reemplazos en las páginas:

- **OperarioPage**: eliminar el `useEffect` con `setInterval` de 5 s y
  `api.getEvents` (líneas 71 a 82 actuales). Sustituir por
  `const { conectar, eventos, estado } = usePlantEvents()` +
  `useEffect(() => { const t = getTenantId(); if (t) conectar(t) }, [])`.
  Render: `eventos.slice(-3)` (mismo comportamiento visual que hoy) y un
  indicador de estado (badge "En vivo" / "Reconectando...").
- **SupervisorPage**: hoy no usa eventos. Integración opcional y aditiva:
  suscribirse y refrescar KPIs cuando `ultimoEvento?.tipo === 'kpi'` o
  `'incidencias'`. La carga inicial sigue por REST (polling de KPIs a 10 s se
  puede reducir o eliminar para esos tipos). No es requisito de esta fase;
  lo mínimo es OperarioPage.
- **`api.getEvents` y `GET /api/v1/events/{tenant_id}`**: se conservan como
  fallback REST (compatibilidad y diagnóstico manual); el frontend deja de
  usarlos por defecto.

## Alternativas evaluadas

| Alternativa | Ventajas | Inconvenientes | Descartada por |
|---|---|---|---|
| Mantener polling HTTP (statu quo) | Cero cambios, ya funciona, sin estado de conexión en el servidor | Latencia hasta 5 s, requests vacíos cada 5 s por panel, no aprovecha el broker (spec 05 2.6 lo diseñó para push), no escala con muchas pantallas | El broker ya existe y está documentado para WebSocket; el polling es deuda, no diseño |
| Server-Sent Events (SSE, EventSource) | Unidireccional servidor a cliente suficiente para alertas, reconexión nativa del navegador, reutiliza HTTP | Sin canal cliente a servidor (no hay pong ni re-suscripción), la reconexión nativa no reenvía bien query params dinámicos, headers custom requieren fetch + ReadableStream, no se alinea con el patrón bidireccional del legacy (Socket.IO) | El control del cliente (heartbeat, estado, re-suscripción) y el patrón del v2 son bidireccionales |
| Socket.IO (como el legacy v2) | Patrón ya probado en el legacy, rooms por tenant, reconexión y acks incluidas | Dependencia nueva (python-socketio + cliente JS), protocolo sobre WebSocket sin necesidad: una planta, pocos paneles, FastAPI ya tiene WS nativo | YAGNI: el stack actual cubre el caso con WS nativo y menos dependencias |
| Redis pub/sub desde el inicio | Escalado horizontal desde el día uno, cola centralizada | Infraestructura y operación nuevas (otro servicio), latencia de red añadida, sin demanda: un solo proceso y una planta en la demo | YAGNI documentado como vía futura en este ADR; la demo no tiene N instancias |
| WS nativo + broker extendido con listeners (ELEGIDA) | Mínimo cambio sobre el core probado, sin dependencias nuevas, la cola existente resuelve las reconexiones gratis, subprotocolo versiona el formato | El broker deja de ser 100 % "sin infraestructura" (gana callbacks), fan-out local limita a un proceso (documentado), token por query param en demo | - |

## Consecuencias

**Positivas:**

- Alertas de planta en tiempo real (push inmediato en vez de 5 s de polling).
- Se aprovecha el broker ya construido; los 3 tests existentes de
  `test_events.py` siguen pasando (backward compatible).
- La cola FIFO por tenant resuelve la reconexión sin estado adicional en BD.
- Sin dependencias nuevas en backend ni frontend (WebSocket nativo).
- El subprotocolo `kavana.v1` permite evolucionar el formato sin romper
  clientes viejos.

**Negativas / tradeoffs:**

- Entrega at-most-once: un lote perdido en una caída justa entre `consume` y
  envío no se recupera. Aceptable: los eventos son efímeros y la fuente de
  verdad (PostgreSQL) no depende de ellos.
- El broker con listeners deja de ser "core sin infraestructura": los
  callbacks son acoplamiento, mitigado con best-effort (un callback roto no
  rompe el publish).
- Escalado limitado a un proceso hasta migrar el fan-out a Redis (documentado,
  no implementado).
- El token JWT por query param queda en logs de proxy en producción futura;
  compromiso aceptado para la demo, alternativa de subprotocolo documentada.
- Vercel + WebSockets requiere verificación en el deploy real; fallback
  `VITE_WS_URL` directo a Fly.

**Cómo se verifica:**

- Tests backend: handshake, entrega de cola pendiente, push en tiempo real,
  separación por tenant, cierres 4403/4404, limpieza de suscripción al
  desconectar, backward compatibility del broker (lista completa abajo).
- E2E contra PostgreSQL real (`e2e_websockets.py`): conexión con el tenant del
  seed demo, publicación vía servicio real y recepción del push.
- Tests frontend: hook con WebSocket mock (fake timers para el backoff) y
  tests de OperarioPage con el polling eliminado.
- Manual: dos pestañas abiertas en la demo; producir una bobina en una y
  ver la alerta en la otra sin recargar.

## Tests necesarios

Backend (`backend/tests/test_websockets.py` + E2E `backend/e2e_websockets.py`):

1. `test_ws_handshake_acepta_subprotocolo_kavana_v1`
2. `test_ws_conecta_y_recibe_hello_con_tenant`
3. `test_ws_entrega_cola_pendiente_al_conectar` (2 publicados antes → lote
   `events` con 2; `consume` posterior devuelve vacío)
4. `test_ws_push_en_tiempo_real_al_publicar` (conectado → publish →
   `type=event`)
5. `test_ws_separa_canales_por_tenant` (dos sockets de dos tenants; cada uno
   recibe solo lo suyo)
6. `test_ws_tenant_inexistente_cierra_4404`
7. `test_ws_token_invalido_cierra_4403`
8. `test_ws_token_de_otro_tenant_cierra_4403`
9. `test_ws_sin_token_conecta_en_modo_demo`
10. `test_ws_desconexion_limpia_suscripcion` (cerrar → publish no notifica;
    reconectar → `consume` entrega lo publicado mientras estaba caído)
11. `test_ws_mensaje_desconocido_recibe_error`
12. `test_broker_subscribe_notifica_callback_en_publish`
13. `test_broker_unsubscribe_deja_de_notificar`
14. `test_broker_publish_sin_listeners_mantiene_encolado` (backward compat)
15. `test_broker_callback_que_falla_no_rompe_publish`
16. E2E `e2e_websockets.py`: conexión real contra el tenant del seed demo,
    publish vía un servicio real (p.ej. incidencias) y recepción del push.

Frontend (`frontend/src/test/usePlantEvents.test.tsx` + actualización de
`OperarioPage.test.tsx`):

1. `test_conectar_abre_websocket_con_tenant_id_y_subprotocolo`
2. `test_recibe_lote_events_y_actualiza_eventos`
3. `test_recibe_event_individual_y_hace_append_con_limite`
4. `test_responde_pong_al_recibir_ping`
5. `test_reconexion_automatica_con_backoff_exponencial` (fake timers)
6. `test_reconexion_inmediata_al_volver_la_red` (evento `online`)
7. `test_desconectar_cierra_socket_y_limpia_estado`
8. `test_estado_conexion_se_expone` (los 4 estados)
9. `test_operario_muestra_eventos_del_websocket` (mock global de WebSocket;
    el polling de 5 s desaparece)
10. `test_operario_muestra_estado_reconectando`

## Localización en código

- `backend/app/routers/ws.py`: NUEVO: endpoint `WS /api/v1/ws/events`,
  handshake, validación de tenant/token, protocolo de mensajes, heartbeat.
- `backend/app/services/ws_manager.py`: NUEVO: `ConnectionManager` con
  registro de sockets por tenant, cola thread-safe por conexión y task
  drenador.
- `backend/app/services/events.py`: MODIFICAR: añadir `subscribe` /
  `unsubscribe` y la llamada best-effort a callbacks en `publish`.
- `backend/app/main.py`: MODIFICAR: registrar el router WS.
- `frontend/src/hooks/usePlantEvents.ts`: NUEVO: hook con la API
  `conectar/desconectar/eventos/ultimoEvento/estado/error` y reconexión con
  backoff.
- `frontend/src/pages/OperarioPage.tsx`: MODIFICAR: eliminar el polling de
  5 s, usar el hook, indicador de estado de conexión.
- `frontend/src/pages/SupervisorPage.tsx`: MODIFICAR (opcional): refresco de
  KPIs al recibir `kpi` / `incidencias`.
- `frontend/src/lib/api.ts`: SIN CAMBIOS: `getEvents` se conserva como
  fallback REST.
- `backend/tests/test_websockets.py`, `backend/e2e_websockets.py`,
  `frontend/src/test/usePlantEvents.test.tsx`: NUEVOS (lista completa
  arriba).

## Referencias

- Spec: `docs/specs/05-otros-servicios.md` sección 2.6 (alertas en tiempo
  real, patrón Socket.IO del v2) y 3.5 (auditoría best-effort, modelo para el
  callback del broker).
- Código actual: `backend/app/services/events.py`, `backend/app/main.py`
  (endpoint de polling), `frontend/src/lib/api.ts` (`getEvents` y
  `getTenantId`), `frontend/src/pages/OperarioPage.tsx` (polling actual).
- ADRs relacionados: ADR-002 (PostgreSQL como fuente de verdad de negocio;
  los eventos efímeros no se persisten por diseño).
