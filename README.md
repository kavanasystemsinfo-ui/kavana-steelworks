# KAVANA Steelworks

MES/MOM para el sector metalúrgico: control de bobinas de acero, consumo FIFO,
reconciliación industrial, OEE, calidad y trazabilidad ISO 9001. Desplegado en
producción como demo (Fly.io + Vercel) y construido con desarrollo guiado
por tests en las partes críticas (dominio, seguridad y concurrencia).

**Este repo es la reconstrucción moderna (v4) de un sistema legacy.** La lógica
de dominio única (bobinas, FIFO, reconciliación) proviene de años de
experiencia real en planta, y se portó a un stack moderno con TDD, ADRs y
despliegue profesional.

## El origen

Este sistema nació en el suelo de la fábrica, de 8 años trabajando como
operario en fábricas metalúrgicas (CNC, turnos, empresas medianas y grandes).
Nadie lo diseñó en un despacho: lo diseñó alguien que vivió la pérdida de
tiempo del papel, los Excel que no cuadraban y los sistemas que se enteraban de
lo que pasaba en planta horas o días después.

[Lee la historia completa](docs/commercial/01-origen-sistema.md)

## Qué es (y qué no es)

Es un **MES (Manufacturing Execution System) con alcance MOM**, especializado
en la transformación de bobinas de acero. Cubre las 4 actividades de
operaciones del estándar ISA-95: producción, calidad, mantenimiento e
inventario. No es un ERP: no gestiona finanzas ni recursos de la empresa, su
frontera es la planta.

[ADR-001: clasificación del sistema](docs/adr/ADR-001-clasificacion-mes-mom.md)

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Python + FastAPI + WebSockets |
| Base de datos | PostgreSQL (Alembic) |
| Frontend | React + TypeScript (Vite) |
| Tests | pytest + Vitest |
| Despliegue | Fly.io (backend) + Vercel (frontend) + GitHub Actions |

## Estado

