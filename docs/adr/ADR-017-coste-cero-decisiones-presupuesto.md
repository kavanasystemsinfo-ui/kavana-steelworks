# ADR-017: Coste cero y decisiones tomadas por presupuesto

- Estado: Aceptado
- Fecha: 2026-09-17
- Autor: Jorge Adán (KAVANA Systems)

## Contexto

KAVANA Steelworks es una pieza de portafolio con un único usuario real: su
autor. Está desplegado y funciona (Fly.io + Vercel, con migraciones y seed demo
en el entrypoint), pero se ha construido para costar ~0 €/mes. Esa restricción
no es un detalle de infraestructura: ha decidido el transporte de eventos, el
almacenamiento de las fotos de incidencias, el motor de búsqueda de los
asistentes RAG, los límites anti-abuso y el tamaño de la máquina.

Parte de esas decisiones ya están documentadas por separado (ADR-014 para los
WebSockets, ADR-016 para las limitaciones de multi-instancia). Este ADR las
reúne, las declara como decisiones económicas —no técnicas neutrales— y fija
qué cambiaría con usuarios reales y presupuesto.

## Decisión

Se mantiene la arquitectura actual de coste ~0 €/mes y se asume y se documenta
cada partida con lo que hay hoy, el porqué y qué cambiaría con usuarios reales
y presupuesto. La regla es que ninguna limitación presupuestaria quede
implícita: si algo es barato pero peor, se dice en la misma frase.

### Partidas y frontera de cada una

| Partida | Hoy | Por qué | Con usuarios reales y presupuesto |
|---|---|---|---|
| Cómputo | App `steelworks-api` en Fly.io, `cpu_kind = "shared"` (1 CPU) / 256 MB / región `cdg`, con `min_machines_running = 0` y `auto_stop_machines = "stop"` | Una demo con un usuario no necesita una máquina despierta 24 h; la máquina se apaga y el coste tiende a cero | Réplicas mínimas fijas (sin arranque en frío), más memoria, región o regiones cercanas a planta y un entorno de staging separado |
| Base de datos | PostgreSQL gestionado (migraciones Alembic + CHECK reales) | El dominio es relacional (órdenes, bobinas, consumos, Kardex) y el FIFO exige transacciones atómicas (ADR-002). Es la pieza que no se negocia por precio | Mismo motor, con backups, réplica de lectura y plan dimensionado |
| Eventos de planta | `EventBroker` en memoria del proceso (`app/services/events.py`), con polling como fallback | Con una sola instancia el fan-out local es correcto y ahorra un servicio (ADR-014, ADR-016) | Redis Pub/Sub o PostgreSQL LISTEN/NOTIFY detrás de la misma interfaz `publish/subscribe/consume`; el dominio y los clientes WebSocket no cambian |
| Migraciones y seed | `alembic upgrade head` + seed demo idempotente en `docker-entrypoint.sh` | Con una instancia el patrón release-migration es suficiente y evita un paso de release extra | `flyctl release_command` para las migraciones y seed solo en demo (ADR-016) |
| Fotos de incidencias | BYTEA en PostgreSQL (`incidencias.foto_data`), con sesión de subida de un solo uso y validación por magic bytes | El legacy usaba Cloudinary; no portarlo ahorra un servicio externo y mantiene la foto dentro de la transacción de la incidencia | Object storage + CDN y liberar los bytes de la base de datos; el flujo por QR y sesión de un solo uso se conserva |
| Asistentes RAG (2 bots) | TF-IDF en memoria (sin embeddings, sin coste) + LLM vía OpenRouter con modelo `:free`; el corpus se copia al contenedor en el build | Se buscaba un asistente honesto sobre la documentación real, no un buscador semántico; TF-IDF basta para el tamaño del corpus | Embeddings + pgvector o índice gestionado, y modelo de pago con presupuesto de tokens |
| Límites anti-abuso | En memoria del proceso: 15 preguntas/día por IP y 500 caracteres por pregunta, pensados para contener el coste del asistente | Con un proceso y tráfico de portafolio, un contador en memoria es suficiente y no añade Redis | Rate limit en almacén compartido (Redis) para que valga con varias instancias, más cuotas por usuario |
| Identidad | JWT propio con roles (operario, materiales, supervisor, admin) y cuentas demo publicadas a propósito (`<rol>@demo.local`, password `kavana`). `SECURITY.md` prohíbe desplegar con datos reales | La demo tiene que poder probarse sin fricción: el reclutador entra con una credencial publicada y datos ficticios | Identidad real (SSO/IdP corporativo), MFA, secretos por entorno y retirada de las cuentas demo |
| Verificación | 233+ tests backend y 71 frontend en CI (ruff, pytest, migraciones, build TS, vitest). Los E2E contra PostgreSQL real (`backend/e2e_*.py`) se ejecutan a mano en local | No gastar minutos de CI en levantar un PostgreSQL por job, y mantener la suite de CI rápida y verde | CI con servicio PostgreSQL y los E2E dentro del pipeline, tests de carga y observabilidad (APM y alertas); hoy la única señal en producción son `/health/live` y `/health/ready` |

## Alternativas evaluadas

