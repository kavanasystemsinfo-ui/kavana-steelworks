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
