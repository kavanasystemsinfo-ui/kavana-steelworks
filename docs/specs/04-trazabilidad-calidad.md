# 04. Trazabilidad y Calidad

Dominio: trazabilidad ISO 9001 de producción (eventos inmutables), autocontroles de calidad del operario (no bloqueantes) y gestión de incidencias de planta con cierre financiero.

## 1. Fuente legacy

| Archivo | Rol |
|---|---|
| `/root/kavanasystems/backend/src/services/TraceabilityService.js` | Registro de eventos de producción inmutables y consulta de trazabilidad por orden |
| `/root/kavanasystems/backend/src/services/QualityService.js` | Evaluación de mediciones contra el plan de calidad (números y pasafalla) |
| `/root/kavanasystems/backend/src/models/QualityRecord.js` | Modelo del registro de inspección de calidad |
| `/root/kavanasystems/backend/src/models/ProductionLog.js` | Modelo del log inmutable de producción (base de la trazabilidad) |
| `/root/kavanasystems/backend/src/models/ManufacturingModel.js` | Plantilla de pieza que contiene el `qualityPlan` (plantilla de controles) |
| `/root/kavanasystems/backend/src/models/Incidencia.js` | Modelo de incidencia de planta |
| `/root/kavanasystems/backend/src/controllers/QualityController.js` | Orquestación del registro de autocontrol y consulta de registros |
| `/root/kavanasystems/backend/src/controllers/IncidenciaController.js` | Alta, foto móvil, consulta y cierre de incidencias |
| `/root/kavanasystems/backend/src/services/OEEService.js` | Consumo de `resolucion.tiempoParada` de incidencias como downtime (parcial) |
| `/root/kavanasystems/DECISIONES_ESTRATEGICAS.md` (decisión 2026-05-18) | Protocolo de recordatorios de calidad no bloqueantes (15 min y cada 2 h) |
| `/root/kavanasystems/frontend/src/pages/operator/OperatorDashboard.jsx` | Implementación del ciclo de recordatorios (toasts) y reseteo de temporizadores |

## 2. Entidades y relaciones

### 2.1 ProductionLog (evento de trazabilidad)

Registro de evento de producción **inmutable** (`immutable: true` en el esquema: no se puede modificar ni borrar un log; es la base de auditoría).

| Campo | Tipo | Notas |
|---|---|---|
| `tenantId` | ObjectId -> Tenant | requerido, indexado |
| `orderId` | ObjectId -> Order | requerido, indexado |
| `lineId` | ObjectId | ID de la línea **dentro de la orden** (`Order.lines[]`), requerido |
| `operatorId` | ObjectId -> User | quién lo hizo, requerido |
| `timestamp` | Date | default `Date.now`, indexado |
| `action` | enum | `start`, `pause`, `resume`, `finish`, `produce`, `scrap`, `setup_start`, `setup_finish`, `close_shift`. Nota: el código de trazas habla también de `stopped` y `quality_check` como acciones usadas en consultas y logs |
| `quantity` | Number | default 0; para `produce` o `scrap` |
| `metadata` | objeto flexible | `reason` (motivo de pausa), `materialBatch`, `notes`, `device` ('tablet', 'pc'), `totalRealized`, `consumedMaterial`, `consumedAmount`, `incrementalCost`, `incrementalMaterialCost`, `efficiency`, `observaciones`, `workstationName`, `manufacturingModel`, `activeCoilId` (-> StockItem), `activeCoilCode` (redundancia histórica, ej: '301173852') |
| `shift` | enum | `morning`, `afternoon`, `night` (calculado, futuro) |

Índices: `{tenantId, timestamp: -1}`, `{orderId, timestamp: 1}`, `{operatorId, timestamp: -1}`.

### 2.2 QualityRecord (registro de inspección)

| Campo | Tipo | Notas |
|---|---|---|
| `tenantId` | ObjectId -> Tenant | requerido, indexado |
| `orderId` | ObjectId -> Order | requerido, indexado |
| `workstationId` | String | ID de puesto **desde la config del Tenant** (no es ObjectId), requerido |
| `operatorId` | ObjectId -> User | requerido |
| `stockItemId` | ObjectId -> StockItem | opcional (trazabilidad de material si hay auditoría activa) |
| `manufacturingModelId` | ObjectId -> ManufacturingModel | requerido (plantilla usada) |
| `measurements[]` | subdocumentos | `checkName` (String req), `valueEntered` (Mixed: Number o Boolean), `isPassed` (Boolean req), `nominal` (Number), `tolPlus` (Number), `tolMinus` (Number) |
| `overallStatus` | enum | `approved`, `rejected`, `rework`; requerido, indexado |
| `notes` | String | opcional |

