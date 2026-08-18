# ADR-015: Administración multi-tenant — normalización sobre el monolito del v2

Estado: Aceptado
Fecha: 2026-08-16
Autor: Jorge Adán (KAVANA Systems) + Hermes (ejecución)

## Contexto

El legacy v2 guarda TODA la configuración de la empresa en un único documento
MongoDB (`Tenant.js`): auth, roles con permisos, secuencias, puestos de
trabajo (standalone + grupos), tema, finanzas y plan. Jorge quiere portar esa
capacidad a Steelworks ("cada tenant configura su propia empresa"), pero el
monolito tiene problemas conocidos:

- Los puestos viven como arrays anidados en JSON; `order_lines` y
  `quality_records` referencian puestos por un string suelto, sin integridad.
- Los roles con permisos están embebidos; no hay forma de consultar "qué
  puede hacer este rol" sin cargar todo el tenant.
- Las secuencias dependen de un documento con `$inc` de MongoDB, que no
  garantiza atomicidad real bajo concurrencia (dos requests pueden leer el
  mismo número).
- Cualquier cambio de config reescribe el documento entero (carreras de
  escritura).

## Opciones consideradas

### A. Portar el monolito tal cual (JSONB gigante en `tenants`)

- **Pros**: rápido, fiel al v2, cero migraciones complejas.
- **Contras**: replica los problemas de concurrencia y consulta; los puestos
  siguen sin integridad referencial; el "mejoro la arquitectura" que busca el
  portfolio no ocurre.

### B. Normalizar entidades consultables + JSONB solo para config pura (elegida)

- Tablas nuevas: `tenant_roles`, `sequences`, `workstations`,
  `workstation_groups`.
- `tenants` se amplía con columnas escalares (slug, status) y dos JSONB
  (`theme`, `finances`) que son configuración pura sin consulta relacional.
- `tenant_features` (ADR-003) ya cubre el plan: se integra, no se duplica.
- `users` gana `employee_number` y `default_workstation_code`.

**Pros**:
- Integridad real: puesto referenciado = fila existente en su tenant.
- Secuencias atómicas con `SELECT FOR UPDATE` (concurrencia segura).
- Permisos consultables y editables por rol sin cargar todo el tenant.
- Multi-tenant demostrable: cada admin gestiona solo su empresa, tenant del
  JWT, nunca del path.
- Historia limpia para el portfolio: "porté el monolito y lo normalicé".

**Contras**: más trabajo; migración Alembic nueva; hay que mantener
compatibilidad con el `workstation_id` string actual (los puestos nuevos usan
`code` y el resto del sistema sigue igual esta fase).

### C. No portar y dejarlo documentado

- **Contras**: Jorge pidió explícitamente el nivel 3.

## Decisión

Opción B. Se normaliza lo que es entidad consultable (roles, secuencias,
puestos) y se mantiene JSONB solo para configuración pura (theme, finanzas).
`tenant_features` (ADR-003) sigue siendo la fuente del plan. El seed demo crea
puestos LINEA-1..3 y admin@demo.local con todos los permisos, manteniendo la
compatibilidad con la Fase 6.

## Consecuencias

- **Positivas**: multi-tenant real configurable; concurrencia segura en
  secuencias; integridad de puestos; admin panel completo; decisión de
  arquitectura demostrable en el portfolio.
- **Negativas**: fase de trabajo grande (spec 07 completa: backend + frontend);
  los `workstation_id` strings históricos conviven con los `code` nuevos hasta
  una migración futura (ADR aparte si Jorge la pide).
- **Pendiente documentado (YAGNI)**: `scheduledExport`/Data Vault del v2
  (depende de cron de exportación; no aporta a la demo de planta).

## Referencias

- Legacy: `/root/kavanasystems/backend/src/models/Tenant.js`,
  `backend/src/routes/admin.js`, `routes/users.js`, `routes/sequences.js`,
  `models/Sequence.js`
- Spec: `docs/specs/07-admin-multitenant.md`
- Previo: ADR-003 (feature flags por plan), Fase 6 (login y roles)
