# Changelog de trabajo — KAVANA MES/MOM

Registro de cambios por fase. Formato: problema, solución, archivos,
verificación. No documentar actividad por actividad: documentar fases con
narrativa de ingeniería.

## 2026-08-14 — Fase 0 (inicio): Estructura de documentación y clasificación

### Added: Clasificación del sistema (ADR-001)
- **Problema:** No estaba definido qué es el sistema (MES, MOM, ERP), y eso
  condicionaba todo el posicionamiento de portafolio.
- **Solución:** ADR-001 clasifica el sistema como MES con alcance MOM,
  especializado en transformación de bobinas de acero, con justificación
  basada en el estándar ISA-95 y las 4 actividades de operaciones.
- **Archivos:** `docs/adr/ADR-001-clasificacion-mes-mom.md`

### Added: Historia de origen del sistema
- **Problema:** El origen real del proyecto (operario de planta que vivió los
  problemas de papel/Excel/sistemas no automatizados) no estaba documentado.
- **Solución:** Narrativa de portafolio basada en la experiencia real de Jorge
  (8 años en metalurgia, CNC, turnos), marcada como borrador para revisión.
- **Archivos:** `docs/commercial/01-origen-sistema.md`

### Added: Índice maestro y plantilla de ADR
- **Problema:** No había estructura de documentación ni convención de ADRs.
- **Solución:** `docs/README.md` como índice maestro, `docs/adr/TEMPLATE.md`
  como plantilla obligatoria, estructura adr/commercial/technical/audit/deploy.
- **Archivos:** `docs/README.md`, `docs/adr/TEMPLATE.md`

### Added: Plan de reconstrucción v4
- **Problema:** La reconstrucción del proyecto no tenía plan escrito.
- **Solución:** Plan por fases (0-5) con stack objetivo aprobado por Jorge.
- **Archivos:** `docs/plan-reconstruccion-v4.md`