Índices: `{tenantId, orderId}`, `{tenantId, createdAt: -1}`, `{tenantId, overallStatus}`.

### 2.3 ManufacturingModel.qualityPlan (plantilla de controles)

Cada check del plan: `name` (req, ej: "Largo Total"), `type` (enum `numeric` | `pass_fail` | `visual`, default `numeric`), `toolId` (String, ej: "Calibre", "Micrómetro"), `nominalValue` (Number), `tolerancePlus` (Number), `toleranceMinus` (Number), `isCritical` (Boolean, default `true`).

El `ManufacturingModel` además define `workstationIds[]` (puestos que pueden fabricar el modelo), `materialCode`, `technicalSpecs` (largo, ancho, espesor, peso, RAL, plano) y `predefinedLengths[]`. El control de calidad valida **cada check del plan** contra las mediciones introducidas por el operario.

### 2.4 Incidencia

| Campo | Tipo | Notas |
|---|---|---|
| `tenantId` | ObjectId -> Empresa | requerido, indexado |
| `ordenId` | ObjectId -> Order | default `null` (se asocia la orden activa de la línea si existe) |
| `lineaId` | String | puede ser ObjectId o string en V2; default `null` |
| `puesto` | String | nombre del puesto resuelto desde el Tenant, default `''` |
| `operarioId` | ObjectId -> User | requerido (quien reporta) |
| `descripcion` | String | requerido |
| `tipo` | enum | `maquina`, `material`, `seguridad`, `otro`; default `otro` |
| `foto` | String | URL de la foto (local o Cloudinary), default `null` |
| `estado` | enum | `abierta`, `en_revision`, `resuelta`, `cerrada`; default `abierta` |
| `historialEstados[]` | subdocumentos | `estado`, `usuario` (-> User), `timestamp` (default now), `comentario` |
| `resolucion` | objeto | `tipo` ('reparacion', 'cambio_pieza', 'ajuste', etc.), `descripcion`, `tiempoParada` (Number, **minutos**), `coste` (Number, **euros**), `responsableId` (-> User) |

Índices: `{tenantId, estado, createdAt: -1}`, `{tenantId, tipo}`.

### 2.5 Relaciones

- `ProductionLog.orderId -> Order`; `ProductionLog.lineId -> Order.lines[]._id` (emparejamiento por igualdad de IDs, ver MaintenanceService y OEE); `ProductionLog.operatorId -> User`; `ProductionLog.metadata.activeCoilId -> StockItem`.
- `QualityRecord.orderId -> Order`; `QualityRecord.operatorId -> User`; `QualityRecord.stockItemId -> StockItem` (opcional); `QualityRecord.manufacturingModelId -> ManufacturingModel` (cuyo `qualityPlan` es la plantilla evaluada).
- `Incidencia.ordenId -> Order` (opcional); `Incidencia.operarioId -> User`; `Incidencia.resolucion.responsableId -> User`; `Incidencia.lineaId` referencia débil al `workstationId` de la config del Tenant.
- El `OEE` consume `Incidencia.resolucion.tiempoParada` como downtime del periodo (`totalDowntimeMin` = suma de `tiempoParada` de incidencias creadas desde `startDate`).

## 3. Operaciones clave

### 3.1 Trazabilidad (TraceabilityService)

#### `logEvent({ tenantId, orderId, lineId, operatorId, action, quantity = 0, timestamp?, metadata = {} })`

- **Comportamiento**: crea un `ProductionLog` con `timestamp = timestamp || new Date()` y lo persiste. Devuelve el log guardado.
- **Invariantes**: el log es inmutable una vez escrito (schema `immutable: true`). El `action` debe pertenecer al enum. Si el guardado falla, se registra `❌ Critical Error in Traceability` y el error se **traga** (en un sistema real iría a una Dead Letter Queue); el llamador no recibe excepción. Esto implica que la trazabilidad es best-effort y no debe romper el flujo de planta.
- **Uso real observado**: en `QualityController.registerQualityCheck` se invoca con `action: 'quality_check'`, `quantity: 0` y metadata con `workstationId`, `status` (overallStatus), `manufacturingModel` (nombre), `measurementsCount`, `stockItemId`.

