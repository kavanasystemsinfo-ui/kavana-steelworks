# 05. Otros Servicios

Dominio: servicios de soporte del MES: mantenimiento preventivo por horas de uso, alertas de stock bajo con impacto financiero, alertas de parada prolongada, secuencias/contadores atómicos, auditoría en 4 capas y el modelo de sesión (JWT 8 h = un turno, con invalidación server-side).

## 1. Fuente legacy

| Archivo | Rol |
|---|---|
| `/root/kavanasystems/backend/src/services/MaintenanceService.js` | Horas de uso por puesto, alertas de mantenimiento preventivo, reset de contador |
| `/root/kavanasystems/backend/src/services/StockAlertService.js` | Alertas de stock bajo mínimo con severidad e impacto financiero |
| `/root/kavanasystems/backend/src/services/AutomatonService.js` | Autómata de suelo de fábrica: chequeo de stock y de paradas prolongadas (> 30 min) |
| `/root/kavanasystems/backend/src/services/SequenceService.js` | Generador atómico de códigos secuenciales (Auto-Number) |
| `/root/kavanasystems/backend/src/models/Sequence.js` | Modelo del contador atómico por tenant + tipo + prefijo |
| `/root/kavanasystems/backend/src/services/AuditLoggerService.js` | Auto-auditoría en 4 capas (Winston, snapshots, Telegram, reportes de turno) |
| `/root/kavanasystems/backend/src/services/AuthService.js` | Login (JWT 8 h), turno de operario, logout con revocación |
| `/root/kavanasystems/backend/src/models/RevokedToken.js` | Lista negra de tokens con TTL |
| `/root/kavanasystems/backend/src/middlewares/authMiddleware.js` | Verificación de token y de revocación en cada request |
| `/root/kavanasystems/backend/src/models/Material.js` | Material con `stock.current`, `stock.minimum`, `costPerUnit`, `unit`, `isActive` |
| `/root/kavanasystems/backend/src/models/ProductionLog.js` | Fuente de eventos para horas de uso y detección de paradas |
| `/root/kavanasystems/backend/src/models/UserShift.js` (referenciado) | Turno activo del operario (sesión de 8 h) |
| `/root/kavanasystems/frontend/src/utils/tokenUtils.js` | Almacenamiento del token en `sessionStorage` (frontend) |

## 2. Entidades y relaciones

### 2.1 Puestos de trabajo con configuración de mantenimiento (dentro del Tenant)

Los puestos viven en `tenant.workstations` como `standalone[]` o `groups[].workstations[]`. Campos de mantenimiento por puesto:

- `maintenanceIntervalHours` (Number): horas de uso que disparan la alerta. **0 = mantenimiento deshabilitado**.
- `maintenancePreWarningHours` (Number): umbral de preaviso; si no se define, default `intervalHours * 0.8` (80 %).
- `lastMaintenanceReset` (Date): momento del último reset; default `new Date(0)` si nunca se reseteó.
- `accumulatedHours` (Number): campo legacy que `resetMaintenanceCounter` pone a 0 (el cálculo real usa los logs, no este campo).

### 2.2 Material (stock y coste)

- `stock.current` (Number, default 0), `stock.minimum` (Number, default 0).
- `costPerUnit` (Number, default 0): coste unitario en EUR, usado para el impacto financiero.
- `unit` (enum `kg`, `uds`, `m`, `litros`; default `kg`).
- `isActive` (Boolean, default true): solo los materiales activos generan alertas.
- UNIQUE `(tenantId, code)`.

### 2.3 Sequence (contador atómico)

- `tenantId` (-> Tenant), `sequenceType` (enum `order` | `lot`), `prefix` (String, ej: 'OP-0326' o 'LT-210326'), `currentValue` (Number, default 0).
- **Índice único** `(tenantId, sequenceType, prefix)`: un solo contador por tenant + tipo + periodo.
- El `prefix` incorpora la fecha, lo que reinicia los contadores por periodo (mes para órdenes, día para lotes).

### 2.4 RevokedToken (lista negra de sesiones)

- `token` (String, requerido, **unique**), `expiresAt` (Date, requerido).
- **TTL index** `{ expiresAt: 1 }, { expireAfterSeconds: 0 }`: MongoDB borra el documento automáticamente al expirar. La BD se mantiene limpia de tokens revocados caducados.

