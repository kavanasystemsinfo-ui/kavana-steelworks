# Changelog de trabajo — KAVANA Steelworks

Registro de cambios por fase. Formato: problema, solución, archivos,
verificación. No documentar actividad por actividad: documentar fases con
narrativa de ingeniería.

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