#### `getOrderTrace(tenantId, orderId)`

- **Comportamiento**: devuelve todos los logs de `tenantId + orderId` ordenados por `timestamp` ascendente, con `operatorId` poblado (`firstName lastName employeeNumber`) y `metadata.activeCoilId` poblado (`coilId lote`).
- **Invariantes**: es la fuente de la traza completa de una orden (serie temporal de eventos). Orden estricto por timestamp.

#### `getLastActiveSessionStart(tenantId, orderId, lineId, operatorId)`

- **Comportamiento**: busca el evento `start` o `resume` más reciente de esa combinación (operario + línea + orden). Si existe y hay un evento `pause`, `finish` o `stopped` **posterior** a ese start, la sesión lógica ya está cerrada y devuelve `null`. Si no hay stop posterior, devuelve el `lastStart` (sesión activa).
- **Invariantes**: se usa para calcular duración de sesiones de trabajo. Un start/resume sin cierre posterior es una sesión abierta; un start seguido de stop ya no cuenta. `stopped` se comenta como "strict enum map" (estado de línea detenida).

### 3.2 Autocontroles de calidad (QualityService + QualityController)

#### `evaluateNumeric(nominal, tolPlus, tolMinus, valueEntered)`

- **Comportamiento**: `maxLimit = nominal + tolPlus`; `minLimit = nominal - tolMinus`; devuelve `valueEntered >= minLimit && valueEntered <= maxLimit`.
- **Invariantes**: límites **inclusivos** (un valor exactamente en el límite pasa). Tolerancias asimétricas soportadas (tolPlus y tolMinus independientes).

#### `evaluateInspection(template, measurementsEntered, contextOverrides = {})`

- **Comportamiento**: recorre cada check del `template` (`ManufacturingModel.qualityPlan`). Para cada check busca la medición entrante con `m.checkName === check.name`; **si no existe, lo omite** (no cuenta como fallo). El nominal efectivo se resuelve como `contextOverrides[check.name]?.nominalValue ?? check.nominalValue`.
  - Tipo `numeric`: `isPassed = evaluateNumeric(nominalEfectivo, tolerancePlus, toleranceMinus, value)`.
  - Tipo `pass_fail` o `visual`: `isPassed = (value === true || value === 'pass' || value === 'OK')`.
  - Acumula en `processedMeasurements`: `{ checkName, valueEntered, isPassed, nominal (efectivo), tolPlus, tolMinus }`.
  - Si algún check falla: `allPassed = false`; si el check fallido tiene `isCritical`, `criticalFailed = true`.
- **Resultado**: `overallStatus = allPassed ? 'approved' : (criticalFailed ? 'rejected' : 'rework')`.
- **Invariantes**:
  - `approved`: todas las mediciones presentes pasan.
  - `rejected`: al menos un check **crítico** falla (prevalece sobre rework).
  - `rework`: hay fallos pero ninguno crítico.
  - Los checks sin medición entrante se ignoran silenciosamente (no bloquean el registro).

#### `registerQualityCheck(req)` (controller)

- **Entrada**: `{ orderId, workstationId, manufacturingModelId, stockItemId?, measurements, notes? }` más `req.user.{tenantId, id}`. Validación: `orderId`, `manufacturingModelId` y `measurements` obligatorios (400 si faltan); modelo inexistente -> 404.
- **Comportamiento**:
  1. Carga el `ManufacturingModel` (plantilla) y la `Order`.
  2. **Resolución de largos dinámicos**: busca la línea de la orden con `workstationId` igual y obtiene `orderLengthMm` con prioridad: `line.metros * 1000` -> `line.customFields.largo` -> `order.customFields.largo`. Si hay largo, aplica `contextOverrides[check.name] = { nominalValue: orderLengthMm }` a **todo check cuyo nombre matchee** `/largo\s*total|longitud/i` (ej: "Largo Total"). Esto permite validar la cota real de la orden y no el nominal de la plantilla.
  3. `evaluateInspection(model.qualityPlan, measurements, contextOverrides)`.
  4. Crea y guarda el `QualityRecord` con los measurements procesados y el `overallStatus`.
  5. Registra evento de trazabilidad `quality_check` (ver 3.1).
  6. Responde 201 con `msg: Inspección registrada: <STATUS>` y el record.