### 2.5 UserShift (turno de operario, usado por AuthService)

- `tenantId`, `operatorId` (-> User), `loginTime`, `logoutTime`, `status` ('active' | 'completed'), `totalHours`, `ordersHandled[]`, `globalEfficiency`, `metadata`.
- Un operario tiene **un solo turno activo** (`findOne({ tenantId, operatorId, status: 'active' })`).

### 2.6 Alertas (efímeras)

Las alertas de stock y downtime son **eventos en tiempo real** (Socket.IO, evento `kavana_auto_alert`) con campos `type`, `title`, `message`, `severity`, `timestamp` y datos específicos. No se persisten en el legacy; el cache anti-spam de downtime es en memoria (se pierde al reiniciar).

### 2.7 Relaciones

- `Sequence.tenantId -> Tenant`; contador por `(tenant, sequenceType, prefix)`.
- `Material.tenantId -> Tenant`; alerta derivada de `stock.current <= stock.minimum`.
- `RevokedToken` es independiente (no tiene tenant: el token completo es la clave).
- `UserShift.operatorId -> User`, `UserShift.tenantId -> Tenant`.
- MaintenanceService cruza `ProductionLog.orderId -> Order.lines[]` para atribuir logs al puesto correcto (ver 3.1).

## 3. Operaciones clave

### 3.1 Mantenimiento preventivo (MaintenanceService)

#### `calculateWorkstationHours(tenantId, workstationId)`

- **Comportamiento**:
  1. Carga el Tenant; si no existe -> `Error('Tenant no encontrado')`. Busca el puesto en standalone y grupos; si no -> `Error('Puesto no encontrado')`.
  2. Lee `intervalHours = maintenanceIntervalHours || 0`, `preWarningHours = maintenancePreWarningHours || intervalHours * 0.8`, `lastReset = lastMaintenanceReset || new Date(0)`.
  3. **Si `intervalHours === 0`**: devuelve `{ totalHours: 0, alertActive: false, intervalHours: 0, lastReset: null, disabled: true }` (mantenimiento deshabilitado, sin cálculo).
  4. Agrega los `ProductionLog` del tenant con `action IN ('start','finish','pause','resume','stopped')` y `timestamp >= lastReset`. Une con `orders` y desempaqueta `order.lines`; **empareja** `log.lineId` (a string) con `order.lines._id` (a string) Y `order.lines.workstationId === workstationId`. Así solo cuentan los logs de ese puesto concreto.
  5. **Emparejamiento de pares**: recorre los logs ordenados por timestamp; `start`/`resume` fija `pendingStart`; `finish`/`pause`/`stopped` con `pendingStart` activo suma `(end - start)` en minutos (solo si `duration > 0`) y limpia `pendingStart`.
  6. **Sesión abierta al final**: si queda `pendingStart`, suma `now - pendingStart` en minutos SOLO si `0 < duration < 720` (límite de 12 h para evitar errores por sesiones olvidadas).
  7. `totalHours = round(totalMinutes / 60, 1 decimal)`.
  8. `alertActive = totalHours >= intervalHours`; `warningActive = !alertActive && preWarningHours > 0 && totalHours >= preWarningHours`; `percentUsed = round(totalHours / intervalHours * 100)`.
  9. Devuelve `{ totalHours, alertActive, warningActive, intervalHours, preWarningHours, lastReset, percentUsed }`.
- **Invariantes**: el cálculo es idempotente y determinista (misma data -> mismo resultado). El puesto deshabilitado nunca genera alerta. Un arranque sin cierre cuenta como uso solo hasta 12 h.

#### `resetMaintenanceCounter(tenantId, workstationId, technicianId, notes = '')`

- **Comportamiento**: busca el puesto en standalone y grupos; al encontrarlo fija `lastMaintenanceReset = new Date()` y `accumulatedHours = 0`; guarda el tenant. Si no existe -> `Error('Puesto no encontrado')`. Devuelve `{ success: true, message: 'Contador reseteado correctamente', resetAt: new Date() }`.
- **Invariantes**: el reset solo toca la config del puesto; los logs históricos NO se borran (el cálculo futuro simplemente arranca desde `lastReset`). `technicianId` y `notes` se aceptan pero **no se persisten** (TODO: crear `MaintenanceLog` de auditoría).