| Alternativa | A favor | En contra | Veredicto |
|---|---|---|---|
| Fly.io free con auto-stop y una instancia (ELEGIDA) | Coste ~0 €/mes, despliegue reproducible por Dockerfile, PostgreSQL gestionado en la misma plataforma | Arranque en frío, 256 MB, sin margen para escalado horizontal ni staging | Elegida para una demo de un usuario; la vía de escape está en ADR-016 |
| VPS propio o clúster k3s | Control total, sin límites de plataforma, permite varios servicios (Redis, object storage) | Coste fijo mensual y trabajo de operación (parches, backups, TLS) que no aporta nada al portafolio | Descartada por presupuesto y por foco: la plataforma gestionada ya cubre la demo |
| Redis desde el primer día (eventos y rate limit) | Realtime distribuido y límites compartidos entre instancias | Otro servicio que pagar y operar sin demanda real: hoy hay una planta y un proceso (YAGNI, ADR-014) | Descartada ahora; vía futura documentada detrás de la interfaz de `EventBroker` |
| Object storage (o Cloudinary) para las fotos | No engorda la base de datos, CDN, ciclo de vida de objetos | Servicio externo y credenciales más para una funcionalidad que en la demo se usa con fotos de prueba | Descartada ahora; documentada como el cambio a hacer con usuarios reales |
| Embeddings y base vectorial para el asistente | Mejor recuperación semántica | Índice que mantener, vector store o pgvector, coste por embedding y por token | Descartada ahora; el corpus real del repo funciona con TF-IDF y el modelo `:free` |
| Cuentas de usuario reales desde el principio | Seguridad creíble desde el día uno | Un sistema de identidad completo (alta, recuperación, MFA, correo) es un proyecto aparte y no demuestra el dominio MES | Descartada; en su lugar, roles reales y cuentas demo explícitamente públicas y datos ficticios |
| Levantar PostgreSQL también en CI para correr los E2E | Cada push verifica contra el motor real | Más minutos de CI y suites más lentas para un proyecto de un solo autor | Descartada de momento; los E2E se ejecutan a mano contra PostgreSQL real y la CI mantiene ruff + pytest + check de migraciones |

## Consecuencias

### Positivas

- El coste de operación es ~0 €/mes y toda la inversión se ha ido al dominio, a
  las specs y a los tests, que es lo que se puede evaluar leyendo el repo.
- Las fronteras están escritas: quién lea este ADR y ADR-016 sabe qué garantías
  no tiene el sistema y con qué se sustituye cada pieza.
- El cambio de infraestructura es localizado y no toca el dominio: el broker
  está detrás de una interfaz, el corpus y el índice detrás de funciones, y la
  foto detrás de una columna y un flujo ya probado.

### Límites que se asumen

- Una sola instancia y máquina que se apaga: arranque en frío y sin realtime
  distribuido.
- Migraciones y seed en el entrypoint (ADR-016).
- Las fotos viven en la misma base de datos que el dominio y su crecimiento no
  está planificado.
- Los límites anti-abuso y el índice del asistente son por proceso: con varias
  instancias dejarían de ser globales.
- Identidad de demo: las credenciales están publicadas y `SECURITY.md` deja
  claro que no debe desplegarse con datos reales.
- Sin observabilidad externa más allá de los health checks, y los E2E contra
  PostgreSQL real no corren en CI.

### Cómo se verifica

- La forma de las decisiones es comprobable en el repositorio: `fly.toml`
  (`min_machines_running = 0`, `auto_stop_machines = "stop"`, `cpu_kind =
  "shared"`, 1 cpu, 256 MB), `backend/docker-entrypoint.sh` (migraciones + seed
  + uvicorn), `backend/app/services/events.py` (broker en memoria),
  `backend/app/services/assistant.py` (TF-IDF en memoria, modelo `:free`,
  límite diario por IP), `backend/app/models/incidencia.py` (foto BYTEA),
  `.github/workflows/ci.yml` (pytest + check de migraciones offline, sin
  servicio PostgreSQL) y los scripts `backend/e2e_*.py` ejecutados a mano.

## Señal de revisión

Revisar este ADR cuando ocurra cualquiera de estas cosas:

1. Entra un segundo usuario o una segunda planta real (aunque sea un piloto):
   toca identidad real, cuotas por usuario y backups.
2. El arranque en frío o los 256 MB se notan en la demo: subir a réplicas
   mínimas fijas y más memoria.
3. Se necesita más de una instancia: Redis o LISTEN/NOTIFY para eventos y
   límites, y `release_command` para las migraciones (ADR-016).
4. El peso de las fotos en PostgreSQL deja de ser despreciable: object storage.
5. El asistente supera el modelo `:free` en volumen o el límite diario por IP
   empieza a molestar a usuarios legítimos.

## Referencias

- Código: `fly.toml`, `backend/docker-entrypoint.sh`,
  `backend/app/services/events.py`, `backend/app/services/assistant.py`,
  `backend/app/models/incidencia.py`, `.github/workflows/ci.yml`.
- Documentos: `SECURITY.md`, `docs/adr/ADR-014-websockets-planta.md`,
  `docs/adr/ADR-016-limitaciones-multi-instancia.md`,
  `docs/audit/changelog.md` (Fase 4, despliegue demo).
- ADRs relacionados: ADR-002 (PostgreSQL sobre MongoDB), ADR-014, ADR-016.