- **Invariantes**: el record guardado contiene SOLO los measurements procesados (con `isPassed`, `nominal` efectivo, tolerancias), no los crudos. Un autocontrol no bloquea la producción aunque el resultado sea `rejected` (el registro se persiste igualmente).

#### `getQualityRecords(req)` (controller)

- **Entrada**: `{ orderId?, limit = 20 }`; filtra por `tenantId` y opcionalmente `orderId`, ordena `createdAt` descendente, limita a `parseInt(limit)`.
- **Comportamiento**: puebla `operatorId` (`firstName lastName`) y `stockItemId` (`coilId lote`). Devuelve `{ success: true, records }`.

#### Recordatorios de autocontrol no bloqueantes (decisión 2026-05-18)

- **Disparo de inicio (15 minutos)**: si transcurren 15 min desde el inicio de la jornada (turno) sin registrar ningún control de calidad, se lanza el primer recordatorio en pantalla (toast).
- **Ciclo periódico (cada 2 horas)**: tras cada control de calidad registrado, el temporizador se reinicia y programa una alerta recurrente cada 120 minutos (2 h) para el siguiente control.
- **No bloqueantes**: son notificaciones asíncronas amigables (`react-hot-toast` con estilo Kavana Industrial). NUNCA bloquean la interfaz ni detienen la línea. La razón documentada: un bloqueo rígido generaría paradas no planificadas y afectaría el OEE del turno.
- **Reseteo de temporizadores**: al registrar un autocontrol con éxito, el frontend actualiza `lastQualityCheckTime` y `lastPeriodicQualityReminderTime` a `now`; el recordatorio periódico se calcula desde `lastPeriodicQualityReminderTime` (no desde el último check), evitando duplicados. El primer recordatorio solo se muestra una vez (`firstQualityReminderShown`).
- **Invariantes**: el backend no impone cadencia; los recordatorios son puramente de UI. La fuente de verdad de "cuándo se hizo el último control" son los `QualityRecord` (y el estado local de sesión del frontend).

### 3.3 Incidencias (IncidenciaController)

#### `create(req)`

- **Entrada**: `{ lineaId, descripcion, tipo, machineStatus?, fotoUrl? }` (operario autenticado). Validación: `lineaId`, `descripcion` y `tipo` obligatorios (400).
- **Comportamiento**:
  1. Resuelve el nombre del puesto (`puesto`) buscando `lineaId` en `tenant.workstations.standalone` y `groups[].workstations`.
  2. Busca la **orden activa** en esa línea: `Order.findOne({ tenantId, 'lines.workstationId': lineaId, status: 'active' })` ordenada por `createdAt` descendente. Si existe, la asocia como `ordenId`; si no, `ordenId = null`.
  3. Crea la incidencia con `operarioId = req.user.id`, `foto = fotoUrl || null` e `historialEstados` inicial `[{ estado: 'abierta', usuario, timestamp }]`.
  4. Si `machineStatus` viene y no es `'none'`, queda un TODO de cambio de estado de máquina (se loguea).
  5. Emite `nueva_incidencia` por Socket.IO a la sala del tenant.
- **Invariantes**: una incidencia nace SIEMPRE en `abierta`. `tipo` está restringido al enum. La foto es una URL (nunca binario en el documento).

#### `uploadMobilePhoto(req)` (público con sessionId)

- **Entrada**: `sessionId` en params + archivo subido (middleware `upload`).
- **Comportamiento**: con Cloudinary, `req.file.path` es la URL absoluta; guarda nada en BD, solo emite por Socket.IO `mobile_photo_uploaded` con `{ sessionId, fotoUrl }` (el cliente PC filtra por sessionId). Devuelve `{ success: true, fotoUrl }`.
- **Invariantes**: el flujo móvil es desacoplado: el móvil sube la foto, el PC la asocia a la incidencia en edición. Sin archivo -> 400.

#### `getAll(req)`

- **Comportamiento**: devuelve las incidencias del tenant ordenadas `createdAt` descendente, poblado `operarioId` (`nombre apellido`), con **límite duro de 50** registros (seguridad/rendimiento).

#### `update(req)` (resolver / cerrar / en revisión)

