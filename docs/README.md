# Documentación: KAVANA MES/MOM Metalúrgico

Índice maestro de la documentación del sistema. Este proyecto documenta tanto
el **por qué** (historia, decisiones) como el **qué** (arquitectura, módulos,
operación). La regla es: si no está documentado aquí, no existe para el
portafolio.

## Estructura

| Carpeta | Contenido | Para quién |
|---|---|---|
| `adr/` | Decisiones de arquitectura (Architecture Decision Records) | Ingenieros, reclutadores técnicos |
| `commercial/` | Historia de origen, casos de estudio, narrativa de negocio | Reclutadores, clientes |
| `technical/` | Documentación técnica por módulos, esquemas, flujos | Ingenieros |
| `audit/` | Auditorías, changelog por fases | Todo el equipo |
| `deploy/` | Guías de despliegue y operación | DevOps, despliegues |

## Mapa de documentos

### Historia y posicionamiento
- [Origen del sistema](commercial/01-origen-sistema.md): por qué existe, la historia del operario de planta
- [ADR-001: Clasificación MES/MOM](adr/ADR-001-clasificacion-mes-mom.md): qué es este sistema y qué no es

### Decisiones de arquitectura (ADR)
Cada decisión no trivial queda registrada en `adr/ADR-NNN-titulo.md` con:
contexto, decisión, alternativas evaluadas y consecuencias. Índice:

| ADR | Título | Estado |
|---|---|---|
| 001 | Clasificación del sistema: MES/MOM especializado en metalurgia | Aceptado |

### Documentación técnica
- `documentacion tecnica oficial/ESQUEMA_RECONCILIACION.md`: motor FIFO y reconciliación (legacy, se migrará)
- `_KAVANA_SYSTEMS_DOCS/`: documentación histórica del desarrollo v2 (referencia legacy)

### Registros de trabajo
- `docs/audit/changelog.md`: cambios por fase (problema, solución, archivos, verificación)
- `docs/decisions-log.md`: decisiones estratégicas a lo largo del tiempo

## Convención de ADRs

1. Numeración correlativa: `ADR-001`, `ADR-002`, ...
2. Nombre de archivo: `ADR-NNN-titulo-corto-con-guiones.md`
3. Estado: Propuesto → Aceptado → Reemplazado/Superseded
4. Estructura obligatoria: Contexto → Decisión → Alternativas evaluadas → Consecuencias
5. Toda decisión con alternativas descartadas documenta el porqué de cada descarte
6. Un ADR se escribe **antes** de implementar, no después
7. Referencia cruzada: el README del repo enlaza los ADRs principales

## Estado de la documentación

- [x] Historia de origen
- [x] Clasificación del sistema (ADR-001)
- [ ] ADR-002: Stack de reconstrucción (FastAPI + PostgreSQL + React TS)
- [ ] ADR-003: Modelo de datos PostgreSQL (portado de Mongoose)
- [ ] Documentación técnica por módulos (en reconstrucción)
- [ ] Guía de despliegue (Fase 4)

_Última actualización: 2026-08-14_
