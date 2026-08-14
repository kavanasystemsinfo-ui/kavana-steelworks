# DECISIONS.md — KAVANA Steelworks

Documento de decisiones técnicas del proyecto. El embudo CV → Landing →
GitHub debe contar la misma historia: cada decisión aquí tiene su ADR y su
código verificable en este repositorio.

## ADRs

| # | Decisión | Archivo |
|---|---|---|
| 001 | Clasificación MES/MOM (ISA-95), no ERP | [ADR-001](docs/adr/ADR-001-clasificacion-mes-mom.md) |
| 002 | PostgreSQL sobre MongoDB | [ADR-002](docs/adr/ADR-002-postgresql-sobre-mongodb.md) |
| 003 | Feature flags por plan (básico/pro/industrial) | [ADR-003](docs/adr/ADR-003-feature-flags-planes.md) |

## Decisiones de implementación (Problema → Decisión → Por qué → Trade-off)

### Motor FIFO con burbuja de vinculación
**Problema:** en planta, cada puesto acumula bobinas de turnos anteriores;
consumir la bobina equivocada rompe el coste y el stock.
**Decisión:** cascada FIFO por fecha de entrada restringida a la burbuja de
vinculación (bobinas explícitamente vinculadas a la orden + la prioritaria).
**Por qué:** es el comportamiento que el legacy ya resolvía y que hace que los
kilos cuadren con la báscula.
**Trade-off:** el modo auditoría exige mantener la tabla `coil_links`
consistente; el modo simple (sin burbuja) se mantiene para plantas pequeñas.

### PostgreSQL en vez de MongoDB
**Problema:** el legacy usaba MongoDB y arrastraba 45 scripts `fix_*` por
datos corruptos; el dominio es altamente relacional (órdenes, bobinas,
consumos, stock).
**Decisión:** PostgreSQL con SQLAlchemy 2.0, migraciones Alembic y
constraints (CHECK) para kilos y dinero.
**Por qué:** transacciones atómicas para el FIFO (consumir + decrementar +
Kardex en una sola operación) y coherencia con el ecosistema Kavana.
**Trade-off:** Mongo solo tendría sentido con telemetría masiva o esquemas
impredecibles, que no es este caso.

### Feature flags por plan
**Problema:** cada planta necesita un nivel de automatización distinto; el
v3 ya resolvía esto con feature flags JSONB.
**Decisión:** catálogo de 12 features con 3 planes (básico, pro, industrial)
en `app/core/features.py`, persistido en `tenant_features`.
**Por qué:** mismo código para todas las plantas, cada una paga y usa solo lo
que necesita. Patrón probado en el ecosistema Kavana.
**Trade-off:** hay que gobernar las features (dos son obligatorias: Kardex y
recepción simple, porque apagarlas rompería la trazabilidad).

### TDD contra specs extraídas del legacy
**Problema:** portar 7.800 líneas de lógica sin perder comportamiento.
**Decisión:** extraer specs del contrato (9 documentos en `docs/specs/`) y
escribir cada servicio con tests rojos primero; CI ejecuta la suite en cada
push.
**Por qué:** el portado no pierde lógica por el camino y el reclutador puede
verificar los tests contra las specs.
**Trade-off:** el proceso de extracción es lento al inicio, pero evita los
regresiones que el legacy arrastraba.

## Por qué existe este documento

El CV de Jorge, esta landing y este repositorio cuentan la misma historia:
un MES nacido de 8 años en metalurgia, reconstruido con un stack moderno,
decisiones documentadas y tests que lo demuestran.

Números verificados (2026-08-14): 28 tests (23 pytest + 5 vitest) · 3 ADRs ·
9 specs · 13 tablas PostgreSQL.