- **Entrada**: `{ id }` + `{ estado?, comentario?, resolucionTipo?, resolucionDesc?, tiempoParada?, coste? }`. Busca por `_id` **y** `tenantId` (aislamiento multi-tenant); si no existe -> 404.
- **Comportamiento**:
  - Si `estado`: lo asigna y hace push a `historialEstados` con `{ estado, usuario: req.user.id, timestamp, comentario: comentario || 'Estado cambiado a <estado>' }`.
  - Si `resolucionTipo` o `resolucionDesc`: construye/actualiza `resolucion` con `tipo`, `descripcion`, `tiempoParada: Number(...)`, `coste: Number(...)` (si vienen `undefined` conserva los previos) y `responsableId: req.user.id`.
  - Emite `incidencia_actualizada` por Socket.IO a la sala del tenant.
- **Invariantes**: `tiempoParada` se expresa en **minutos** y `coste` en **euros** (se convierten con `Number()` al guardar). El cierre financiero es la escritura de `resolucion`; el OEE suma `tiempoParada` de las incidencias del periodo como downtime. No hay regla que obligue a que `cerrada` requiera resolución completa (el estado y la resolución se actualizan de forma independiente).

## 4. Reglas de negocio críticas

1. **Inmutabilidad de la trazabilidad**: un `ProductionLog` no puede modificarse ni eliminarse (auditoría ISO 9001). El portado a PostgreSQL debe prohibir `UPDATE` y `DELETE` sobre la tabla de logs (o implementarlo vía permisos/triggers).
2. **Trazabilidad de orden completa**: `getOrderTrace` debe devolver la serie temporal completa y ordenada (timestamp asc) de eventos de una orden: start, pause, resume, produce (cantidad), scrap, finish, setup, close_shift, quality_check.
3. **Sesión de trabajo**: una sesión activa es un `start`/`resume` sin `pause`/`finish`/`stopped` posterior. `getLastActiveSessionStart` devuelve `null` si la sesión ya cerró. Este contrato alimenta el cálculo de duraciones y costes.
4. **Evaluación de calidad con tolerancias inclusivas**: pasa si `minLimit <= valor <= maxLimit`. El resultado global es `approved` (todo pasa), `rejected` (falla algún check crítico) o `rework` (fallan solo no críticos). `rejected` prevalece.
5. **Largos dinámicos de orden**: las cotas tipo "Largo Total" se validan contra el largo REAL de la orden (prioridad: `line.metros * 1000` -> `line.customFields.largo` -> `order.customFields.largo`), no contra el nominal de la plantilla. Patrón: `/largo\s*total|longitud/i`.
6. **Checks sin medición no bloquean**: un check del plan sin valor entrante se omite. El operario no queda bloqueado por no medir todo.
7. **Autocontroles no bloqueantes**: los recordatorios (15 min al inicio, luego cada 2 h) son solo notificaciones; el registro de un autocontrol nunca interrumpe la producción, aunque el resultado sea `rejected`.
8. **Incidencias y downtime**: los minutos de parada declarados en `resolucion.tiempoParada` de incidencias del periodo alimentan el cálculo de disponibilidad/OEE (`totalDowntimeMin`). Es la única fuente de downtime "declarado" por incidencia.
9. **Aislamiento multi-tenant**: todas las consultas y actualizaciones filtran por `tenantId` (incluida la búsqueda de incidencia por `_id + tenantId`).
10. **Límites de listado**: incidencias y registros de calidad con límite (50 y 20 respectivamente) para no degradar la UI de planta.

## 5. Casos límite conocidos

- **Fallo de persistencia del log**: `logEvent` captura el error y no lo propaga (best-effort, DLQ en sistemas reales). El registro de calidad puede completarse aunque falle el evento de trazabilidad asociado.
- **Valor exactamente en el límite**: `evaluateNumeric` usa comparaciones inclusivas, un valor igual a `nominal + tolPlus` o `nominal - tolMinus` pasa.
- **`valueEntered` no numérico en check `numeric`**: la comparación aritmética con un valor no numérico produce `false` (fallo), que si es crítico deriva en `rejected`.
- **Valores válidos de pass_fail/visual**: solo `true`, `'pass'`, `'OK'` pasan. Cualquier otra cadena (ej: `'ok'` en minúsculas, `'PASS'`) falla. Portar la normalización tal cual o documentarla como mejora.
- **Check del plan sin medición**: se omite, no falla (puede dar `approved` con controles sin medir).
- **Orden sin largo resoluble**: si no hay `line.metros`, `customFields.largo` en línea ni en orden, no hay override y se usa el nominal de la plantilla.
- **Incidencia sin orden activa**: `ordenId = null` (la línea puede estar parada sin orden en curso).
- **Doble clic en logout / estado**: `update` con `estado` repetido es idempotente en el sentido de que solo añade una entrada al historial.
- **`tiempoParada`/`coste` ausentes en resolución**: si se actualiza la resolución sin esos campos, conserva los valores previos (`incidencia.resolucion?.tiempoParada`).
- **Foto sin archivo**: `uploadMobilePhoto` devuelve 400; el flujo de incidencia tolera incidencias sin foto (`foto: null`).
- **Consulta de registros sin `orderId`**: `getQualityRecords` sin filtro de orden devuelve los últimos 20 del tenant.

