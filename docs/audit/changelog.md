# Changelog de trabajo — KAVANA Steelworks

Registro de cambios por fase. Formato: problema, solución, archivos,
verificación. No documentar actividad por actividad: documentar fases con
narrativa de ingeniería.

## 2026-08-17 — Fase 7: administración multi-tenant (spec 07 + ADR-015)

- **Problema:** la empresa demo no tenía panel de administración; el v2
  guardaba toda la configuración (roles, secuencias, puestos) en un JSON
  monolito dentro de Tenant.js. Había que normalizar las entidades
  consultables y exponerlas a un admin por tenant.
- **Solución (ADR-015, normalización del monolito):**
  - Modelos nuevos: `app/models/admin.py` (TenantRole con permisos
    granulares + catálogo, Sequence con prefix/padding/next_number,
    WorkstationGroup y Workstation con coste/hora y mantenimiento).
    `tenant.py` ampliado: slug único, status, auth/theme/finances/
    sequences_config como JSON; User con employee_number y
    default_workstation_code.
  - Servicio `app/services/sequences.py`: `next_sequence` con SELECT FOR
    UPDATE (mejora sobre el $inc de MongoDB) y `peek_sequence` (siguiente
    número sin consumir). Fix de concurrencia real: al crear la fila por
    primera vez, dos hilos concurrentes violaban el unique constraint;
    se resuelve con savepoint + recarga con FOR UPDATE (verificado con 10
    hilos en E2E contra PostgreSQL real).
  - Router `/api/v1/admin` (solo rol admin, tenant SIEMPRE del JWT):
    tenant GET/PUT, users CRUD (soft delete, sin auto-desactivación, puesto
    validado contra el tenant), sequences GET/PUT + GET next/{type},
    workstations CRUD + grupos, roles GET/PUT (solo custom editables; los
    del sistema son fijos y el seed los crea).
  - Migración `59bee63a26fb` con el patrón seguro add-column + backfill del
    slug + NOT NULL: validada upgrade → downgrade → upgrade en BD limpia
    contra PostgreSQL real.
  - Seed demo ampliado: _asegurar_workstations_demo (LINEA-1..3) y
    _asegurar_roles_demo (4 roles del sistema con permisos), idempotente.
  - Frontend: panel Admin con pestañas (Empresa, Usuarios, Secuencias,
    Puestos, Roles), ruta /admin, home del admin = /admin, nav visible solo
    para rol admin (matriz de roles espejo en lib/roles.ts).
- **Verificación:** 29 tests nuevos backend (221 total; suite completa
  verde), 10 tests frontend nuevos (67 total; suite completa verde),
  E2E `backend/e2e_admin.py` contra PostgreSQL real: seed → login admin →
  tenant/usuarios/secuencias/puestos/roles → 403 para no-admin y
  concurrencia de secuencias con 10 hilos y 10 números únicos. CI verde
  (ruff + pytest + build TS + vitest).

## 2026-08-16 — Fase 6: login y roles por panel (credenciales demo)

- **Problema:** la demo era pública sin login (decisión anterior) y el JWT
  existía pero ningún endpoint exigía token; no había forma de demostrar el
  multirol del sistema.
