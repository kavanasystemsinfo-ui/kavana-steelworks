# KAVANA Steelworks

MES/MOM para el sector metalúrgico: control de bobinas de acero, consumo FIFO,
reconciliación industrial, OEE, calidad y trazabilidad ISO 9001. Desplegado en
producción como demo (Fly.io + Vercel) y construido con TDD estricto.

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
| Tests | pytest + Vitest (TDD) |
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
- **297 tests** (226 pytest + 71 vitest) contra el contrato de las specs,
  ejecutados en CI.

Métricas verificables: los números reales se mantienen al día en el changelog
[`docs/audit/changelog.md`](docs/audit/changelog.md).

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