## 6. Requisitos para el modelo relacional (PostgreSQL)

### Tabla `production_logs` (trazabilidad, inmutable)

| Columna | Tipo | Constraints |
|---|---|---|
| `id` | BIGSERIAL | PK |
| `tenant_id` | BIGINT | NOT NULL, FK -> `tenants.id`, INDEX |
| `order_id` | BIGINT | NOT NULL, FK -> `orders.id`, INDEX |
| `line_id` | BIGINT | NOT NULL, FK -> `order_lines.id` (la línea DENTRO de la orden), INDEX |
| `operator_id` | BIGINT | NOT NULL, FK -> `users.id` |
| `timestamp` | TIMESTAMPTZ | NOT NULL, default now(), INDEX `(tenant_id, timestamp DESC)`, `(order_id, timestamp ASC)`, `(operator_id, timestamp DESC)` |
| `action` | TEXT | NOT NULL, CHECK `action IN ('start','pause','resume','finish','produce','scrap','setup_start','setup_finish','close_shift','stopped','quality_check')` |
| `quantity` | NUMERIC(14,3) | NOT NULL, default 0 |
| `metadata` | JSONB | NOT NULL, default '{}' (reason, efficiency, incrementalCost, activeCoilId, etc.) |
| `shift` | TEXT | NULL, CHECK `shift IN ('morning','afternoon','night')` |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() |

- **Inmutabilidad**: revocar `UPDATE` y `DELETE` a los roles de aplicación sobre esta tabla; alternativa: trigger `BEFORE UPDATE OR DELETE` que lance excepción. Nunca exponer endpoints de modificación/borrado.
- `metadata` JSONB permite evolución sin migraciones (el legacy es un documento flexible).

### Tabla `quality_records`

| Columna | Tipo | Constraints |
|---|---|---|
| `id` | BIGSERIAL | PK |
| `tenant_id` | BIGINT | NOT NULL, FK -> `tenants.id` |
| `order_id` | BIGINT | NOT NULL, FK -> `orders.id` |
| `workstation_id` | TEXT | NOT NULL (ID de puesto de la config del tenant, no FK dura) |
| `operator_id` | BIGINT | NOT NULL, FK -> `users.id` |
| `stock_item_id` | BIGINT | NULL, FK -> `stock_items.id` (opcional) |
| `manufacturing_model_id` | BIGINT | NOT NULL, FK -> `manufacturing_models.id` |
| `overall_status` | TEXT | NOT NULL, CHECK `IN ('approved','rejected','rework')` |
| `notes` | TEXT | NULL |
| `created_at`, `updated_at` | TIMESTAMPTZ | NOT NULL |

- Índices: `(tenant_id, order_id)`, `(tenant_id, created_at DESC)`, `(tenant_id, overall_status)`.

### Tabla `quality_measurements` (hija de quality_records)

| Columna | Tipo | Constraints |
|---|---|---|
| `id` | BIGSERIAL | PK |
| `quality_record_id` | BIGINT | NOT NULL, FK -> `quality_records.id` ON DELETE CASCADE |
| `check_name` | TEXT | NOT NULL |
| `value_entered` | JSONB | NOT NULL (Number o Boolean; Mixed del legacy) |
| `is_passed` | BOOLEAN | NOT NULL |
| `nominal` | NUMERIC(14,3) | NULL (nominal EFECTIVO, ya con override de largo) |
| `tol_plus` | NUMERIC(14,3) | NULL |
| `tol_minus` | NUMERIC(14,3) | NULL |