- **Solución (decisión de Jorge: credenciales fáciles, password `kavana`):**
  - `app/core/security.py`: `autenticar` (Bearer + JWT + revocación, 401) y
    `require_roles` (403 si el rol no corresponde), patrón Annotated.
  - TODOS los routers exigen token; matriz de permisos:
    - operario (operator): escaneo, vincular, fin de bobina, retirar,
      producción, autocontroles, crear incidencia y su foto.
    - materias (materials): recepción e inventario.
    - supervisor: OEE/KPIs, trazabilidad, órdenes, gestionar incidencias
      (y puede operar, demo).
    - admin: hereda supervisor.
    - Público sin token: solo login y subida de foto del móvil (el
      session_id es la credencial de un solo uso).
  - Seed: 4 usuarios demo `<rol>@demo.local` con password `kavana`,
    idempotente y REPARADOR (actualiza el password legacy `!demo`).
  - El tenant se resuelve del JWT en quality/supervisor/orders (antes "primer
    tenant", incorrecto con multi-tenant real). El polling QR del móvil
    resuelve su tenant desde la propia sesión (obtener_sesion_por_id).
  - Frontend: guard de rutas RequireRole (sin token → /login; sin acceso →
    home del rol), LoginPage con las cuentas demo visibles y redirección por
    rol, Layout con navegación filtrada por rol + botón Salir (logout).
    `lib/roles.ts` con la matriz espejo del backend.
  - `user_id` real del token conectado en recepción, producción, calidad,
    stock e incidencias (los TODOs del v2 ya no hacen falta: el operario
    queda registrado en Kardex/traza/historial).
- **Verificación:** 204 tests backend (192 unit + 3 E2E contra PG real con
  drop_all/create_all reproducibles), 57 tests frontend, ruff/oxlint/tsc
  limpios, CI local verde. Desplegado: Fly (steelworks-api) + Vercel manual.
  En producción: login 200 para los 4 roles, 401 sin token, 403 con rol
  incorrecto, 200 con rol correcto.

## 2026-08-16 — Endurecimiento de seguridad (auditoría con 5 subagentes)

- **Problema:** la demo era pública sin login y el JWT no estaba conectado al
  flujo HTTP; faltaba revisar secretos, dependencias y superficie de ataque
  antes de abrir la demo a cualquiera.
- **Solución (commits 2160721 + 04618aa):**
  - JWT secret fail-fast: `model_validator` exige `len >= 32` en producción;
    Fly ya tiene `STEELWORKS_JWT_SECRET`.
  - Logout por header `Authorization: Bearer` (antes query param) e
    idempotente (evita 500 por unique).
  - Subida de fotos anti-DoS: lectura en chunks con aborto 413 al superar
    10 MB (antes `foto.read()` cargaba todo el cuerpo).
  - Cabeceras de seguridad (nosniff, X-Frame-Options DENY, Referrer-Policy,
    HSTS) en middleware global.
  - Rate limit de subida con poda de IPs vencidas + uvicorn con
    `--proxy-headers` para que la IP real llegue tras el edge de Fly.
  - Límites en schemas Pydantic (max_length, ge=0, `limit` clampado a >=1).
  - `SECURITY.md` y `.env.example` nuevos.
- **Verificación:** sin secretos en git (`git rev-list --all` limpio), sin
  SQLi/XSS/SSRF/path traversal, CVE único `ecdsa@0.19.2` transitiva de
  python-jose no explotable con HS256, frontend 0 CVEs, 178 tests backend.

## 2026-08-15 — Fase 5: trazabilidad ISO 9001, calidad, incidencias y foto QR

### Added: trazabilidad ISO 9001 (spec 04 §3.1, commits fbeef02 + 93c47aa + 2f3bb03)
- **Problema:** no existía registro inmutable de la cadena de producción
  (quién, cuándo, qué, con qué bobina), requisito de la ISO 9001.
- **Solución:** modelo `ProductionLog` (11 acciones, metadata JSONB,
  índices tenant/orden/operario), TRIGGER de inmutabilidad en PostgreSQL
  (UPDATE/DELETE bloqueados), servicio `log_event` best-effort tipo DLQ que
  NUNCA rompe la planta, integrado en producción (produce), fin de bobina
  (scrap) y retirar pico (finish). Router GET /api/v1/trace/orders/{id} y
  UI de timeline en el panel Supervisor con selector de órdenes.
- **Pitfall resuelto:** la columna `metadata` choca con el MetaData de
  SQLAlchemy; usar `metadata_` en el ORM y serialización explícita.
- **Verificación:** E2E 7/7 contra PostgreSQL real (UPDATE/DELETE
  bloqueados), 4 tests frontend nuevos.

### Added: autocontroles de calidad (spec 04 §3.2, commits 8a9eb0f + 1a8dc1f)
- **Problema:** el operario no podía registrar los controles de calidad del
  modelo (largo, acabado, espesor) con sus tolerancias.
- **Solución:** modelos ManufacturingModel/QualityPlanCheck/QualityRecord/
  QualityMeasurement (columna `tipo`, no `type`: palabra reservada SQL),
  servicio portado del legacy con límites inclusivos, checks sin medición
  omitidos, rejected (crítico) nunca bloquea producción. Tarjeta de
  autocontrol en el panel Operario tras vincular bobina. Seed idempotente
  PERFIL-DEMO-001 con 3 controles.
- **Verificación:** 15 tests backend + 3 frontend, E2E contra PG real.

### Added: incidencias de planta con cierre financiero (spec 04 §3.3, commits 194f6cd + f87be8e + fixes)
- **Problema:** no había canal para reportar paradas/incidencias ni su
  impacto en el OEE.
- **Solución:** modelo Incidencia + IncidenciaHistorial con CHECK reales,
  nace en 'abierta', asocia la orden activa de la línea, cierre con
  responsable. OEE descuenta `tiempo_parada_min` como downtime
  (`total_downtime_min`). Formulario clásico en Operario (auto-importa
  operario, puesto, modelo, fecha) y gestión en Supervisor. La severidad NO
  existe (decisión de Jorge). 9 tests + E2E.

### Added: evidencia fotográfica por QR + móvil (spec 04 §3.3.2, commits 2db9162 + d627d73 + 2863af9 + 5b07203)
- **Problema:** el operario debía poder adjuntar foto de la incidencia desde
  el móvil sin sesión.
- **Solución:** SIN Cloudinary: foto como BYTEA en PostgreSQL con sesiones
  de un solo uso (TTL 15 min, estados pending/uploaded/used/expired).
  Flujo: POST /upload-session (PC) → QR → POST /upload-mobile/{id} público
  (validación magic bytes + 10MB + rate limit 20/10min) → polling → la foto
  se serializa como data URL. Decisión de producto: la foto es vía MÁS del
  formulario clásico (opcional, sin foto se reporta igual).
- **Verificación:** 131 tests backend + 21 frontend, CI verde, flujo
  verificado en producción con una foto real.

## 2026-08-15 — WebSockets de planta en tiempo real (ADR-014, commit efaf191)

- **Problema:** el panel hacía polling de eventos; la planta necesita push.
- **Solución:** router WS `/api/v1/ws/{tenant_id}` con autenticación
  opcional por token, reintentos con backoff en el cliente, y cola por
  tenant del broker. El polling sigue como fallback.
- **Verificación:** tests de conexión, token inválido/expirado/revocado
  (códigos 4404/4403), eventos push en tiempo real.

## 2026-08-15 — Fase 3: validación de material por características

### Added: `validar_material_compatible` (anexo A punto 8)

- **Problema:** faltaba la última pieza de la Fase 3: el sistema no sabía
  qué material gasta el modelo de la orden, así que podía vincular una
  bobina de otro tipo (galva en vez de decapado) o de dimensiones
  incompatibles. La visión de Jorge (anexo A, punto 8) lo prohíbe.
- **Solución:**
  - `OrderLine.material_id` (FK materials, nullable): la orden declara el
    material que gasta el modelo. Migración Alembic
    `d7e9f2c4a1b3_order_lines_material_id.py`.
  - `validar_material_compatible` en `app/services/inventory.py`, llamada en
    `link_coil` ANTES del cobro BULK:
    - Material distinto al declarado → bloquea ("Material incompatible").
    - Ancho fuera de ±2 mm del nominal → bloquea ("Ancho incompatible").
    - Espesor fuera de ±10 % del nominal → bloquea ("Espesor
      incompatible"); dentro de tolerancia comercial de laminación → permite.
    - Línea sin `material_id`: no valida (compatibilidad hacia atrás, la
      demo pre-existente sigue funcionando).
  - Seed demo actualizado: la línea OP-DEMO-001 declara el material
    ACERO-DC01, y el seed idempotente lo repara en despliegues existentes.
- **Verificación:** 6 tests TDD nuevos (test_material_compat.py: material
  correcto, otro material, ancho, espesor, tolerancia comercial, sin
  declarar), 69 tests backend totales, ruff limpio, migración validada
  desde cero contra PostgreSQL real (13 tablas), E2E real 5/5
  (e2e_material_compat.py).

## 2026-08-15 — Fase 3: producción con auto-consumo FIFO (recordProduction)

### Added: `record_production` (spec 02 3.4 + spec 01 3.12)
- **Problema:** faltaba el corazón del ciclo: registrar piezas y que el FIFO
  consuma el material automáticamente, con trazabilidad real por lote.
- **Solución:** servicio `app/services/production.py`:
  - Cálculo de kg por pieza: `density_formula` (ancho/espesor del lote,
    largo de `meters_per_piece`, densidad calibrada Kavana 7.7807 kg/dm³ ×1000)
    con fallback `meters_legacy` y `bom_static` (spec 01 3.12).
  - Modo auditoría (línea con bobina activa): consume por burbuja de
    vinculación + bobina prioritaria (`consume_stock_fifo` con contexto de
    producción: `produced_quantity`, `kg_por_pieza`, `calculation_method`,
    `tipo auto_audit`); el fallo de deducción BLOQUEA la producción.
  - Modo simple (sin bobina): FIFO global; el fallo NO bloquea (produce sin
    descuento, nunca consumos fantasma).
  - GUARDIA DE SEGURIDAD (evaluada ANTES de descontar stock, porque
    `consume_stock_fifo` hace commit interno): kilos teóricos acumulados no
    pueden superar los reales vinculados + max(15%, 150 kg).
  - WIP waterfall entre líneas en cascada; `produced >= total` → línea
    `completed`; `real_time` en minutos; roll-up de coste de la orden.
  - Nuevo endpoint POST /api/v1/production/record.
- **Verificación:** 8 tests TDD (rol operator, cantidad/horas, consumo por
  burbuja con density_formula, modo simple tolerante, auto-complete,
  guardia de seguridad, WIP, horas), 56 tests backend totales, ruff limpio.
  E2E contra PostgreSQL real: bobina 800 kg, 10 piezas → 9,49 kg consumidos
  (density_formula), MaterialConsumo auto_audit, fin de bobina por radio
  (queda 626,43 kg en puesto, 164,08 kg merma), retirar a 'Retales'.
- Migración Alembic `c4a9f2e7d1b3` (real_time en order_lines).

### Changed: frontend panel de operario (producción real)
- El botón "Registrar producción" ahora es un formulario: piezas (+ horas
  opcional) que llama a /api/v1/production/record y muestra el resultado
  (piezas, kg consumidos, método). Botón "Desvincular bobina" secundario.
- **Verificación:** 8 tests vitest (2 nuevos: panel post-vincular con radio
  + Retirar, y llamada real a /api/v1/production/record), tsc limpio, build PWA.

### Totales tras el cambio
- 56 tests backend + 8 tests frontend, ruff limpio, CI con los dos jobs.
- Archivo de verificación: `backend/e2e_produccion.py`.

## 2026-08-15 — Fase 3: panel Supervisor con OEE y KPIs (spec 03, adaptado al v2)

### Added: servicio OEE y KPIs + endpoints
- **Problema:** el panel de Supervisor mostraba '--' (datos simulados); la spec
  03 depende de modelos legacy no portados (ProductionLog, Incidencia, Tooling,
  UserShift).
- **Solución:** `app/services/oee_kpis.py` con los datos reales del v2:
  - OEE = A × P × Q: disponibilidad (real_time vs turno 480 min), rendimiento
    (produced/total), calidad (material bueno/material total). Clamp a 100,
    sin datos → 0 (nunca inventar, AUDIT FIX 2.3).
  - KPIs financieros: coste real vs estimado, varianzas, eficiencia (invertida),
    tasa de merma. Sin costes → 0 (sin división por cero).
  - Endpoints GET /api/v1/supervisor/oee y /kpis (tenant del token en Fase 4;
    demo usa el primer tenant).
- **Verificación:** 5 tests TDD, E2E contra PostgreSQL real: vincular → producir
  10 piezas con 2 h → OEE A=25% P=20% Q=100% → 5%, KPIs con 1 orden activa.

### Changed: frontend panel Supervisor conectado
- `SupervisorPage` llama a los endpoints reales (polling 10 s): tarjeta OEE
  grande con A/P/Q, KPIs de turno (producción, merma, varianza de coste,
  eficiencia), detalle de órdenes y tasa de merma.
- **Verificación:** 2 tests vitest (datos reales cargados + sin datos no
  inventa), tsc limpio, build PWA.

### Totales tras el cambio
- 63 tests backend + 10 tests frontend, ruff limpio, CI con los dos jobs.
- Archivo de verificación: `backend/e2e_supervisor.py`.

## 2026-08-15 — Fase 4: despliegue demo (Fly.io + Vercel + PostgreSQL)

### Added: backend en Fly.io (steelworks-api)
- **Decisión:** Fly.io + PostgreSQL gestionado (patrón BusRoad verificado; el VPS
  es laboratorio, no producción — estándar KAVANA 2026-08-05). La BD es
  PostgreSQL real con los CHECK constraints que el modelo exige.
- **Infra:** Dockerfile python:3.12-slim, fly.toml (machines, region cdg,
  256mb), entrypoint que aplica migraciones + seed + uvicorn. App `steelworks-api`,
  clúster `steelworks-db` (shared-cpu-1x, 1 GB), attach con secret DATABASE_URL.
- **Config:** `config.py` acepta `DATABASE_URL`/`JWT_SECRET` estándar (alias
  STEELWORKS_*) y normaliza `postgres://` → `postgresql+psycopg://`.
- **Seed demo:** `app/services/seed_demo.py` idempotente (tenant Demo Aceros +
  material ACERO-DC01 + bobina COIL-DEMO-001 + orden + operario), 2 tests.
- **Verificación:** health OK, materials con datos reales, scan de
  COIL-DEMO-001 devuelve la ficha completa (800 kg, 1220×1,2 mm).

### Added: frontend en Vercel (steelworks-kavana)
- `vercel.json` con rewrites `/api/*` → steelworks-api.fly.dev + fallback SPA.
- CORS del backend incluye el dominio final y el de Vercel.
- Dominio `steelworks.kavanasystems.com` añadido en Vercel (CNAME
  `c656b0c70cfddc43.vercel-dns-017.com.` en Namecheap, pendiente propagación).
- **Verificación:** frontend 200 en Vercel, rewrite /api/* con datos reales.

### URLs de la demo (verificadas)
- App: https://steelworks-kavana.vercel.app (final: steelworks.kavanasystems.com)
- API: https://steelworks-api.fly.dev/health

## 2026-08-15 — Fase 3: fin de bobina corregido (radio→kg, fórmula v2) + botón Retirar

### Added: port de la fórmula v2 radio→kg (coil_math)
- **Problema:** el `create_retal` anterior pedía al operario los kg que
  quedaban; en planta NO se puede pesar una bobina montada en la máquina.
  La fórmula v2 (legacy coilMath.js, verificada por Jorge en fábrica) solo
  existía en JavaScript.
- **Solución:** módulo `app/services/coil_math.py` con `peso_desde_radio_mm`
  (π·(R_ext²−R_int²)·ancho·densidad), Densidad Calibrada Kavana 7.7807 kg/dm³
  (Decisión 92) como default, mandril 508 mm. Redondeo a 2 decimales.
- **Verificación:** 7 tests unitarios con valores de referencia del legacy
  (radio 500/ancho 1000 → 12.319,67 kg; radio 250/ancho 122 → 565,12 kg);
  radio 0 → 0; sin ancho → ValueError explícito.

### Changed: `create_retal` mide milímetros de radio (no kg)
- **Problema:** la implementación anterior contradecía el modelo de Jorge
  (medir kg directos, tratar el sobrante como merma, mover el pico a
  'Retales' siempre).
- **Solución:** `create_retal` recibe `radio_mm`, convierte con la fórmula v2
  usando el ancho de la bobina y la densidad calibrada del material. La merma
  invisible sigue siendo la reconciliación FIFO-vs-medición (ISO 9001,
  merma_puntas + Kardex ajuste). El SOBRANTE NO es merma: queda como pico
  EN EL PUESTO (misma ubicación), material FIFO para el siguiente turno.
  Reembolso a la línea de lo que deja de estar comprometido. Endpoint
  POST /stock-items/fin-bobina con `radio_mm`.
- **Verificación:** tests reescritos al nuevo contrato (8), E2E contra
  PostgreSQL real: bobina 800 kg, consumidos 300, radio 200 mm → 422,27 kg
  restantes, 77,73 kg de merma, pico en 'LINEA-1'.

### Added: botón "Retirar" (segunda opción del fin de bobina)
- **Problema:** faltaba la segunda opción que Jorge describió: devolver el
  pico al inventario cuando el material no se va a gastar (pasa a otra orden
  de otro material).
- **Solución:** `retirar_pico`: mueve la bobina a ubicación 'Retales' con
  estado pico/es_pico, desvincula la línea activa si sigue vinculada
  (reembolso), y registra traslado en Kardex. Endpoint POST /stock-items/retirar.
  `/picos` ahora solo sugiere picos del almacén (ubicación 'Retales'), no los
  que siguen en la máquina.
- **Verificación:** 3 tests (retirar a inventario, error sin material,
  filtro de sugerencias), E2E real: pico en puesto no sugerido → tras
  retirar aparece en /picos con 422,27 kg.

### Changed: frontend panel de operario
- Formulario de fin de bobina pide "Radio restante (mm)" (input step 0,5,
  min 0) y muestra el resultado con kg restantes + merma. Botón secundario
  "Retirar pico a inventario" llama a /stock-items/retirar.
- **Verificación:** 6 tests vitest, `tsc --noEmit` limpio, build PWA OK.

### Totales tras el cambio
- 48 tests backend (37 previos + 11 nuevos: 7 coil_math + 3 retirar/picos +
  1 reescrito), 6 tests frontend, ruff limpio, CI con los dos jobs.
- Archivo de verificación: `backend/e2e_radio_retirar.py` (usa PostgreSQL
  real del contenedor de test, nunca toca la BD del VPS).

## 2026-08-14 — Fase 2 (backend): base FastAPI + motor FIFO con TDD

### Added: Proyecto FastAPI con estructura modular
- **Problema:** no existía backend en el repo nuevo; había que arrancar con
  bases profesionales (uv, SQLAlchemy 2.0, tests desde el día uno).
- **Solución:** proyecto con `uv`, estructura `app/core|models|services|tests`,
  configuración vía pydantic-settings, motor SQLAlchemy con pool_pre_ping.
- **Archivos:** `backend/pyproject.toml`, `backend/app/core/*`
- **Verificación:** `uv run pytest` 6 tests verdes; `uv run ruff check` limpio.

### Added: Modelo relacional (9 tablas)
- **Problema:** portar 22 modelos Mongoose a un esquema relacional con
  integridad real (ADR-002).
- **Solución:** 9 tablas: tenants, users, materials, stock_items, orders,
  order_lines, material_transactions (Kardex inmutable), material_consumos,
  coil_links (burbuja de vinculación explícita, mejora estructural del v4).
  Constraints, FKs, UUID v4 como PK.
- **Archivos:** `backend/app/models/*`
- **Verificación:** `Base.metadata.tables` = 9 tablas importadas sin error.

### Added: Motor de consumo FIFO con TDD (corazón del sistema)
- **Problema:** la lógica de bobinas del v2 (InventoryService, 810 líneas)
  era el activo más valioso y no tenía tests.
- **Solución:** `consume_stock_fifo` implementado con TDD estricto (rojo →
  verde): cascada FIFO por fecha_entrada ASC con herencia entre bobinas,
  burbuja de vinculación en modo auditoría (solo coil_links + bobina
  prioritaria), bobinas fantasma no elegibles, coste real por lote, registro
  de MaterialConsumo con auditoría, error 409-equivalente en stock
  insuficiente.
- **Archivos:** `backend/app/services/inventory.py`, `backend/tests/test_fifo_*`
- **Verificación:** 6 tests verdes (contrato, burbuja, errores).

### Nota de ingeniería
El guard de seguridad de kilos (`max(15%, 150kg)`) y el cobro BULK de
`linkCoil` se implementan en la siguiente iteración de la Fase 2 (spec 01,
secciones 3.3 y D).

## 2026-08-14 — Fase 2 (continuación): recepción, feature flags, Alembic y CI

### Added: Módulo de Materias Primas (recepción) con TDD
- **Problema:** el rol de recepción no existía; el operario tecleaba peso y
  lote a mano. La investigación de industria confirmó el flujo estándar
  (ASN → recepción → GRN → lote → etiqueta → putaway).
- **Solución:** `receive_coil` (alta de bobina activa + Kardex GRN + stock
  padre), `build_label` (etiqueta QR escaneable), `move_coil` (putaway con
  traslado en Kardex). Campos estándar de bobina: heat_number, grado_acero,
  supplier_coil_id, parent_coil_id.
- **Verificación:** 6 tests nuevos (16 total verdes).

### Added: Sistema de planes con feature flags (ADR-003)
- **Problema:** cada planta necesita distinto nivel de automatización.
- **Solución:** `TenantFeature` (JSONB) + catálogo de 12 features + 3 planes
  (básico/pro/industrial), patrón replicado del v3.
- **Verificación:** PLANES con features correctas por nivel.

### Added: Alembic + CI
- **Problema:** sin migraciones versionadas ni pipeline.
- **Solución:** Alembic con migración autogenerada, aplicada y verificada
  contra PostgreSQL real (11 tablas). CI en GitHub Actions: uv + ruff +
  pytest + check de migraciones. Primer run: success.
- **Verificación:** `\dt` en postgres:16 real; `gh run view` success.

## 2026-08-14 — Fase 2 (cierre): Auth JWT y WebSockets

### Added: Autenticación JWT (spec 05)
- **Problema:** faltaba la sesión de 8 horas (un turno) con invalidación
  server-side que el v2 ya tenía.
- **Solución:** `auth.py` con login (JWT 8h), bcrypt directo (passlib roto
  con bcrypt 4.x), logout con RevokedToken, UserShift con un turno activo.
  Modelos `revoked_tokens` y `user_shifts`.
- **Verificación:** 4 tests nuevos; migración aplicada en PostgreSQL real.

### Added: Broker de eventos WebSocket (spec 05)
- **Problema:** los eventos de planta (consumo, stock_deficit, downtime)
  necesitaban canal por tenant.
- **Solución:** `EventBroker` en memoria con cola por tenant y límite;
  endpoint GET /api/v1/events/{tenant_id} para polling; WebSocket completo
  en la Fase 3.
- **Verificación:** 3 tests nuevos (23 total verdes); CI success.

## 2026-08-14 — Fase 3 (hito 1): Frontend React+TS con design system KAVANA

### Added: Frontend con directriz UX de Jorge
- **Problema:** no existía interfaz; había que aplicar la directriz "esencia
  brutalista pero sin abrumar al operario".
- **Solución:** Vite + React 19 + TS + Tailwind v4 con tokens del design
  system v2 (deep black #050505, orange #E56B2E, Montserrat uppercase, mono
  para datos físicos, botones táctiles ≥48px, step-guide de acción).
  Páginas: Login (JWT), Operario (escaneo con guía de acción y datos
  colapsados), Materias Primas (recepción spec 06), Supervisor (KPIs).
  PWA offline-first (network-first navigation).
- **Verificación:** 5 tests vitest sobre la directriz UX; build 263KB/82KB
  gzip; CI con job frontend verde.

### Added: Routers de la API (backend)
- **Problema:** el frontend llamaba a endpoints que no existían.
- **Solución:** POST /api/v1/auth/login y /logout (JWT 8h), POST/GET
  /api/v1/stock-items (receive_coil + listado). Usuario 'system' para
  movimientos automáticos. Seed de demo (operario@demo.local/kavana123).
- **Verificación:** E2E contra PostgreSQL real: login 200, recepción 200,
  listado 200.

### Added: Frontend conectado a la API (f3-4)
- **Problema:** los paneles usaban datos simulados; no hablaban con el backend.
- **Solución:** cliente API tipado (`lib/api.ts`) con decodificación del JWT
  para tenant_id; LoginPage real; MateriasPrimasPage carga materiales y
  registra bobinas; OperarioPage hace polling de eventos (WebSocket completo
  en Fase 4) y muestra "Alertas de almacén". Endpoints nuevos: materiales
  activos y sugerencia de picos (`GET /stock-items/picos`), que implementa la
  idea de Jorge: aconsejar usar picos del almacén antes de abrir bobina
  nueva, como sugerencia visible y nunca imposición.
- **Verificación:** E2E extendido (login, materiales, recepción, picos con 1
  sugerencia real, evento recepcion_material visible); CI verde con los dos
  jobs.

### Added: Flujo de escaneo y vinculación del operario (anexo A)
- **Problema:** el panel de operario tenía el escaneo simulado; no buscaba
  bobinas reales ni las vinculaba a la orden.
- **Solución:** `find_coil` (escaneo por coil_id o lote con material,
  dimensiones y peso, modo automático) y `link_coil` (vinculación con cobro
  BULK por adelantado, idempotente, reubicación JIT con Kardex, spec 01
  3.6). Endpoints GET /stock-items/scan y POST /stock-items/link. El panel
  muestra la ficha de la bobina escaneada con "Vincular a mi orden".
- **Verificación:** 9 tests nuevos backend (32 total), 6 tests frontend del
  flujo escaneo→ficha, E2E contra PostgreSQL real (scan por coil_id, por
  lote e inexistente), CI verde.

### Added: Fin de bobina con reconciliación de merma (spec 01 3.9)
- **Problema:** faltaba el cierre del flujo del operario: medir los
  milímetros de radio restantes de la bobina y calcular la merma real
  (la visión de Jorge).
- **Solución:** `create_retal`: el operario mide los kg físicos, el sistema
  compara con lo que el FIFO cree que queda; la diferencia es merma
  invisible (MaterialConsumo merma_puntas con reconciliation ISO 9001); el
  sobrante real vuelve a inventario como retal en 'Retales' o agota la
  bobina; reembolso a la línea y merma a scrap. Endpoint POST
  /stock-items/fin-bobina y formulario en el panel del operario.
- **Verificación:** 5 tests nuevos (37 total), E2E contra PostgreSQL real:
  bobina de 800 kg, operario mide 420 → 380 kg de merma (399 €), retal en
  'Retales', línea con scrap y sin bobina activa. CI verde.