✅ **Reconstrucción completa por fases (0-7).** Backend en
[steelworks-api.fly.dev](https://steelworks-api.fly.dev) con PostgreSQL
gestionado (migraciones + seed demo en el entrypoint) y frontend en Vercel
([steelworks.kavanasystems.com](https://steelworks.kavanasystems.com)) con
rewrites `/api/*`. CI verde en cada push: ruff + pytest + migraciones + build
TS + vitest.

### Qué incluye

- **Motor FIFO de bobinas**: cascada por fecha de entrada con burbuja de
  vinculación, herencia entre bobinas, JIT Move y tolerancia de superávit
  `max(15%, 150kg)`.
- **Reconciliación industrial**: retales medidos en milímetros de radio,
  merma oculta entre lo que el FIFO cree y lo que pesa la báscula, coste real
  por lote.
- **Fin de bobina**: el operario mide el radio en mm y el sistema calcula kg
  con densidad calibrada (7.7807 kg/dm³). Botón Retirar devuelve picos como
  sugerencia, nunca imposición.
- **OEE y KPIs**: disponibilidad, rendimiento y calidad con datos reales; sin
  datos muestra 0, nunca inventa.
- **Trazabilidad ISO 9001**: ProductionLog inmutable (trigger de UPDATE/DELETE)
  y timeline en el panel Supervisor.
- **Autocontroles de calidad** e **incidencias de planta** con evidencia
  fotográfica desde el móvil (sesión QR + validación magic bytes).
- **WebSockets de planta** (ADR-014) con fallback a polling.
- **Auth JWT 8h con roles** (operario, materiales, supervisor, admin) y
  **administración multi-tenant** (Fase 7): usuarios, secuencias, puestos,
  roles.
- **233+ tests backend** (pytest, incluye E2E contra PostgreSQL real y
  tests de aislamiento cross-tenant) **+ 71 frontend** (vitest), ejecutados
  en CI.

- **Asistentes IA con RAG sobre la documentación real** (2 bots sobre el mismo
  corpus): bot de **usuario** (`POST /api/v1/assistant/ask`) que explica el
  producto desde el punto de vista de planta, y **asistente técnico para
  reclutadores** (`POST /api/v1/assistant/ask-tech`) que responde arquitectura,
  decisiones (ADRs), seguridad y limitaciones documentadas. TF-IDF en memoria +
  OpenRouter; regla de honestidad: si no está en la documentación, lo dice.

Métricas verificables: los números reales se mantienen al día en el changelog
[`docs/audit/changelog.md`](docs/audit/changelog.md).

## 💰 Cómo está construido y cómo lo construiría con presupuesto

Este repo es una pieza de portafolio con **un solo usuario real: su autor**, y
está construido para costar ~0 €/mes. Esa restricción no es un detalle de
infraestructura: ha decidido el transporte de eventos, dónde viven las fotos,
el motor de búsqueda de los asistentes y el tamaño de la máquina. Aquí está
cada partida con lo que hay hoy, el porqué y qué cambiaría con usuarios reales
y presupuesto. El detalle completo, con alternativas descartadas, está en
[ADR-017](docs/adr/ADR-017-coste-cero-decisiones-presupuesto.md).

- **Cómputo:** la API corre en Fly.io en una máquina `cpu_kind = "shared"` de 1
  CPU y 256 MB con `min_machines_running = 0` y `auto_stop_machines = "stop"`,
  es decir, se apaga cuando nadie la usa (`fly.toml`). Con usuarios reales:
  réplicas mínimas fijas para eliminar el arranque en frío, más memoria y un
  entorno de staging separado de la demo.
- **Base de datos:** PostgreSQL gestionado con migraciones Alembic y CHECK
  reales, porque el dominio es relacional y el FIFO necesita transacciones
  atómicas (ADR-002). Es la pieza que no se ha recortado por precio. Con
  usuarios reales: el mismo motor, con backups, réplica de lectura y plan
  dimensionado.
- **Eventos de planta:** el `EventBroker` vive en memoria del proceso, así que
  el push de WebSockets funciona dentro de una única instancia (ADR-014,
  ADR-016). Con usuarios reales: Redis Pub/Sub o PostgreSQL LISTEN/NOTIFY detrás
  de la misma interfaz `publish/subscribe/consume`, sin tocar el dominio ni los
  clientes.
- **Migraciones y seed:** `alembic upgrade head` y el seed demo idempotente se
  ejecutan en el entrypoint del contenedor (`backend/docker-entrypoint.sh`), que
  es suficiente con una instancia. Con usuarios reales: mover las migraciones a
  un `flyctl release_command` y dejar el seed solo para la demo.
- **Fotos de incidencias:** se guardan como BYTEA en PostgreSQL
  (`incidencias.foto_data`), sin Cloudinary ni almacenamiento de objetos: el
  legacy usaba Cloudinary y no se portó. Con usuarios reales: object storage +
  CDN y liberar esos bytes de la base de datos, conservando el flujo de sesión
  de un solo uso por QR.
- **Asistentes RAG:** dos bots (usuario y técnico) con búsqueda TF-IDF en
  memoria, sin embeddings ni base vectorial, y LLM vía OpenRouter con modelo
  por defecto `:free`; los contadores anti-abuso (15 preguntas/día por IP y 500
  caracteres por pregunta) también viven en el proceso. Con usuarios reales:
  embeddings con pgvector o un índice gestionado, y rate limit en un almacén
  compartido para que valga con varias instancias.
- **Identidad:** JWT propio con roles (operario, materiales, supervisor, admin)
  y cuentas demo publicadas a propósito (`<rol>@demo.local`, password `kavana`)
  sobre datos ficticios; `SECURITY.md` dice explícitamente que no debe
  desplegarse con datos reales. Con usuarios reales: identidad corporativa
  (SSO/IdP), MFA, secretos por entorno y retirada de las cuentas de demo.
- **Verificación:** 233+ tests backend y 71 frontend corren en GitHub Actions
  (ruff + pytest + check de migraciones + build TS + vitest), pero los E2E
  contra PostgreSQL real (`backend/e2e_*.py`) se lanzan a mano en local, no en
  CI. Con usuarios reales: servicio PostgreSQL en el pipeline con los E2E dentro,
  pruebas de carga y observabilidad (APM y alertas); hoy la única señal en
  producción son `/health/live` y `/health/ready`.

**Lo que no cambia entre los dos escenarios** es el dominio y su verificación:
la cascada FIFO con burbuja de vinculación, la conversión radio→kg con densidad
calibrada (7.7807 kg/dm³), la guardia de seguridad `max(15%, 150kg)` antes de
descontar stock, el `ProductionLog` inmutable por trigger de PostgreSQL, la
validación de material por características (±2 mm de ancho, ±10 % de espesor) o
el aislamiento por tenant resuelto desde el JWT son decisiones de ingeniería,
no de factura; con un usuario o con cincuenta se implementan igual. Tampoco
cambian las specs extraídas del legacy, los ADRs, el changelog por fases ni la
suite de tests que los respalda: eso es lo que se puede verificar leyendo el
repositorio. Lo que sí cambiaría con presupuesto está escrito arriba y en
ADR-017, no escondido.

## Problemas conocidos / pendientes

- Capturas reales de la demo y post de LinkedIn (Fase 5 portfolio).
- Ver [`docs/audit/changelog.md`](docs/audit/changelog.md) para el detalle por
  fase y [`docs/decisions-log.md`](docs/decisions-log.md) para decisiones.

## Documentación

- [Índice de documentación](docs/README.md)
- [Historia de origen](docs/commercial/01-origen-sistema.md)
- [Decisiones de arquitectura](docs/adr/)
- [Registro de decisiones](docs/decisions-log.md)
- [Changelog](docs/audit/changelog.md)