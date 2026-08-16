# Política de seguridad — KAVANA Steelworks

## Reportar una vulnerabilidad

Si encuentras un problema de seguridad, por favor repórtalo de forma privada
a **kavanasystems.info@gmail.com**. No abras un issue público con detalles
explotables hasta que hayamos tenido la oportunidad de corregirlo.

Agradecemos incluir: descripción del problema, pasos para reproducirlo,
impacto potencial y (si es posible) una sugerencia de corrección.

## Alcance

Aplica al repositorio `kavana-steelworks` (backend FastAPI + frontend React)
y a los despliegues públicos de la demo.

## Estado de seguridad conocido

Este proyecto es un portfolio público. La demo desplegada funciona **sin
autenticación** a propósito: los endpoints de escritura (producción, stock,
incidencias, calidad) resuelven el tenant y el operario de la demo
internamente. Es una decisión de producto para que el reclutador pueda
probar el flujo completo sin credenciales.

Esto implica que, si se despliega con datos reales, la API queda abierta a
escritura por cualquiera con la URL. La habilitación de autenticación por
roles (operario vs supervisor) está prevista y no debe desplegarse en
producción con datos reales sin ella.

## Buenas prácticas aplicadas

- JWT HS256 con fail-fast: producción exige `STEELWORKS_JWT_SECRET` (>= 256 bits).
- Revocación de tokens server-side (lista negra), logout idempotente.
- Contraseñas con bcrypt (12 rondas), comparación timing-safe.
- Consultas SQL siempre parametrizadas (SQLAlchemy 2.0).
- Subida de fotos validada por magic bytes (lista blanca PNG/JPEG/WebP/GIF,
  sin SVG), tamaño máximo 10 MB con lectura streaming y sesión de un solo uso
  (UUIDv4, TTL 15 min).
- Rate limit de subidas por IP.
- Cabeceras de seguridad en todas las respuestas.
