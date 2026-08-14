# KAVANA Steelworks

MES/MOM para el sector metalúrgico: control de bobinas de acero, consumo FIFO,
reconciliación industrial, OEE y trazabilidad ISO 9001.

**Este repo es la reconstrucción moderna (v4) de un sistema legacy.** La lógica
de dominio única (bobinas, FIFO, reconciliación) proviene de años de
experiencia real en planta, y se está portando a un stack moderno con TDD,
ADRs y despliegue profesional.

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
| Base de datos | PostgreSQL |
| Frontend | React + TypeScript (Vite) |
| Tests | pytest + Vitest (TDD) |
| Despliegue | Docker + CI/CD |

## Estado

🚧 **En reconstrucción.** Este repo arranca con la documentación de base
(historia, ADR de clasificación, plan de fases) y se construye por fases con
TDD estricto. El código legacy de referencia vive en el repo privado
`kavanasystems` (v2).

[Ver plan de reconstrucción](docs/plan-reconstruccion-v4.md)

## Documentación

- [Índice de documentación](docs/README.md)
- [Historia de origen](docs/commercial/01-origen-sistema.md)
- [Decisiones de arquitectura](docs/adr/)
- [Registro de decisiones](docs/decisions-log.md)
- [Changelog](docs/audit/changelog.md)