- UNIQUE `(quality_record_id, check_name)`: un check por registro (el legacy sobrescribe por nombre).

### Tabla `manufacturing_models` (mínimo para calidad)

- `id`, `tenant_id` FK, `code` (UNIQUE por tenant), `name`, `description`, `material_code`, `is_active`, timestamps.
- UNIQUE `(tenant_id, code)`.

### Tabla `quality_plan_checks` (plantilla, hija de manufacturing_models)

| Columna | Tipo | Constraints |
|---|---|---|
| `id` | BIGSERIAL | PK |
| `manufacturing_model_id` | BIGINT | NOT NULL, FK -> `manufacturing_models.id` ON DELETE CASCADE |
| `name` | TEXT | NOT NULL |
| `type` | TEXT | NOT NULL, CHECK `IN ('numeric','pass_fail','visual')` |
| `tool_id` | TEXT | NULL |
| `nominal_value` | NUMERIC(14,3) | NULL |
| `tolerance_plus` | NUMERIC(14,3) | NULL |
| `tolerance_minus` | NUMERIC(14,3) | NULL |
| `is_critical` | BOOLEAN | NOT NULL, default TRUE |

- Orden de los checks preservado con `position INT NOT NULL` (el orden del array legacy importa para la UX del formulario).

### Tabla `incidencias`

| Columna | Tipo | Constraints |
|---|---|---|
| `id` | BIGSERIAL | PK |
| `tenant_id` | BIGINT | NOT NULL, FK -> `tenants.id` |
| `order_id` | BIGINT | NULL, FK -> `orders.id` |
| `linea_id` | TEXT | NULL (workstationId de la config del tenant) |
| `puesto` | TEXT | NOT NULL, default '' |
| `operario_id` | BIGINT | NOT NULL, FK -> `users.id` |
| `descripcion` | TEXT | NOT NULL |
| `tipo` | TEXT | NOT NULL, CHECK `IN ('maquina','material','seguridad','otro')`, default 'otro' |
| `foto` | TEXT | NULL (URL local o Cloudinary) |
| `estado` | TEXT | NOT NULL, CHECK `IN ('abierta','en_revision','resuelta','cerrada')`, default 'abierta' |
| `resolucion_tipo` | TEXT | NULL |
| `resolucion_descripcion` | TEXT | NULL |
| `tiempo_parada_min` | NUMERIC(10,2) | NULL, CHECK `>= 0` (minutos) |
| `coste` | NUMERIC(12,2) | NULL, CHECK `>= 0` (euros) |
| `responsable_id` | BIGINT | NULL, FK -> `users.id` |
| `created_at`, `updated_at` | TIMESTAMPTZ | NOT NULL |

- Índices: `(tenant_id, estado, created_at DESC)`, `(tenant_id, tipo)`.
- La resolución financiera (tipo, descripcion, minutos, coste, responsable) se modela como columnas nullable en la misma fila (el legacy la trata como objeto embebido con actualización parcial: cada campo conserva su valor previo si no viene en el update).

### Tabla `incidencia_historial_estados` (hija de incidencias)

| Columna | Tipo | Constraints |
|---|---|---|
| `id` | BIGSERIAL | PK |
| `incidencia_id` | BIGINT | NOT NULL, FK -> `incidencias.id` ON DELETE CASCADE |
| `estado` | TEXT | NOT NULL (mismo CHECK que incidencias.estado) |
| `usuario_id` | BIGINT | NOT NULL, FK -> `users.id` |
| `timestamp` | TIMESTAMPTZ | NOT NULL, default now() |
| `comentario` | TEXT | NULL |

- La primera fila del historial se inserta en el alta (`abierta`).

### Notas de portado

- **Cadencia de recordatorios**: es lógica de UI (toasts), no de backend. El backend solo debe exponer la consulta de últimos controles para que el frontend calcule los 15 min y las 2 h. No crear jobs de recordatorio en el backend sin necesidad.
- **Índice compuesto clave para OEE**: `incidencias(tenant_id, created_at)` para sumar `tiempo_parada_min` del periodo (consulta actual del OEE).
- **Normalización de pasafalla**: el legacy acepta `true`, `'pass'`, `'OK'`; si el portado quiere normalizar mayúsculas/minúsculas, debe hacerlo en el servicio de evaluación y documentarlo como cambio de contrato.