#### `getAlertsForTenant(tenantId)`

- **Comportamiento**: recopila todos los puestos (standalone con `groupName: null` y grupos con `groupName: g.name`). Para cada puesto con `maintenanceIntervalHours > 0` calcula horas y, si `alertActive`, añade `{ workstationId, workstationName, groupName, totalHours, intervalHours, percentUsed, lastReset }`. Los errores por puesto se loguean y se saltan (un puesto roto no tumba el listado).
- **Invariantes**: solo devuelve puestos en alerta ACTIVA; los que están en preaviso no salen aquí (sí en el estado general).

#### `getAllWorkstationsStatus(tenantId)`

- **Comportamiento**: como el anterior pero devuelve TODOS los puestos con su estado: `status: 'alert'` (alerta activa), `'warning'` (preaviso), `'ok'` (resto con mantenimiento habilitado) o `'disabled'` (`maintenanceIntervalHours === 0`, con `disabled: true`). Incluye `...stats` completos (totalHours, percentUsed, etc.).

### 3.2 Alertas de stock bajo (StockAlertService + AutomatonService)

#### `getMaterialAlerts(tenantId)`

- **Comportamiento**: busca `Material.find({ tenantId, isActive: true, $expr: { $lte: ['$stock.current', '$stock.minimum'] } })` (comparación de campos DENTRO del mismo documento; una query simple de campo contra valor no sirve). Selecciona `code name stock costPerUnit unit`.
- **Derivación por material**: `current = stock.current`; `minimum = stock.minimum`; `deficit = minimum - current`; `severity`:
  - `current === 0` -> `'critical'`;
  - `current < minimum * 0.5` -> `'high'`;
  - resto -> `'warning'`.
- `unit = material.unit || 'uds'`.
- **Impacto financiero**: `costImpact = deficit * (costPerUnit || 0)` (EUR estimados para reponer hasta el mínimo).
- Devuelve `[{ materialId, code, name, currentStock, minStock, deficit, unit, severity, costImpact }]`. Los errores se relanzan (el autómata los captura).
- **Invariantes**: solo materiales activos; severidad estrictamente por las reglas de arriba; `costImpact` es 0 si no hay coste definido.

#### `checkTenantStock(tenantId)` (autómata)

- **Comportamiento**: obtiene las alertas; si no hay, retorna. Por cada alerta emite por Socket.IO `kavana_auto_alert` con `type: 'stock_deficit'`, título `⚠️ STOCK MÍNIMO SOBREPASADO: <code>`, mensaje con `currentStock`, `minStock` y `deficit` formateados a 1 decimal, `severity`, `materialId`, `costImpact` y `timestamp`. Además loguea la sugerencia de reposición autónoma (auto-requisition): pedir `deficit` unidades con impacto `costImpact` EUR.
- **Invariantes**: es monitorización en segundo plano; cualquier error se captura y loguea sin romper el loop.

### 3.3 Alertas de parada prolongada (AutomatonService.checkTenantDowntime)

- **Comportamiento**:
  1. Busca órdenes `status: 'in_progress'` del tenant. Si no hay, retorna.
  2. Por cada línea con `line.status === 'stopped'`, busca el último `ProductionLog` de `(tenantId, orderId, lineId)`.
  3. Si el último log es `action === 'pause'`, calcula `minutesStopped = (now - pauseTime) / 60000`.
  4. **Umbral: `minutesStopped >= 30`** -> emite `kavana_auto_alert` con `type: 'downtime_stoppage'`, título `🚨 PARADA DE MÁQUINA PROLONGADA: <workstationName>`, mensaje con `orderNumber`, `minutesStopped` (0 decimales) y `latestLog.metadata?.reason || 'No especificado'`, `severity: 'high'`, `orderId`, `lineId`, `minutesStopped` (redondeado), `timestamp`.
  5. **Anti-spam**: cache estática en memoria `alertedStoppages` con key `orderId-lineId`; solo se re-alerta si han pasado `>= 15` minutos desde la última alerta de esa línea.
- **Invariantes**: solo aplica a líneas `stopped` cuyo último evento sea `pause`. El umbral es 30 min y la re-alerta 15 min. La cache es **volátil** (se pierde al reiniciar el proceso, causando re-alertas tras un reinicio).

