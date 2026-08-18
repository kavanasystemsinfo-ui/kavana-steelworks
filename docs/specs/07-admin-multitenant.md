# Especificación del Dominio: ADMINISTRACIÓN MULTI-TENANT (spec 07)

Documento de contrato para portar la administración de empresa del legacy v2
(`/root/kavanasystems/backend/src/models/Tenant.js` + rutas admin/users/sequences)
a FastAPI + PostgreSQL con TDD, **con mejoras de escalabilidad y organización
sobre el monolito original**.

Regla de oro: el v2 guarda TODA la configuración de la empresa en un solo
documento JSON embebido. En el portado se normaliza lo que es entidad
consultable (puestos, roles, secuencias) y se mantiene JSONB solo para lo que
es configuración pura (tema, finanzas). El objetivo: multi-tenant real donde
cada empresa configura su sistema, con datos relacionales limpios.

---

## 1. Fuente legacy

| Archivo | Rol |
|---|---|
| `backend/src/models/Tenant.js` | Modelo monolito de la empresa (slug, auth, roles, sequences, workstations, theme, finances, plan) |
| `backend/src/routes/admin.js` | GET /tenant/:slug, PUT /tenant/config |
| `backend/src/routes/users.js` | CRUD de usuarios del tenant (roles, employeeNumber, defaultWorkstation) |
| `backend/src/routes/sequences.js` | GET /next/:type, POST /consume/:type, PUT /config |
| `backend/src/models/Sequence.js` | Contador por tenant+tipo+prefix con índice único |
| `backend/src/controllers/UserController.js` | Alta/edición de usuarios con roles |

---

## 2. Entidades del portado

### 2.1 Tenant (ampliado)

El modelo `tenants` actual solo tiene `name` e `is_active`. Se amplía:

| Campo | Tipo | Default | Notas |
|---|---|---|---|
| `slug` | str unique | — | Identificador de la empresa en URL (p.ej. `demo`) |
| `status` | enum | `active` | `active` \| `suspended` \| `trial` |
| `auth.login_method` | enum | `username_password` | `username_password` \| `employee_id` |
| `auth.require_line_number` | bool | `true` | Pide número de línea al operario |
| `theme.colors.primary` | str | `#007bff` | Color principal |
| `theme.branding.company_name` | str | `Demo Aceros` | Nombre mostrado |
| `theme.branding.logo_url` | str | `''` | Logo opcional |
| `finances.overhead_hourly_cost` | numeric | `0` | Coste global de mano de obra/h |
| `finances.operator_categories` | jsonb | 4 categorías del v2 | Peón Especialista 15, Oficial 3ª 18, Oficial 2ª 21, Oficial 1ª 25 |

Decisiones:
- `scheduledExport` (Data Vault) **NO se porta en esta fase**: depende de un
  cron de exportación y no aporta a la demo de planta. Queda documentado como
  pendiente (YAGNI por ahora, el v2 ya lo demuestra).
- `theme` y `finances` van como **JSONB** en `tenants` (config pura, sin
  consultas relacionales).
- El `plan` ya existe en `tenant_features` (ADR-003): se integra, no se duplica.

### 2.2 Roles configurables (tabla nueva `tenant_roles`)

El v2 embebe `roles: [{id, name, permissions}]` en el tenant. Se normaliza:

```
tenant_roles
- id uuid PK
- tenant_id FK tenants
- role_key str        # 'operator' | 'supervisor' | 'materials' | 'admin' | 'custom'
- name str            # etiqueta visible
- permissions jsonb   # lista de permisos granulares
- is_system bool      # true si es rol del sistema (no se puede borrar)
- UNIQUE(tenant_id, role_key)
```

Permisos granulares (catálogo v1):
`stock.scan`, `stock.link`, `stock.finish`, `stock.receive`, `stock.list`,
`production.record`, `quality.check`, `quality.read`, `incidencia.create`,
`incidencia.manage`, `oee.read`, `trace.read`, `orders.read`,
`admin.users`, `admin.tenant`, `admin.sequences`, `admin.workstations`,
`admin.roles`.

El rol `admin` del sistema tiene todos los permisos. Los demás se definen por
defecto con la matriz de la Fase 6 y el admin puede editarlos.

### 2.3 Secuencias automáticas (tabla nueva `sequences`)

Portado del modelo Sequence.js del v2:

```
sequences
- id uuid PK
- tenant_id FK tenants
- sequence_type str  # 'order' | 'lot'
- prefix str         # 'OP-{MM}{YY}-' o resuelto 'OP-0326'
- padding int        # 3
- next_number int    # contador
- UNIQUE(tenant_id, sequence_type, prefix)
```

Config por tenant (`tenant.sequences.order.prefix/padding`): se guarda en la
tabla `tenant_settings` (JSONB) o como columnas; el contador vivo es la tabla
`sequences` con `SELECT ... FOR UPDATE` (mejora sobre MongoDB, que no garantiza
atomicidad de incremento).

