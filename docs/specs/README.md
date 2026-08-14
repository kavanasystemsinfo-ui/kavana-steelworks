# Specs del dominio: KAVANA Steelworks

Resultado de la Fase 1: especificaciones extraídas del código legacy v2.
Cada spec documenta el contrato de comportamiento que la reconstrucción
(Fase 2, backend) debe implementar y testear. Los subagentes que las
extrajeron no modificaron el código legacy.

## Índice

| Spec | Módulo legacy | Contenido |
|---|---|---|
| [01-inventario-bobinas](01-inventario-bobinas.md) | `InventoryService.js` | Stock, bobinas, consumos FIFO, vinculación, retales |
| [02-ordenes-produccion](02-ordenes-produccion.md) | `OrderService.js` | Ciclo de vida de órdenes, líneas, estados |
| [03-oee-costes-kpis](03-oee-costes-kpis.md) | `OEEService.js`, `CalculationEngine.js`, `OrderCostCalculator.js`, `KPIService.js` | Eficiencia, costes, KPIs |
| [04-trazabilidad-calidad](04-trazabilidad-calidad.md) | `TraceabilityService.js`, `QualityService.js` | Trazabilidad ISO 9001, autocontroles |
| [05-otros-servicios](05-otros-servicios.md) | `MaintenanceService.js`, `StockAlertService.js`, `SequenceService.js`, `AuditLoggerService.js` | Incidencias, alertas, secuencias, auditoría |

## Formato de cada spec

1. **Fuente legacy**: rutas y archivos consultados.
2. **Entidades y relaciones**: qué se modela y cómo se relaciona.
3. **Operaciones clave**: firma, comportamiento, invariantes.
4. **Reglas de negocio críticas**: las que no se pueden perder en el portado.
5. **Casos límite conocidos**: errores y bordes que el v2 ya resolvió.
6. **Requisitos para el modelo relacional**: tablas, claves, constraints.

## Estado

- [x] 01-inventario-bobinas
- [x] 02-ordenes-produccion
- [x] 03-oee-costes-kpis
- [x] 04-trazabilidad-calidad
- [x] 05-otros-servicios

_Actualizado: 2026-08-14_