#### `init()` / `runAutopilotCheck()`

- Heartbeat: primer chequeo a los 5 s de arrancar y luego cada 1 minuto (en producción puede ser 5 min). Itera los tenants activos y ejecuta `checkTenantStock` + `checkTenantDowntime` por tenant. Errores del loop global capturados.

### 3.4 Secuencias y contadores atómicos (SequenceService)

#### `getNextNumber(tenantId, type)` -> `'<prefix><counter>'`

- **Comportamiento**:
  1. `_getConfig(tenantId, type)`: lee `tenant.sequences`; defaults: orden -> `'OP-{MM}{YY}-'` con padding 3; lote -> `'LT-{DD}{MM}{YY}-'` con padding 3. Tipo desconocido -> `Error('Tipo de secuencia desconocido: <type>')`.
  2. `_parsePrefix(format, now)`: sustituye `{DD}` (día 2 dígitos), `{MM}` (mes 2 dígitos), `{YY}` (año 2 dígitos), `{YYYY}` (año 4 dígitos). Con `format` null/undefined/'' devuelve `''` (sin prefijo).
  3. **Incremento atómico**: `Sequence.findOneAndUpdate({ tenantId, sequenceType: type, prefix }, { $inc: { currentValue: 1 } }, { new: true, upsert: true, setDefaultsOnInsert: true })`. El upsert crea el contador si el prefijo (periodo) no existe; el `$inc` es atómico (sin carreras entre peticiones concurrentes).
  4. `counter = padding > 0 ? String(currentValue).padStart(padding, '0') : String(currentValue)`.
  5. Devuelve `prefix + counter`, ej: `OP-0826-001`, `LT-140826-001`.
- **Invariantes**: cada llamada consume exactamente 1 del contador y devuelve un valor único para (tenant, type, prefix). El índice único `(tenantId, sequenceType, prefix)` garantiza un solo contador por periodo. `padding` 0 = sin relleno.

#### `previewNextNumber(tenantId, type)`

- **Comportamiento**: como `getNextNumber` pero con `findOne` (sin incremento): `nextValue = (seq?.currentValue || 0) + 1`. Devuelve el mismo formato sin consumir.
- **Invariantes**: es solo informativo; dos previews seguidos devuelven el mismo valor, y el siguiente `getNextNumber` devolverá ese valor.

### 3.5 Auditoría en 4 capas (AuditLoggerService)

Diseñado para funcionar **sin depender de red ni de BD externa** (solo sistema de archivos + opcional Telegram). Directorios bajo `backend/logs/`: `logs/`, `logs/snapshots/`, `logs/reports/`.

- **`init(telegramToken, telegramChatId)`**: configura Telegram (opcional) y marca `initialized`. Loguea `AUDIT_LOGGER` con `telegramEnabled` y `logDir`.
- **CAPA A: logging estructurado (Winston)**: nivel por `AUDIT_LOG_LEVEL` (default `info`), formato JSON con timestamp `YYYY-MM-DD HH:mm:ss.SSS`, `defaultMeta: { service: 'kavana-mes' }`. Transportes:
  - `kavana-error.log` (solo level `error`, rotación 5 MB x 5 archivos).
  - `kavana-combined.log` (5 MB x 3 archivos).
  - Consola con color y formato `timestamp [level] [module|GENERAL] message`.
  - Métodos con firma `(module, message, meta = {})`:
    - `info`: cambios de estado ordinarios (inicio de turno, cambio de orden, operario logueado).
    - `warn`: demoras inusuales, microparadas sospechosas, ediciones con progreso activo.
    - `error`: fallos de persistencia, errores de cálculo, excepciones controladas.
    - `critical`: desconfiguración del OEE, discrepancias en mermas, fallos de conexión DB. Además de loguear con prefijo `[CRITICAL]`, dispara CAPA B y CAPA C.
