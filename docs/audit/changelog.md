# Changelog de trabajo — KAVANA Steelworks

Registro de cambios por fase. Formato: problema, solución, archivos,
verificación. No documentar actividad por actividad: documentar fases con
narrativa de ingeniería.

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