Servicio `next_sequence(db, tenant_id, type)`:
1. Resuelve el prefix con la fecha actual (`{MM}{YY}` → mes/año).
2. `SELECT ... FOR UPDATE` del contador con ese prefix; si no existe, crea con
   `next_number = 1` y persiste el prefix.
3. Devuelve el número formateado con padding y lo incrementa.

### 2.4 Puestos de trabajo (tabla nueva `workstations`)

**Mejora de organización principal**: hoy `workstation_id` es un string suelto
en `order_lines` y `quality_records`. El v2 embebe puestos en JSON con grupos.
Se normaliza:

```
workstations
- id uuid PK
- tenant_id FK tenants
- group_id FK workstation_groups nullable
- code str            # 'LINEA-1' (sustituye al string suelto)
- name str
- color str
- hourly_cost numeric
- registration_method enum  # 'timer' | 'quantity' | 'manual'
- maintenance_interval_hours int (0 = deshabilitado)
- maintenance_pre_warning_hours int
- last_maintenance_reset timestamptz nullable
- accumulated_hours numeric
- is_active bool
- UNIQUE(tenant_id, code)

workstation_groups
- id uuid PK
- tenant_id FK tenants
- name str
- color str
- UNIQUE(tenant_id, name)
```

Regla de compatibilidad: `order_lines.workstation_id` (string) se mantiene como
está durante la fase; el admin crea puestos con `code` y el resto del sistema
sigue usando el string. Un ADR posterior puede migrar las FKs si Jorge lo pide.

### 2.5 Usuarios (ampliar `users`)

El modelo User ya tiene tenant_id, email, name, password_hash, role, is_active.
Se añade (portado de UserController.js):

| Campo | Tipo | Notas |
|---|---|---|
| `employee_number` | str nullable | Nº de empleado (login method employee_id) |
| `default_workstation_code` | str nullable | Puesto por defecto |

`role` sigue siendo el rol simple del sistema (operator/supervisor/materials/
admin); los permisos granulares se resuelven por `tenant_roles` y el rol admin
hereda todo.

---

## 3. Endpoints (todos protegidos: solo rol admin del tenant)

Prefijo `/api/v1/admin`:

| Método | Ruta | Acción | Permiso |
|---|---|---|---|
| GET | `/tenant` | Config de la propia empresa | admin.tenant |
| PUT | `/tenant` | Actualizar name, slug, status, auth, theme, finances | admin.tenant |
| GET | `/users` | Listar usuarios del tenant | admin.users |
| POST | `/users` | Crear usuario (email, password, role, employee_number) | admin.users |
| PATCH | `/users/{id}` | Editar (role, is_active, employee_number, password) | admin.users |
| DELETE | `/users/{id}` | Desactivar usuario (soft) | admin.users |
| GET | `/sequences` | Config de secuencias (prefix/padding por tipo) | admin.sequences |
| PUT | `/sequences` | Actualizar prefix/padding | admin.sequences |
| GET | `/sequences/next/{type}` | Siguiente número (sin consumir) | admin.sequences |
| GET | `/workstations` | Listar puestos y grupos | admin.workstations |
| POST | `/workstations` | Crear puesto | admin.workstations |
| PATCH | `/workstations/{id}` | Editar puesto | admin.workstations |
| DELETE | `/workstations/{id}` | Desactivar puesto | admin.workstations |
| GET | `/roles` | Listar roles con permisos | admin.roles |
| PUT | `/roles/{role_key}` | Editar permisos de un rol custom | admin.roles |

Siempre con `tenant_id` del token (nunca del path): cada admin gestiona SOLO su
empresa. No existe superadmin cross-tenant en esta fase.

---

## 4. Reglas de negocio

1. **Un admin solo ve su tenant**: todas las queries filtran por
   `current_user.tenant_id`.
2. **El slug es único global** (identifica la empresa en URL/demo).
3. **No se puede borrar** un usuario: se desactiva (`is_active=False`).
4. **Los roles del sistema** (`operator`, `supervisor`, `materials`, `admin`)
   no se pueden borrar ni cambiar de role_key; solo editar permisos de los
   custom.
5. **Secuencias atómicas**: `next_sequence` usa `SELECT FOR UPDATE` (mejora
   sobre MongoDB; dos peticiones concurrentes nunca reciben el mismo número).
6. **Los puestos se desactivan, no se borran** (historia de órdenes intacta).
7. El `default_workstation_code` de un usuario debe existir en su tenant.

---

## 5. Verificación

- Tests TDD por entidad (roles, sequences con concurrencia simulada,
  workstations, users admin, tenant config).
- E2E contra PostgreSQL real: alta de tenant → admin crea usuario, puesto,
  cambia secuencias → login del nuevo usuario → `next_sequence` devuelve el
  número esperado.
- El seed demo crea los puestos LINEA-1..3 y un admin@demo.local con todos los
  permisos (compatibilidad con la Fase 6).