- **CAPA B: snapshots JSON**: `_captureSnapshot(module, message, meta)` escribe en `logs/snapshots/snapshot_<module>_<timestamp-ISO-sin-:-.>.json` un objeto con `timestamp`, `module`, `message`, `meta` y `system: { nodeVersion, platform, memoryUsage, uptime, pid }` (fotografía del estado en el momento del error). Fallos al guardar se loguean como error, no rompen nada.
- **CAPA C: alertas Telegram no bloqueantes**: `_sendTelegramAlert(message)` usa `fetch` con `AbortSignal.timeout(3000)` (3 s máximo). Solo si hay config; respuesta no-OK -> `warn`; excepción (red caída, timeout) -> `warn` y se continúa. **Nunca bloquea el flujo de planta**. Formato Markdown, prefijo `🚨 *CRÍTICO KAVANA* [<module>]`.
- **CAPA D: reporte post-turno**: `consolidateShiftReport(tenantId, workstationId, operatorId)` genera `{ reportId: 'shift_<epoch>', tenantId, workstationId, operatorId, generatedAt, snapshots: _getTodaySnapshots(), criticalAlerts: _getTodayCriticalAlerts(), summary: { totalSnapshots, totalCriticals, hasAnomalies } }` y lo escribe en `logs/reports/shift_report_<workstationId>_<operatorId>_<epoch>.json`. `_getTodaySnapshots` lee los `.json` de hoy del directorio de snapshots (los corruptos entran como `{ filename, parseError: true }`). `_getTodayCriticalAlerts` devuelve `[]` (TODO V2: parsear `kavana-error.log`).
- **Invariantes**: ninguna capa puede lanzar excepciones al llamador (todo capturado). El sistema funciona offline.

### 3.6 Modelo de sesión y auth (AuthService + authMiddleware)

#### `login(username, password, tenantSlug)`

- **Comportamiento**:
  1. `Tenant.findOne({ slug: tenantSlug })`; si no -> `Error('Empresa no válida')`.
  2. `User.findOne({ username: username.toUpperCase(), tenantId })` con `select('+password')` (el password está oculto por defecto). Si no existe o `!isActive` -> `Error('Usuario no encontrado o inactivo')`.
  3. `bcrypt.compare(password, user.password)`; si no coincide -> `Error('Credenciales incorrectas')`.
  4. **Módulo de Turno Global (V2.4.5)**: si `user.roles` incluye `'operator'`:
     - Busca `UserShift.findOne({ tenantId, operatorId, status: 'active' })`.
     - **Turno stale**: si existe y `(now - loginTime) > 14 h`, lo auto-cierra: `logoutTime = loginTime + 8 h`; recupera los `ProductionLog` de ese operario en la ventana `[loginTime, loginTime + 8 h]` con `action IN ('produce','finish','close_shift')`; `ordersHandled = orderIds únicos`; `globalEfficiency = promedio de metadata.efficiency` (0 si no hay); `totalHours = totalTimeSpentHours` si `0 < x <= 14`, si `> 14` -> 8.0, si 0 -> 8.0; `status = 'completed'`; `metadata.notes += ' [Auto-cerrado por inactividad > 14h]'`. Luego crea un turno nuevo activo.
     - **Sin turno activo**: crea `UserShift({ tenantId, operatorId, loginTime: now, status: 'active' })`.
     - Devuelve `activeShiftId`.
  5. **JWT**: `jwt.sign({ id: user._id, tenantId, roles: user.roles, slug: tenant.slug }, process.env.JWT_SECRET, { expiresIn: '8h' })`. El TTL de 8 h corresponde a **un turno**.
  6. Devuelve `{ token, user: { id, tenantId, username, firstName, roles, tenantName, tenantSlug, defaultWorkstation, activeShiftId } }`.
- **Invariantes**: el username se normaliza a MAYÚSCULAS en el login (y así se guarda). El token lleva `id`, `tenantId`, `roles` y `slug`; el frontend deriva permisos de `roles` y multi-tenant de `tenantId`. TTL = 8 h exactas.

#### `logout(token)`

- **Comportamiento**: si no hay token, retorna. Decodifica con `jwt.decode` (sin verificar firma); si no hay `exp`, retorna. `expiresAt = new Date(decoded.exp * 1000)`. `RevokedToken.updateOne({ token }, { $set: { expiresAt } }, { upsert: true })`. Errores se capturan e ignoran (token ya expirado, doble clic, etc.).
- **Invariantes**: el logout es idempotente (upsert). La revocación dura hasta la expiración natural del token (el TTL de Mongo limpia el documento).

#### `authMiddleware` (por request)

