# Principios visuales: KAVANA Steelworks

Estado: Borrador aprobado por Jorge (2026-08-14), aplicable en Fase 3
(frontend).

## Directriz de Jorge

> Mantener la esencia visual del sistema (brutalismo industrial KAVANA) pero
> hacerla más fácil de entender para el operario. Que no se sienta abrumado,
> sin quitar capacidad de funcionalidades.

## Qué se mantiene (esencia KAVANA)

- **Brutalismo industrial**: radios `rounded-sm`, tipografía de alto contraste
  (Montserrat, `font-black`, `uppercase`), acento Naranja Industrial `#E56B2E`,
  carbono mate, cobre metálico y neon green para estados críticos.
- **UI no bloqueante**: nada de `window.alert`/`confirm`, notificaciones
  asíncronas (toasts). El operario nunca pierde el hilo de su trabajo.
- **Poka-yoke táctil**: botones grandes (≥48px), flujos de escaneo con
  verificación, teclado táctil, consola pensada para tablets y guantes.
- **Filosofía "Un vistazo, un clic"**: el supervisor lee el estado de la planta
  sin navegar; el operario llega a su acción en un toque.

## Qué se mejora (no abrumar al operario)

| Problema detectado | Mejora |
|---|---|
| Demasiada información simultánea en la consola | Jerarquía visual clara: la acción principal del momento domina la pantalla; el resto queda en segundo plano visual |
| Muchos datos técnicos visibles a la vez | Agrupación por bloques con títulos; los datos de apoyo se colapsan o se muestran solo en contexto |
| Estados ambiguos (¿qué hago ahora?) | Guía de acción visible: el siguiente paso siempre identificable (color, posición, etiqueta) |
| Ruido de alertas | Alertas por severidad y por rol: solo lo relevante al puesto actual |
| Texto denso | Lenguaje de fábrica, corto y directo; unidades industriales claras (kg, m, uds/h) |

## Regla de oro

La simplificación nunca elimina funcionalidad: reorganiza, jerarquiza y
oculta por contexto. Si una función existía en el v2, existe en el v4.

## Referencias

- KAVANA_DESIGN.md (repo legacy v2): design system completo.
- ADR-004 del v3 (UX tunnel vision): referencia de principios similares.
- Plan: `docs/plan-reconstruccion-v4.md`, Fase 3.
