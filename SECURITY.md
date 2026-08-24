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

## Estado de seguridad (actualizado 2026-08-24, Fases 6-7)

La demo desplegada **exige autenticación** desde la Fase 6. Todos los
endpoints requieren un Bearer JWT válido, excepto el login y la subida de
foto desde el móvil (que usa una sesión de un solo uso como credencial).
Los roles (operator / materials / supervisor / admin) se aplican por
endpoint con una matriz explícita; el frontend la refleja con guards de
ruta. Las cuentas demo (`operario@demo.local`, etc., password `kavana`)
están publicadas a propósito para que el reclutador pueda probar el flujo
completo.

El aislamiento entre tenants se aplica en cada endpoint: el tenant
autorizado sale del JWT, nunca de parámetros controlados por el cliente.
Esto incluye los eventos de planta (REST y WebSocket, endurecido en la
auditoría del 2026-08-24: ver ADR-014 y `tests/test_tenant_isolation.py`).

No debe desplegarse con datos reales sin revisar: es una demo de portfolio
con datos ficticios, no un sistema certificado.

## Buenas prácticas aplicadas

- JWT HS256 con fail-fast: producción exige `STEELWORKS_JWT_SECRET` (>= 256 bits).
- Revocación de tokens server-side (lista negra), logout idempotente.
- Contraseñas con bcrypt (12 rondas), comparación timing-safe.
- Autorización por rol y por tenant en cada endpoint (matriz probada en tests).
- Consultas SQL siempre parametrizadas (SQLAlchemy 2.0).
- Subida de fotos validada por magic bytes (lista blanca PNG/JPEG/WebP/GIF,
  sin SVG), tamaño máximo 10 MB con lectura streaming y sesión de un solo uso
  (UUIDv4, TTL 15 min).
- Rate limit de subidas por IP.
- Cabeceras de seguridad en todas las respuestas.
- Health checks separados: `/health/live` (proceso vivo) y `/health/ready`
  (verifica conectividad real con PostgreSQL).