- Extrae `Authorization: Bearer <token>`; verifica firma con `JWT_SECRET`; **comprueba `RevokedToken.exists({ token })`**; si está revocado -> 401 `'Token revocado o sesión expirada.'`. Adjunta `req.user` (con `tenantId`, `id`, `roles`, `slug`).
- **Modelo de sesión completo**: token en `sessionStorage` del navegador (frontend, `tokenUtils.js`), TTL 8 h = un turno, e invalidación server-side por lista negra (RevokedToken) al hacer logout. El token revocado deja de valer inmediatamente, sin esperar a la expiración.

## 4. Reglas de negocio críticas

1. **Mantenimiento deshabilitado por defecto de facto**: `maintenanceIntervalHours === 0` significa sin alertas ni cálculo (`disabled: true`). El preaviso default es el 80 % del intervalo.
2. **Horas de uso por emparejamiento de pares**: solo cuentan pares `start/resume` -> `finish/pause/stopped` del mismo puesto (validado cruzando `order.lines`). Un `start` sin cierre suma hasta 12 h máximo (sesión olvidada no debe inflar el contador).
3. **Alerta de stock**: `stock.current <= stock.minimum` con material activo. Severidad: `critical` si `current === 0`, `high` si `current < minimum * 0.5`, `warning` en el resto. `costImpact = deficit * costPerUnit` (reposición al mínimo en EUR).
4. **Parada prolongada**: línea `stopped` con último log `pause` y `minutesStopped >= 30` -> alerta `downtime_stoppage` severidad `high`. Re-alerta como mínimo cada 15 min (anti-spam en memoria).
5. **Secuencias atómicas**: el incremento debe ser indivisible (legacy: `findOneAndUpdate` con `$inc` + upsert + índice único `(tenant, type, prefix)`). Un código generado no puede repetirse ni perderse por concurrencia. En PostgreSQL: `INSERT ... ON CONFLICT DO UPDATE` o `SELECT ... FOR UPDATE` dentro de transacción.
6. **Prefijos por periodo**: el prefijo con fecha (`OP-{MM}{YY}-` mensual, `LT-{DD}{MM}{YY}-` diario) reinicia los contadores por periodo automáticamente.
7. **Auditoría nunca bloquea**: las 4 capas (logs, snapshots, Telegram, reportes) son best-effort; fallos de red o de disco se loguean y no afectan al flujo de planta. Telegram con timeout de 3 s.
8. **Sesión = 8 h**: JWT `expiresIn: '8h'` (un turno). El cierre de sesión es server-side: token en RevokedToken y cada request verifica la lista negra. Logout idempotente.
9. **Un operario, un turno activo**: al hacer login de operario se garantiza exactamente un `UserShift` activo; los turnos stale (> 14 h) se auto-cierran con datos reconstruidos de los logs.
10. **Normalización de username**: login con `username.toUpperCase()`; el usuario inactivo no puede entrar aunque la contraseña sea correcta.

## 5. Casos límite conocidos

- **Puesto sin `lastMaintenanceReset`**: se usa `new Date(0)` (época) y el cálculo abarca todo el histórico de logs.
- **Sesión olvidada (start sin finish)**: suma hasta 12 h (720 min); si la sesión abierta supera 12 h, no suma nada (evita errores por turnos olvidados).
- **Logs sin orden o línea desaparecida**: el `$lookup`/unwind con `preserveNullAndEmptyArrays` tolera órdenes borradas; el emparejamiento por string de IDs falla silenciosamente (esos logs no cuentan).
- **Duración negativa**: `if (duration > 0)` filtra pares con timestamps invertidos.
- **Alerta de stock con `costPerUnit` 0**: `costImpact` = 0; la alerta se emite igualmente.
- **`minimum` 0**: un material con mínimo 0 y stock 0 cae en `current <= minimum` y en `current === 0` -> `critical`, aunque "nunca" debería faltar. Es un caso heredado.
- **Cache anti-spam volátil**: tras reiniciar el backend, `alertedStoppages` se vacía y una línea parada > 30 min vuelve a alertar de inmediato.
- **`unit` ausente en Material**: se usa `'uds'` en la alerta.
- **Preview de secuencia sin contador creado**: devuelve el valor 1 (o `padding`-rellenado) sin crear fila.
- **Padding 0**: el contador se devuelve sin relleno (`String(currentValue)`).
- **Logout doble clic / token expirado**: `logout` captura todo y no lanza; el upsert hace la revocación idempotente.
- **Turno stale con logs sin `efficiency`**: `globalEfficiency = 0`; `totalHours` cae a 8.0 si no hay `timeSpent` o si supera 14 h.
- **Telegram caído o lento**: alerta no enviada, solo `warn`; la capa crítica (snapshot) ya se escribió en disco.
- **Snapshot corrupto**: entra al reporte de turno como `{ filename, parseError: true }` y cuenta como anomalía.
- **Sin tenants activos / sin órdenes `in_progress`**: el autómata retorna sin hacer nada.

