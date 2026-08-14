# ADR-002 — Motor de base de datos: PostgreSQL sobre MongoDB

Estado: Aceptado
Fecha: 2026-08-14
Autor: Jorge Adán (KAVANA Systems)

## Contexto

El sistema v2 (legacy) usa MongoDB como base de datos. Al reconstruir el
proyecto en `kavana-steelworks`, hay que decidir si se mantiene Mongo o se
migra a un motor relacional.

El dominio es un MES/MOM metalúrgico: órdenes de producción, líneas, bobinas
de acero, consumos FIFO, transacciones de material, stock, mermas, costes
reales y OEE. Son datos con relaciones fuertes y consecuencias económicas
directas (los kilos deben cuadrar con la báscula física).

## Decisión

Usar **PostgreSQL** como base de datos del sistema reconstruido.

## Alternativas evaluadas

| Alternativa | Ventajas | Inconvenientes | Descartada por |
|---|---|---|---|
| **MongoDB (mantener)** | Sin migración; schema flexible; prototipado rápido | Sin integridad referencial; transacciones limitadas; sin migraciones ni validación; datos corruptos requieren scripts de reparación | El v2 acumuló 45 scripts `fix_*`/`debug_*` para reparar datos corruptos; los descuadres de stock y bobinas fantasma eran síntomas de falta de constraints |
| **PostgreSQL** | ACID real; claves foráneas; constraints y checks; migraciones versionadas; SQL potente para KPIs/OEE; estándar de la industria MES; coherencia con el v3 | Migración del modelo de datos | Es la opción elegida |
| **MySQL** | Similar a PostgreSQL | Menos features (JSONB, RLS, funciones avanzadas); el v3 ya usa PostgreSQL | No aporta nada sobre PostgreSQL |

## Consecuencias

- **Positivas**: los datos no pueden corromperse por referencias rotas; las
  operaciones FIFO son atómicas (consumo + stock + transacción + coste en una
  transacción); KPIs y OEE se calculan con SQL agregado; migraciones
  versionadas sustituyen a los scripts de reparación; coherencia técnica con
  el v3 (PostgreSQL + RLS).
- **Negativas**: el modelo de datos del v2 (esquemas Mongoose) debe traducirse
  a tablas relacionales con sus migraciones. Coste de portado acotado a la
  Fase 2 del plan.
- **Verificación**: las specs de la Fase 1 definen el modelo relacional; las
  migraciones se prueban contra PostgreSQL real en CI; los tests de dominio
  (FIFO, reconciliación) pasan contra la BD relacional.

## Referencias

- Código: modelo de datos en `backend/src/models/` del repo legacy v2.
- ADRs relacionados: ADR-001 (clasificación MES/MOM).
- Plan: `docs/plan-reconstruccion-v4.md`, Fases 1 y 2.
