# Registro de decisiones estratégicas

Decisión estratégica, fecha, contexto y enlace al ADR o documento que la
desarrolla. Registro ligero de alto nivel, los detalles viven en los ADRs.

| Fecha | Decisión | Contexto | Documento |
|---|---|---|---|
| 2026-08-14 | Reconstruir el v2 como pieza estrella standalone del portafolio | El v2 contiene la lógica de dominio metalúrgica única (bobinas, FIFO) que no existe en el v3 | `docs/plan-reconstruccion-v4.md` |
| 2026-08-14 | Stack objetivo: FastAPI + PostgreSQL + React TS + WebSockets | Añadir Python serio al CV; no duplicar el stack NestJS del v3 | `docs/plan-reconstruccion-v4.md` |
| 2026-08-14 | Clasificar el sistema como MES/MOM metalúrgico | Duda de posicionamiento: no es ERP, es MES con alcance MOM (ISA-95) | `docs/adr/ADR-001-clasificacion-mes-mom.md` |
| 2026-08-14 | Repo nuevo limpio para la reconstrucción | El historial git del v2 contiene credenciales expuestas; purgar es arriesgado | `docs/plan-reconstruccion-v4.md` |
| 2026-08-15 | Trazabilidad ISO 9001 con ProductionLog inmutable vía trigger PostgreSQL | Auditoría: los logs de producción no deben poder modificarse ni borrarse (regla 1 spec 04); el trigger lo garantiza a nivel BD | `docs/specs/04-trazabilidad-calidad.md` |