## 6. Requisitos para el modelo relacional (PostgreSQL)

### Tabla `workstations` (config de mantenimiento; si se normaliza fuera del tenant)

| Columna | Tipo | Constraints |
|---|---|---|
| `id` | TEXT | PK (el legacy usa strings como 'perfiladora-a') |
| `tenant_id` | BIGINT | NOT NULL, FK -> `tenants.id`, UNIQUE `(tenant_id, id)` |
| `name` | TEXT | NOT NULL |
| `group_name` | TEXT | NULL (si viene de un grupo) |
| `maintenance_interval_hours` | NUMERIC(10,2) | NOT NULL, default 0 (0 = deshabilitado), CHECK `>= 0` |
| `maintenance_pre_warning_hours` | NUMERIC(10,2) | NULL (default calculado: 80 % del intervalo) |
| `last_maintenance_reset_at` | TIMESTAMPTZ | NULL (default: época si nunca se reseteó) |

- Si se conserva JSONB de tenant (`workstations` como JSONB), el cálculo debe seguir leyendo de ahí; se recomienda normalizar para constraints y consultas.

### Tabla `sequences` (contadores atómicos)

| Columna | Tipo | Constraints |
|---|---|---|
| `id` | BIGSERIAL | PK |
| `tenant_id` | BIGINT | NOT NULL, FK -> `tenants.id` |
| `sequence_type` | TEXT | NOT NULL, CHECK `IN ('order','lot')` |
| `prefix` | TEXT | NOT NULL (ej: 'OP-0826') |
| `current_value` | BIGINT | NOT NULL, default 0, CHECK `>= 0` |
| `created_at`, `updated_at` | TIMESTAMPTZ | NOT NULL |

- **UNIQUE `(tenant_id, sequence_type, prefix)`**: garantiza un contador por periodo.
- **Atomicidad**: `getNextNumber` en PostgreSQL = `INSERT ... ON CONFLICT (tenant_id, sequence_type, prefix) DO UPDATE SET current_value = sequences.current_value + 1 RETURNING current_value` (o `SELECT ... FOR UPDATE` en transacción). Nunca leer-modificar-escribir sin bloqueo.

### Tabla `revoked_tokens` (lista negra de sesiones)

| Columna | Tipo | Constraints |
|---|---|---|
| `token` | TEXT | PK (o UNIQUE) |
| `expires_at` | TIMESTAMPTZ | NOT NULL |

- **Limpieza**: el TTL de Mongo equivale a un job periódico (`DELETE FROM revoked_tokens WHERE expires_at < now()`) o una vista filtrada; el middleware solo consulta `WHERE token = $1`.

### Tabla `user_shifts` (sesión de turno; mínima para el modelo de sesión)

| Columna | Tipo | Constraints |
|---|---|---|
| `id` | BIGSERIAL | PK |
| `tenant_id` | BIGINT | NOT NULL, FK -> `tenants.id` |
| `operator_id` | BIGINT | NOT NULL, FK -> `users.id` |
| `login_time` | TIMESTAMPTZ | NOT NULL |
| `logout_time` | TIMESTAMPTZ | NULL |
| `status` | TEXT | NOT NULL, CHECK `IN ('active','completed')` |
| `total_hours` | NUMERIC(6,2) | NOT NULL, default 0 |
| `orders_handled` | JSONB | NOT NULL, default '[]' (array de orderIds) |
| `global_efficiency` | NUMERIC(6,4) | NOT NULL, default 0 |
| `metadata` | JSONB | NOT NULL, default '{}' |
| `created_at`, `updated_at` | TIMESTAMPTZ | NOT NULL |

