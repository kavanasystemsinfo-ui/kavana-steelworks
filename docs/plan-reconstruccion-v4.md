# PLAN: Reconstrucción KAVANA MES v2 → v4 (Pieza estrella metalúrgica)

Fecha: 2026-08-14
Estado: Aprobado por Jorge (stack + rol). En ejecución por fases.

## Objetivo

Reconstruir el MES metalúrgico (repo `kavanasystems`, v2 legacy) como proyecto
standalone moderno y profesional, pieza central del portafolio de Jorge.
Preservar y portar la lógica de dominio única (bobinas, FIFO, reconciliación
industrial, OEE, mermas) que NO existe en el v3 (`kavana-manufacturing`).

## Stack objetivo (decisión Jorge 2026-08-14)

| Capa | Tecnología | Por qué |
|---|---|---|
| Backend | Python + FastAPI | Añade Python serio al CV, muy cotizado |
| BD | PostgreSQL | Relacional, ya conocido en ecosistema Kavana |
| Tiempo real | WebSockets | Mismo modelo de eventos que el v2 (Socket.io → WS) |
| Frontend | React + TypeScript (Vite) | Sube el frontend a TS sin cambiar de ecosistema |
| Tests | pytest (backend) + Vitest (frontend) | ADN KAVANA: TDD obligatorio |
| Despliegue | Docker + CI/CD + servicio cloud | Nuevo despliegue para portafolio |

## Inventario del v2 (auditoría 2026-08-14)

### Lo que se porta (lógica de dominio, ~7.800 líneas)
- `InventoryService.js` (810): consumeStockFIFO, linkCoil, switchCoil, unlinkCoil,
  createRetal, createVirtualCoil, addStock, consumeFromSpecificLot, findLotByCode
- `OrderService.js` (1.519): ciclo de vida de órdenes de producción
- `CalculationEngine.js` (238), `OrderCostCalculator.js` (144): costes
- `OEEService.js` (296), `KPIService.js` (191): eficiencia y KPIs
- `TraceabilityService.js` (82): trazabilidad ISO 9001
- 22 modelos Mongoose → esquemas PostgreSQL (Tenant, Order, Material,
  MaterialConsumo, MaterialTransaction, ProductionLog, StockItem, Tooling,
  QualityRecord, UserShift, ManufacturingModel...)
- 25 rutas / 23 controllers → routers FastAPI + esquemas Pydantic

### Lo que se descarta (~350 MB)
- `_ASSETS_Y_MARKETING/` (204 MB), `testsprite_tests/` (140 MB)
- 45 scripts one-off en raíz de `backend/` (fix_*, debug_*, diagnose_*, verify_*)
- Prototipos HTML sueltos (`operator_dashboard_prototype.html`, etc.)
- 8 archivos `.bat` de Windows, CSVs de importación
- `salesforce/`, `remotion/`, `tools/` (no pertenecen al MES)
- `credenciales mongo.txt`, `backend/.env.production` (SECRETOS → rotar y purgar)

## Fases

### Fase 0: Saneamiento y seguridad
- Backup de basura a /tmp (nunca rm a ciegas)
- Rotar credenciales MongoDB expuestas + purgar del historial git
- Decidir repo destino (nuevo repo limpio vs rama)
- Documento de auditoría archivo por archivo

### Fase 1: Especificación del dominio (context-first)
- Extraer specs de los services: FIFO, reconciliación, OEE, costes, turnos
- Documentar contratos de datos (modelos → esquemas)
- ADR del nuevo stack y de cada decisión de portado

### Fase 2: Backend FastAPI
- Esquemas PostgreSQL + migraciones
- Servicios portados con TDD estricto (pytest)
- WebSockets para eventos dashboard ↔ puesto
- Auth JWT, multi-tenant por tenantId

### Fase 3: Frontend React + TS
- Paneles: Operario (tablet, escaneo), Supervisor (un vistazo, OEE), Admin
- PWA offline-first (como RouteAI)
- Portar Design System KAVANA (brutalismo industrial)

### Fase 4: Despliegue y CI/CD
- Docker multi-stage + docker-compose
- GitHub Actions: tests + build + deploy
- Servicio cloud (a decidir: Railway/Fly.io/VPS k3s) + dominio
- Verificación de despliegue real

### Fase 5: Portfolio
- README honesto con métricas reales
- ADRs + DECISIONS.md
- Landing/case study del proyecto
- Post de LinkedIn anunciándolo

## Reglas de trabajo
- ADN KAVANA: kavana-tdd-kit, TDD, YAGNI, aprobación humana en UX/contenido
- Documentar en `docs/audit/changelog.md` y `docs/decisions-log.md`
- Commits por fase con mensajes descriptivos ($commit)
- Nada de credenciales en git; secrets en entorno