- Índice UNIQUE parcial para "un turno activo por operario": `CREATE UNIQUE INDEX uq_user_shifts_active ON user_shifts(tenant_id, operator_id) WHERE status = 'active'`.
- **Auto-cierre de stale** (> 14 h): job programado o lógica en el login que reconstruya `total_hours`, `orders_handled` y `global_efficiency` desde `production_logs` de la ventana `[login_time, login_time + 8 h]` (acciones `produce`, `finish`, `close_shift`).

### Tabla `materials` (mínimo para alertas)

- Ya especificada en el dominio de inventario; requisitos extra para este spec: `stock_current` y `stock_minimum` NUMERIC NOT NULL CHECK `>= 0`, `cost_per_unit` NUMERIC(12,2) NOT NULL default 0, `unit` TEXT CHECK `IN ('kg','uds','m','litros')`, `is_active` BOOLEAN default true, UNIQUE `(tenant_id, code)`.
- Alerta = query derivada: `WHERE tenant_id = $1 AND is_active AND stock_current <= stock_minimum` (el legacy compara campos dentro del documento; en SQL es directo).

### Tabla `alerts` (recomendada; el legacy no persiste)

El legacy emite alertas solo por Socket.IO (efímeras) con cache en memoria. Para un portado robusto se recomienda persistir:

| Columna | Tipo | Constraints |
|---|---|---|
| `id` | BIGSERIAL | PK |
| `tenant_id` | BIGINT | NOT NULL, FK -> `tenants.id` |
| `type` | TEXT | NOT NULL, CHECK `IN ('stock_deficit','downtime_stoppage')` |
| `severity` | TEXT | NOT NULL, CHECK `IN ('critical','high','warning')` |
| `title` | TEXT | NOT NULL |
| `message` | TEXT | NOT NULL |
| `material_id` | BIGINT | NULL, FK -> `materials.id` (solo stock_deficit) |
| `order_id` | BIGINT | NULL, FK -> `orders.id` (solo downtime_stoppage) |
| `line_id` | BIGINT | NULL, FK -> `order_lines.id` (solo downtime_stoppage) |
| `minutes_stopped` | NUMERIC(10,2) | NULL (solo downtime_stoppage) |
| `cost_impact` | NUMERIC(12,2) | NULL (solo stock_deficit) |
| `payload` | JSONB | NOT NULL, default '{}' |
| `created_at` | TIMESTAMPTZ | NOT NULL |

- Índice `(tenant_id, created_at DESC)`. El anti-spam de downtime (re-alerta cada 15 min por `order_id + line_id`) puede implementarse con `MAX(created_at)` por par en el job.

### Tabla `audit_logs` (opcional; el legacy es file-based)

El legacy escribe archivos JSON (Winston) por diseño offline. Si el portado quiere auditoría consultable, se recomienda `audit_logs`:

| Columna | Tipo | Constraints |
|---|---|---|
| `id` | BIGSERIAL | PK |
| `level` | TEXT | NOT NULL, CHECK `IN ('info','warn','error','critical')` |
| `module` | TEXT | NOT NULL |
| `message` | TEXT | NOT NULL |
| `meta` | JSONB | NOT NULL, default '{}' |
| `created_at` | TIMESTAMPTZ | NOT NULL |

- Índice `(level, created_at DESC)`. La capa de snapshots (`snapshot_*.json` con info de sistema) y los reportes de turno pueden seguir siendo archivos o migrar a tablas `audit_snapshots` y `shift_reports`. La invariancia clave: escribir auditoría **nunca** debe lanzar excepciones al dominio.

### Notas de portado

- **Job del autómata**: en FastAPI, un worker periódico (cada 1 a 5 min) que ejecute: 1) alertas de stock, 2) paradas > 30 min con anti-spam de 15 min. El anti-spam debe ser durable (consulta a `alerts`), no en memoria.
- **Secuencias**: usar la misma estrategia de prefijos por periodo; el formato de fecha del prefijo debe ser configurable por tenant con los mismos defaults (`OP-{MM}{YY}-` padding 3, `LT-{DD}{MM}{YY}-` padding 3).
- **Sesión**: mantener TTL 8 h, `sessionStorage` en frontend, y validación de RevokedToken en cada request autenticado.
