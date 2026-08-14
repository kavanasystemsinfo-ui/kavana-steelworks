# Spec 02 - Órdenes de producción

Dominio: MES/MOM metalúrgico KAVANA. Contrato de comportamiento extraído del
backend legacy v2 (Express + Mongoose + MongoDB) para la reconstrucción
FastAPI + PostgreSQL con TDD.

## 1. Fuente legacy

| Archivo | Rol |
|---|---|
| `/root/kavanasystems/backend/src/services/OrderService.js` (1519 líneas) | Servicio principal: ciclo de vida de órdenes, líneas, producción, costes, eficiencia, undo. Singleton exportado (`module.exports = new OrderService()`). |
| `/root/kavanasystems/backend/src/models/Order.js` | Schema `Order` + `LineaOrdenSchema` embebido, índices, hook cascade delete. |
| `/root/kavanasystems/backend/src/models/ProductionLog.js` | Log de auditoría inmutable de eventos de producción. |
| `/root/kavanasystems/backend/src/models/ManufacturingModel.js` | Plantilla de pieza (velocidad teórica, consumo unitario, specs). |
| `/root/kavanasystems/backend/src/models/MaterialConsumo.js` | Consumos de material por lote/bobina + hooks de roll-up a la orden. |
| `/root/kavanasystems/backend/src/services/TraceabilityService.js` | `logEvent` (escribe ProductionLog) y `getLastActiveSessionStart` (sesión activa). |
| `/root/kavanasystems/backend/src/services/ValidationService.js` | Aliasing de campos (`findValueByAlias`) y cálculo de costes de línea alternativo. |
| `/root/kavanasystems/backend/src/controllers/shiftController.js` | Apertura/cierre de turno de operario (UserShift). |
| `/root/kavanasystems/backend/src/services/AuthService.js` | Creación de turno en login y auto-cierre de turnos stale (> 14 h). |

## 2. Entidades y relaciones

### 2.1 Order (orden de producción)

- `tenantId` (ObjectId ref Tenant, obligatorio, indexado).
- `orderNumber` (String, obligatorio; formato `ORD-XXXX` o `TMP-<Date.now()>` si no se provee).
- `client` (String), `priority` enum `['low','medium','high','urgent']` (default `medium`).
- `status` enum `['draft','active','completed','cancelled']` (default `draft`).
- `lines`: array embebido de `LineaOrdenSchema` (cada línea con `_id` propio).
- `hasRal` (bool, default false), `ralCode` (String nullable).
- `customFields` (Mixed, default `{}`), `specifications` (array de `{name, value, unit}`).
- Finanzas: `estimatedTotalCost`, `realTotalCost`, `estimatedMargin` (precio venta - coste estimado; se almacena, no se calcula en OrderService).
- `createdBy` (ref User), `isDeleted` (bool, default false), `timestamps` (`createdAt`, `updatedAt`).
- Índices: `{tenantId, orderNumber}` único; `{tenantId, status, createdAt: -1}`; `{tenantId, 'lines.workstationId', 'lines.visibility'}`.
- Hook `pre('findOneAndDelete')`: borra en cascada `MaterialConsumo`, `ProductionLog` y `QualityRecord` de la orden (patrón Master-Detail).

### 2.2 OrderLine (línea de orden, embebida)

- `sequence` (Number, obligatorio; 1, 2, 3... lógica waterfall), `workstationId` (String, obligatorio, ej. `'laser'`), `workstationName`.
- `materialCode` (String), `metros` (Number, default 0; metros por pieza para BOM).
- `totalQuantity` (Number, min 0, obligatorio; objetivo), `producedQuantity` (Number, default 0; piezas buenas).
- `status` enum `['pending','in_progress','completed','stopped']` (default `pending`).
- `visibility` enum `['list','queue']` (default `list`).
- `customFields` (Mixed; contiene `largo`, `ancho`, `espesor`, `manufacturingModel`, `componentCode`, `isComponent`, `parentProduct`, `activeCoilId`, `materialName`...), `specifications`.
- Finanzas de línea: `estimatedCost` (incluye material + mano de obra), `realCost` (acumulado en vivo).
- Tiempo: `estimatedTime` (minutos estándar), `realTime` (minutos reales acumulados).
- Material (target vs real): `targetMaterialCost`, `targetMaterialQty`, `targetMaterialUnit` (default `'uds'`; puede ser `m`, `kg`, `liters`), `realMaterialCost`, `realMaterialQty`, `scrapMaterialQty` (merma de punta de bobina, NO desperdicio de proceso).
- Eficiencia: `efficiency` (porcentaje, nullable), `manufacturingModelId` (ref ManufacturingModel).
- Sesión WIP: `sessionStartTime` (Date, ancla temporal), `activeOperator` `{id, firstName, lastName}`.

### 2.3 ProductionLog (bitácora de auditoría)

- Inmutable (`immutable: true` en Mongoose; no se pueden modificar ni borrar salvo `undoProduction` que borra el log original y registra `undo_produce`).
- `tenantId`, `orderId` (ref Order), `lineId` (ObjectId de la línea dentro de la orden, sin ref), `operatorId` (ref User), `timestamp` (default now).
- `action` enum `['start','pause','resume','finish','produce','scrap','setup_start','setup_finish','close_shift']`.
- `quantity` (default 0; piezas en `produce`/`scrap`).
- `metadata` (Mixed): `reason`, `materialBatch`, `notes`, `device`, `totalRealized`, `consumedMaterial`, `consumedAmount`, `incrementalCost`, `incrementalMaterialCost`, `incrementalLaborCost`, `efficiency`, `observaciones`, `workstationName`, `manufacturingModel`, `activeCoilId`, `activeCoilCode`, `targetMaterialQty`, `targetMaterialUnit`, `materialConsumoIds` (IDs exactos de MaterialConsumo para undo preciso).
- `shift` enum `['morning','afternoon','night']`: declarado pero NUNCA poblado en runtime (comentario "Futuro"). Es el placeholder de la lógica de turnos A-B-C; el modelo operativo real de turnos es `UserShift`.
- Índices: `{tenantId, timestamp: -1}`, `{orderId, timestamp: 1}`, `{operatorId, timestamp: -1}`.

### 2.4 ManufacturingModel (plantilla de pieza)

- `tenantId`, `code` (uppercase, trim), `name`, `description`.
- `workstationIds` (array de Strings: puestos que pueden fabricar el modelo).
- `materialCode` (ref Material.code), `defaultQuantity` (default 1).
- **Velocidad teórica**: `unitsPerHour` (Number, default 0; piezas por hora o metros por hora) + `productionUnit` enum `['units','meters']` (default `units`).
- `technicalSpecs`: `largo` (mm), `finalLength` (mm, longitud real según plano), `scrapGap` (mm, pérdida por corte, default 0), `ancho` (mm), `espesor` (mm), `peso` (kg/unidad legacy), `pesoUnitario` (kg/pieza; override manual, si > 0 se usa en vez de la fórmula de densidad), `ral`, `blueprintUrl`, `customFields`.
- `predefinedLengths` `[{value (mm), label}]`, `qualityPlan` `[{name, type enum ['numeric','pass_fail','visual'], toolId, nominalValue, tolerancePlus, toleranceMinus, isCritical}]`.
- `isActive` (default true).
- **Virtual `realUnitConsumptionMeters`**: `(finalLength || largo + scrapGap) / 1000` (metros reales consumidos por pieza, incluye merma de corte).
- Índices: `{tenantId, code}` único; `{tenantId, workstationIds}`; `{tenantId, isActive}`.

### 2.5 MaterialConsumo (consumo de material por lote)

- `tenantId`, `orderId` (ref Order), `workstationId` (String), `materialId` (ref Material), `stockItemId` (ref StockItem, nullable), `lote` (snapshot).
- `consumedQuantity` (obligatorio; cantidad REAL descontada del stock), `unit` (default `m`).
- Contexto: `producedQuantity` (piezas fabricadas), `metersPerPiece`, `kgPorPieza`, `calculationMethod` enum `['density_formula','model_override','meters_legacy','bom_static','manual','coil_end_scrap','manual_late_registration','none']`.
- Costes (snapshot): `costPerUnit`, `totalCost` (calculado en `pre('save')`: `round(consumedQuantity * costPerUnit, 2)`).
- `tipo` enum `['automatico','manual','ajuste','auto_audit','merma_puntas','salida_produccion']` (default `automatico`).
- `operatorId`, `date`, `observaciones`, timestamps.
- **Hook `post('save')`**: si `tipo` en `['automatico','manual','ajuste']` y `totalCost > 0`, hace `$inc` en la Order: `realMaterialCost += totalCost` y `realTotalCost += totalCost`. Los tipos `auto_audit` y `merma_puntas` NO hacen roll-up (el material ya se cargó en bulk al vincular la bobina).
- **Hook `post('findOneAndDelete')`**: mismo filtro de tipos, `$inc` negativo (resta).

### 2.6 UserShift (turno de operario)

- `tenantId`, `operatorId` (ref User), `loginTime` (obligatorio, default now), `logoutTime`, `totalHours`, `status` enum `['active','completed']` (default `active`).
- `ordersHandled` (array de ref Order), `globalEfficiency` (OEE global de la jornada), `metadata` `{device, notes}`.
- Índices: `{tenantId, operatorId, status}`, `{tenantId, loginTime: -1}`.

### 2.7 Entidades dependientes (contexto)

- `Tenant`: `workstations.standalone[]` y `workstations.groups[].workstations[]` con `{id, hourlyCost, materialBOM, activeTool}`; `finances.operatorCategories[]` con `{id, hourlyCost}` (default categoría `peon_especialista`); `finances.overheadHourlyCost`; `plan.features.materialTrackingMode` (`'simple'` | `'audit'`).
- `Material`: `code`, `name`, `costPerUnit`, `density` (default 7850 kg/m3, acero), `dimensions.ancho/espesor`.
- `StockItem` (bobina/lote): `estado` enum (`activo`, `pico`, `agotado`), `cantidadDisponible`, `ubicacion`, `width`, `thickness`, `materialId`, `lote`, `coilId`, `fechaEntrada`.
- `User`: `roles` (array; `operator`, `supervisor`, `admin`), `operatorCategory`, `firstName`, `lastName`.
- `Tooling`: `currentCycles`, `maxCycles`.
- `QualityRecord`: se borra en cascada con la orden (no se detalla aquí; spec 04).

## 3. Operaciones clave

### 3.1 `createOrder(tenantId, userId, rawData)` -> Order

Comportamiento:
1. Construye cabecera con defaults: `orderNumber = rawData.orderNumber || 'TMP-' + Date.now()`, `priority = 'medium'`, `status = 'draft'`, `hasRal = false`, `ralCode = null`, `customFields = {}`, `specifications = []`.
2. **Caso A (productId, BOM explosion)**: carga `Product` con `components.manufacturingModelId` poblado. Si el producto tiene componentes:
   - Valida especificaciones contra `product.specificationTemplates` (`_validateSpecifications`): obligatorias, rangos numéricos (min/max) y regex.
   - Pre-fetches materiales de los componentes (`code -> density`, default 7850).
   - Para cada componente: `compQty = quantityPerKit * orderQuantity`. Calcula material teórico target:
     - Si `realLengthMeters > 0 && ancho > 0 && espesor > 0`: `targetQty = realLengthMeters * (ancho/1000) * (espesor/1000) * densidad * compQty`, unidad `kg` (fórmula de densidad).
     - Si no, y `pesoUnitario > 0`: `targetQty = pesoUnitario * compQty`, unidad `kg`.
     - Si no: `targetQty = compQty`, unidad `uds`.
   - Routing: si el componente define `routing` se usa; si no, fallback a `model.workstationIds` como secuencia 1..n.
   - `estimatedTime` por línea: `(step.estimatedTimePerUnit || (1 / (model.unitsPerHour || 1)) * 60) * compQty` minutos (conversión velocidad teórica a tiempo estándar).
   - Puebla `customFields` de línea con `manufacturingModel`, `componentCode`, `isComponent: true`, `parentProduct`, `largo`, `ancho`, `espesor`.
   - `specLargo` se resuelve con `ValidationService.findValueByAlias` (aliases: largo, longitud, medida_corte, medida, length).
   - Si el producto solo tiene `phases` (fallback legacy): una línea por fase con `estimatedTime = phase.estimatedTime * quantity`.
3. Delega el cálculo financiero a `calculateOrderLines(tenantId, linesToProcess)`.
4. Persiste con `new Order(orderData).save()` (la validación de Mongoose lanza errores de validación al caller).

Invariantes: la orden se crea siempre en `draft` salvo que el caller indique otro estado; `estimatedTotalCost` se calcula en el servidor, nunca se confía en el cliente; sin producto ni líneas, se crea una orden vacía.

### 3.2 `calculateOrderLines(tenantId, linesRaw)` -> `{lines, estimatedTotalCost}` (calculador reutilizable)

Comportamiento:
1. Construye `workstationConfig` desde `tenant.workstations` (standalone + grupos): `{id -> {hourlyCost, materialBOM}}`.
2. Pre-fetches materiales (`code -> {costPerUnit, name, density}`), densidad default 7850.
3. Por cada línea cruda:
   - `orderQuantity = lineRaw.orderQuantity || 1`; si falta `totalQuantity`, se copia `orderQuantity`.
   - `estimatedTimeMinutes = lineRaw.estimatedTime || 0` (SE CONFÍA en el frontend; no se recalcula con el modelo para evitar doble query).
   - `costLabor = (estimatedTime / 60) * hourlyCost` (minutos a horas por coste horario de puesto).
   - Si hay `_bom` y `materialCode`: `targetMaterialQty = totalQuantity * dynamicConsumptionRate`, `targetMaterialCost = targetMaterialQty * material.costPerUnit`.
     - `dynamicConsumptionRate`: si `customFields.largo > 0` y el `materialCode` casa con el regex `/(\d{2,4})\s*[xX]\s*(\d{1,3}(?:[,.]\d+)?)/` (extrae ancho x espesor del código, ej. `100x0.60`), con `ancho <= 2500` y `espesor <= 25`: `rate = largo_m * (ancho/1000) * (espesor/1000) * densidad`. Si no casa, se usa `bom.consumptionRate` estático.
   - `estimatedCost (línea) = costLabor + targetMaterialCost` (OJO: el material YA está incluido en estimatedCost de línea).
   - `estimatedTotalCost = Σ estimatedCost` de todas las líneas.
4. Normaliza cada línea: `sequence = index + 1`, `producedQuantity = 0`, `status = 'pending'`, `visibility = 'list'`, `realCost = 0`, `realTime = 0`, `realMaterialCost = 0`, `realMaterialQty = 0`, `targetMaterialUnit = bom?.unit || 'uds'`, `customFields.materialName = nombre del material`.
5. Redondeos: `estimatedCost` y `estimatedTotalCost` a 2 decimales; `targetMaterialQty` a 4 decimales en el caso de producto (3.1).

Invariantes: `estimatedTotalCost >= 0`; el orden de secuencia de líneas es el del array de entrada; los campos financieros de salida nunca son negativos por construcción.

### 3.3 `updateLineStatus(tenantId, orderId, lineId, newStatus, userId)` -> Order

Comportamiento:
1. Valida `newStatus` en `['pending','in_progress','completed','stopped']`.
2. **Seguridad de rol**: el usuario debe tener rol `operator`, `supervisor` o `admin`; si no, lanza `'No tienes permisos suficientes para cambiar el estado de esta orden.'`.
3. Localiza orden + línea (`'lines._id': lineId`); si no existe, `'Order not found or line non-existent'`.
4. **Auto-vinculación de bobina** (KAVANA Industrial): si `newStatus === 'in_progress'` y la línea no tiene `customFields.activeCoilId`, busca en `StockItem` la bobina activa residual del puesto: `estado in ['activo','pico']`, `cantidadDisponible > 0`, `ubicacion` igual al `workstationId` (con normalización: sin espacios, uppercase, o regex de espacios), ordenada por `updatedAt`/`fechaEntrada` desc. Si la encuentra, llama `InventoryService.linkCoil` y recarga la orden para sincronizar estado en memoria. Los errores de este paso se loguean y NO abortan la operación.
5. Construye `$set`:
   - `lines.$.status = newStatus`.
   - Si `in_progress`: `activeOperator = {id, firstName, lastName}` del usuario, `sessionStartTime = new Date()` (ancla temporal para reconstruir OEE tras pérdida de WiFi), `efficiency = 0` (reset para evitar eficiencia histórica stale).
   - Si no es `stopped`: limpia `activeOperator` (null) y `sessionStartTime = null`.
   - Si `stopped` (pausa): limpia `sessionStartTime` pero CONSERVA `activeOperator`.
6. **Coste de sesión y OEE de sesión** (solo si la línea estaba `in_progress` y pasa a `completed` o `stopped`):
   - `lastStartLog = TraceabilityService.getLastActiveSessionStart(tenantId, orderId, lineId, userId)` (último evento `start`/`resume` sin `pause`/`finish`/`stopped` posterior; si hay stop posterior devuelve null = sesión ya cerrada).
   - `durationHours = (Date.now() - lastStartLog.timestamp) / 3600000`.
   - Coste real de sesión: `incrementalCost = durationHours * (machineHourlyCost + operatorHourlyCost + overheadHourlyCost)` donde machineHourlyCost sale de `tenant.workstations` (standalone o grupo), operatorHourlyCost de `tenant.finances.operatorCategories` según `user.operatorCategory` (default `peon_especialista`), overheadHourlyCost de `tenant.finances.overheadHourlyCost`. Si no hay configuración, cada componente es 0.
   - OEE de sesión: suma `quantity` de los logs `produce` de la sesión; si `model.unitsPerHour > 0`, `actualProducedValue = sessionPieces` (o `sessionPieces * largoMm / 1000` si `productionUnit === 'meters'`), `capacity = unitsPerHour * durationHours`, `efficiency = (actualProducedValue / capacity) * 100` (2 decimales). Si `capacity <= 0`, efficiency 0.
   - **Audit log crítico** si `efficiency > 100` (indica desconfiguración del modelo).
7. `$inc` (solo si `incrementalCost > 0`): `lines.$.realCost += incrementalCost`, `realTotalCost += incrementalCost`, `lines.$.realTime += durationHours * 60`.
8. Si `newStatus === 'completed'`: `lines.$.producedQuantity = totalQuantity` (copia del objetivo, $set).
9. Actualización atómica: `Order.findOneAndUpdate({_id, tenantId, 'lines._id': lineId}, {$set, $inc}, {new: true})`, poblado con `manufacturingModelId` (`unitsPerHour productionUnit`).
10. Trazabilidad: `logEvent` con action mapeada: `in_progress -> 'start'`, `stopped -> 'pause'`, `completed -> 'finish'`, resto `'resume'`; metadata con `previousStatus`, `newStatus`, `workstationName`, `manufacturingModel`, `efficiency` (si aplica).

Invariantes: la transición de estados es un único `findOneAndUpdate` atómico (sin read-modify-write); el ancla `sessionStartTime` existe únicamente mientras la línea está `in_progress`; al completar, `producedQuantity == totalQuantity`; el coste de sesión solo se cobra UNA vez por sesión (la sesión se considera cerrada al pausar/completar).

### 3.4 `recordProduction(tenantId, userId, orderId, lineId, incrementalQuantity, hoursWorked = 0, observaciones = '', activeCoilId = null, nextStatus = null)` -> `{order, log}`

Comportamiento:
1. Carga en paralelo Order (+ línea), Tenant y User.
2. **Seguridad**: solo rol `operator` (lanza `'Permiso denegado: Solo los usuarios con el rol de operario pueden registrar producción.'`).
3. Validación de entrada: `incrementalQuantity` no NaN y `>= 0`; si `incrementalQuantity === 0 && hoursWorked <= 0` lanza `'Must provide either quantity or hours worked (for shift closing)'`.
4. **Modo Auditoría**: si `materialTrackingMode === 'audit'` y `incrementalQuantity > 0` sin `activeCoilId`, lanza `'Modo Auditoría: Debe escanear una bobina antes de registrar producción.'`.
5. **WIP waterfall**: para `lineIndex > 0`, `availableWIP = (previousLine.producedQuantity) - currentRealized` (piezas del paso anterior menos lo ya consumido por esta línea); si `incrementalQuantity > availableWIP`, lanza `'WIP insuficiente: El paso anterior solo ha entregado X piezas. Disponibles para este proceso: Y'`. La primera línea (índice 0) no se valida.
6. Resuelve el ManufacturingModel (`_resolveManufacturingModel`): prioridad `line.manufacturingModelId` > `customFields.manufacturingModel` (match por `code` o `name`) > primer modelo activo cuyo `workstationIds` contenga el puesto.
7. **Auto-consumo** (solo si `incrementalQuantity > 0`):
   - Material: prioridad `activeLot.materialId` (si `activeCoilId` válido) > `Material.findOne({tenantId, code: materialCode})`.
   - Cálculo de kg por pieza (prioridad):
     1. `model.technicalSpecs.pesoUnitario > 0` -> `kgPorPieza = pesoUnitario`, método `model_override`.
     2. Fórmula de densidad: si `ancho > 0 && espesor > 0` (de lote activo > customFields de línea > customFields de orden > material.dimensions): `kgPorPieza = largo_m * (ancho/1000) * (espesor/1000) * densidad` con `largo_m = model.realUnitConsumptionMeters` (incluye scrapGap) o fallback `largo/1000`; método `density_formula`.
     3. Fallback legacy: `metersPerPiece = realUnitConsumptionMeters || line.metros || customFields.largo/1000` -> `consumedAmount = qty * metersPerPiece` unidad `m`, método `meters_legacy`; si no, `rate = targetMaterialQty / totalQuantity` -> `consumedAmount = qty * rate` unidad `targetMaterialUnit`, método `bom_static`.
   - Si `kgPorPieza > 0`: `consumedAmount = round(qty * kgPorPieza, 4)`, unidad `kg`.
   - `incrementalMaterialCost = round(consumedAmount * material.costPerUnit, 2)`.
   - **Deducción de stock FIFO**:
     - Modo `simple`: `InventoryService.consumeStockFIFO({materialId, cantidadRequerida, orderId, lineaOrdenId, motivo})`.
     - Modo `audit`: mismo servicio con `workstationId` y `priorityStockItemId = activeCoilId` (FIFO por puesto priorizando la bobina vinculada).
   - Por cada lote utilizado crea un `MaterialConsumo` con `tipo = 'auto_audit'` (audit) o `'automatico'` (simple), `calculationMethod`, `kgPorPieza`, `costPerUnit`/`totalCost` del detalle FIFO, y guarda los IDs en `materialConsumoIds`.
   - **Manejo de fallos de consumo**: en modo `audit` se relanza el error y ABORTA la producción; en modo `simple` se resetea `consumedAmount = 0`, `incrementalMaterialCost = 0`, `kgPorPieza = 0`, `calculationMethod = 'none'` y la producción se registra IGUAL pero sin descuento de stock (nunca consumos fantasma).
8. **Desgaste de herramienta**: si el puesto tiene `activeTool`, `$inc currentCycles += incrementalQuantity` (errores no abortan).
9. **Coste laboral**: si `hoursWorked > 0`: `incrementalLaborCost = hoursWorked * (machineHourlyCost + operatorHourlyCost + overheadHourlyCost)` (mismos orígenes que 3.3).
10. **Nuevo estado**: `newStatus = 'in_progress'`; si `newTotalRealized >= totalRequired` -> `'completed'`; si no y hay `nextStatus` -> `nextStatus`.
11. **Reparación de targetMaterialQty** (órdenes legacy sin BOM): si `targetMaterialQty` es 0 y `kgPorPieza > 0` -> `totalRequired * kgPorPieza` en `kg`; si no y hay consumo -> `(consumedAmount / incrementalQuantity) * totalRequired` en la unidad de consumo.
12. **GUARDIA DE SEGURIDAD de kilos (modo auditoría)**: si `activeCoilId && incrementalQuantity > 0`: `kgPerUnit = (targetMaterialQty || theoreticalTotal) / totalQuantity`; `newTotalTheoretical = (producedQuantity + incrementalQuantity) * kgPerUnit`; `realLimit = line.realMaterialQty`; `tolerance = max(realLimit * 0.15, 150)` (tolerancia proporcional, cubre tolerancia comercial negativa de espesor). Si `newTotalTheoretical > realLimit + tolerance` lanza `'BLOQUEO DE SEGURIDAD: Los kilos teóricos acumulados (X kg) superarían a los kilos reales vinculados (Y kg) con margen de Z kg. ¿Olvidó registrar material?'`.
13. **Actualización atómica** (`findOneAndUpdate` con `$set` + `$inc`):
    - `$set`: `lines.$.status`; `activeOperator` si `in_progress`; limpiado si no es `stopped`; targets reparados.
    - `$inc`:
      - `lines.$.realTime += hoursWorked * 60`
      - `lines.$.producedQuantity += incrementalQuantity`
      - Con bobina (`activeCoilId`, modo auditoría): `lines.$.realCost += incrementalLaborCost`, `realTotalCost += incrementalLaborCost` (el material se cargó en bulk en linkCoil; NO se toca realMaterialQty).
      - Sin bobina (modo simple): `lines.$.realCost += incrementalMaterialCost + incrementalLaborCost`, `realTotalCost += incrementalLaborCost` (el material de la orden llega por el hook post-save de MaterialConsumo), `lines.$.realMaterialQty += consumedAmount`.
14. **Eficiencia**:
    - Si `hoursWorked > 0 && model.unitsPerHour > 0` (eficiencia acumulada): `realValue = producedQuantity` (o `producedQuantity * largoMm / 1000` si `productionUnit === 'meters'`); `realPerHour = realValue / (realTime / 60)`; `efficiency = (realPerHour / unitsPerHour) * 100` (2 decimales); `$set lines.$.efficiency` y `lines.$.manufacturingModelId`.
    - Si `hoursWorked === 0 && model.unitsPerHour > 0` y la línea está `in_progress` con `sessionStartTime` (OEE en vivo): `liveHours = (now - sessionStartTime)/3600000`; `stabilizedHours = max(liveHours, 0.016)` (piso de 1 minuto, estabilización cliente); `sessionPieces = Σ logs produce de la sesión + incrementalQuantity` (el log actual aún no se ha guardado); `actualProducedValue` con conversión a metros si aplica; `capacity = unitsPerHour * stabilizedHours`; `efficiency = (actual/capacity)*100`; `$set lines.$.efficiency` y se propaga en memoria para sockets.
15. **Log único de trazabilidad**: `actionType = (incrementalQuantity === 0 && hoursWorked > 0) ? 'close_shift' : 'produce'`. Metadata completa: `totalRealized`, `consumedMaterial`, `consumedAmount`, `targetMaterialQty`, `targetMaterialUnit`, `incrementalMaterialCost`, `incrementalLaborCost`, `incrementalCost`, `efficiency`, `observaciones`, `workstationName`, `manufacturingModel`, `activeCoilId`, `activeCoilCode` (`coilId || lote`), `materialConsumoIds`.
16. Devuelve `{order: updatedOrder, log}`.

Invariantes: `producedQuantity` nunca supera `totalQuantity` de forma permanente (el auto-complete lo corta); los `$inc` son atómicos (sin condiciones de carrera entre tablets); en modo simple un fallo de stock no bloquea la producción pero tampoco inventa consumos; en modo auditoría sin bobina NO hay producción; la GUARDIA DE SEGURIDAD impide kilos teóricos muy superiores a los reales vinculados.

### 3.5 `undoProduction(tenantId, userId, logId)` -> Order

Comportamiento (reversión enterprise de `produce` o `scrap`):
1. Busca el ProductionLog por `_id` + `tenantId`. Si no existe, `'Registro no encontrado'`. Solo anula `produce`/`scrap`; otro action lanza `'Tipo de registro no anulable: X. Solo produce/scrap.'`.
2. Separa costes: `materialCostToUndo = metadata.incrementalMaterialCost ?? 0`; `laborCostToUndo = metadata.incrementalLaborCost ?? metadata.incrementalCost ?? 0`.
3. **Reversión de stock** (si `activeCoilId && consumedAmount > 0`): `stockItem.cantidadDisponible += mat`; si `estado === 'agotado'` pasa a `'pico'`; registra transacción Kardex (`tipo: 'entrada_compra'`, motivo `ANULACIÓN PRODUCCIÓN/SCRAP`); recalcula agregados del material padre. Errores se loguean sin abortar.
4. **Borrado de MaterialConsumo**: modo enterprise: `deleteMany({_id: {$in: materialConsumoIds}, tenantId})` (IDs exactos guardados en metadata). Fallback legacy (logs antiguos sin IDs): `deleteMany` por `tenantId + orderId + workstationId + producedQuantity + consumedQuantity + createdAt` en ventana de ±30 segundos.
5. **Inversión de `$inc`**:
   - Si `scrap`: `lines.$.scrapMaterialQty -= (mat || qty)`; si no hay bobina, `lines.$.realMaterialQty += mat` (devuelve el material).
   - Si `produce`:
     - Con bobina (auditoría): `lines.$.realCost -= laborCostToUndo`, `realTotalCost -= laborCostToUndo`.
     - Sin bobina (simple): `lines.$.realCost -= (materialCostToUndo + laborCostToUndo)`, `realTotalCost -= idem`, `lines.$.realMaterialQty -= mat`.
     - En ambos: `lines.$.producedQuantity -= qty`.
   - `$set lines.$.status = 'in_progress'` (la línea se reabre SIEMPRE que haya cambios financieros que aplicar).
6. Borra el log original (`ProductionLog.deleteOne`) y registra evento `undo_produce` con `quantity: -qty` y metadata `{originalLogId, originalAction, revertedCost, revertedMaterial, reason}`.
7. Devuelve la orden actualizada; si no había cambios financieros, solo borra el log y devuelve la orden sin tocar.

Invariantes: la anulación es idempotente a nivel de log (el log original se elimina, no se marca); los IDs de MaterialConsumo en metadata hacen la reversión exacta; el kardex de stock queda auditable con motivo de anulación.

### 3.6 `updateOrder(tenantId, orderId, updateData, userId = null)` -> Order

Comportamiento:
1. Detecta progreso activo: `hasProgress = alguna línea con producedQuantity > 0 || status !== 'pending'`.
2. Actualiza cabecera (client, priority, orderNumber, status) + RAL + customFields, acumulando `changes` para el changelog de trazabilidad.
3. Si llegan `lines`: recalcula con `calculateOrderLines` y **fusiona preservando el progreso**: mantiene `_id` original de cada línea (para que los logs no se rompan), `producedQuantity`, `realCost`, `realTime`, `realMaterialQty`, `realMaterialCost`, `activeOperator`, `efficiency` y **crítico: `sessionStartTime`** (si se pierde, el OEE se recalcula con menos horas y se infla artificialmente). Recalcula estado: `produced >= total && total > 0` -> `completed`; `produced < total && status era completed` -> `stopped` (reabre si subió el objetivo).
4. Mutación in-place de `order.lines` (set/push/splice) para no regenerar ObjectIds; `estimatedTotalCost = recalculo`.
5. Trazabilidad: si `hasProgress && userId && changes`, registra `supervisor_edit` con `changes` y `supervisorName`; AuditLogger.warn si se edita una orden con progreso activo.

Invariantes: editar una orden en progreso NUNCA resetea producción/costes/tiempos; el ID de línea es estable entre ediciones.

### 3.7 `updateExecutionFields(tenantId, orderId, executionFields, userId)` -> Order

- Fusiona SOLO campos de ejecución en `order.customFields` (preserva las specs fijadas por el supervisor). Para tablet del operario.
- Trazabilidad: evento `EXECUTION_FIELDS_UPDATE` con `{before, after, fieldsUpdated}`.

### 3.8 `deleteOrder(tenantId, orderId, permanent = false)` -> `{success, id, permanent}`

- No permanente: `isDeleted = true` (soft delete; las queries lo excluyen por defecto).
- Permanente: `Order.findOneAndDelete` para activar el hook cascade que borra `MaterialConsumo`, `ProductionLog` y `QualityRecord` huérfanos (no corromper métricas OEE/costes).

### 3.9 Consultas

- `getOrdersByTenant(tenantId, includeDeleted = false)`: excluye `isDeleted` salvo flag; popula `lines.manufacturingModelId` (`unitsPerHour productionUnit`); ordena `createdAt` desc; **límite 50**.
- `getArchivedOrders(tenantId)`: `isDeleted: true`, ordena `updatedAt` desc, límite 50.

### 3.10 Helpers internos

- `_findWorkstation(tenantConfig, wsId)`: busca el puesto en `standalone` y luego en `groups`; devuelve config o null.
- `_resolveManufacturingModel(tenantId, line)`: prioridad `line.manufacturingModelId` > `customFields.manufacturingModel` (por `code` o `name`, `isActive: true`) > primer modelo activo por `workstationIds`.
- `_validateSpecifications(templates, specs)`: para cada plantilla, si `isRequired` y falta o está vacía -> throw; si `dataType === 'number'`, valida min/max con parseFloat; si hay `regex` y valor, valida formato.

### 3.11 Ciclo de turnos (UserShift)

- **Login** (`AuthService`): si existe turno `active` del operario y lleva > 14 h desde `loginTime` (turno stale/huérfano), se auto-cierra: `logoutTime = loginTime + 14h`, `totalHours = min(totalTimeSpent, 14)` o 8.0 si no computable, `status = 'completed'`, `ordersHandled` = órdenes únicas de los logs `produce|finish|close_shift` del rango, `globalEfficiency` = media de `metadata.efficiency` de esos logs. Después se crea un turno nuevo `active`. Si no hay turno activo, se crea uno.
- **JWT**: `expiresIn: '8h'` (TTL reducido a un turno).
- **`closeShift`** (`shiftController`): busca el turno activo del operario (404 si no existe); agrega logs desde `loginTime` con action en `['produce','finish','close_shift']`: órdenes únicas, media de `metadata.efficiency` (si no hay, 0), horas = `Σ log.timeSpent` si existe (en la práctica `timeSpent` no se persiste en el modelo, así que cae al fallback reloj) o `(logoutTime - loginTime)`, **cap: si > 14 h -> 8.0**; `status = 'completed'`; guarda.
- `getActiveShift` expone resumen en vivo con el mismo cap de 14 h -> 8 h.
- **OJO**: el campo `ProductionLog.shift` (`morning`/`afternoon`/`night`, turnos A-B-C) está declarado pero nunca se asigna en el código runtime; el turno operativo real es `UserShift` por sesión de login. La reconstrucción puede implementar A-B-C (mañana/tarde/noche) como derivación horaria del `timestamp`, pero el legacy NO lo hace.

## 4. Reglas de negocio críticas

1. **Cascada WIP (waterfall)**: una línea no puede producir más piezas de las que el paso anterior ha entregado (`prev.producedQuantity - current.producedQuantity`). Primera línea sin límite.
2. **Auto-complete**: `producedQuantity >= totalQuantity` -> línea `completed` automáticamente en `recordProduction`; en `updateLineStatus(completed)` se fuerza `producedQuantity = totalQuantity`.
3. **Modo Auditoría**: sin bobina escaneada no hay producción (ni registro, ni consumo, ni coste). El consumo FIFO en auditoría es por puesto con prioridad a la bobina vinculada.
4. **Guardia de kilos**: en auditoría, el peso teórico acumulado no puede superar el peso real vinculado + `max(15% del real, 150 kg)`. Protege contra olvidos de registro de material.
5. **No-kill policy / tolerancia proporcional**: la tolerancia fija de 0.1 kg causaba falsos positivos; se usa tolerancia proporcional porque `switchCoil` no se llama y `realMaterialQty` acumula pesos brutos sin descontar merma hasta fin de bobina.
6. **Los $inc son atómicos**: todas las actualizaciones de progreso/costes son `findOneAndUpdate` con `$set` + `$inc` en un solo documento (concurrencia de tablets).
7. **Roll-up de material**: solo `MaterialConsumo.tipo in ['automatico','manual','ajuste']` actualizan `Order.realMaterialCost` y `Order.realTotalCost` (post-save +). `auto_audit`/`merma_puntas` no (ya cargado en bulk por linkCoil).
8. **Simetría de costes en auditoría**: con bobina, `lines.$.realCost` y `realTotalCost` solo acumulan labor (`incrementalLaborCost`); sin bobina, `lines.$.realCost` acumula material + labor pero `realTotalCost` solo labor (el material llega por el hook).
9. **Logs inmutables**: ProductionLog no se actualiza jamás; la corrección es `undoProduction` (borra el original + evento `undo_produce`).
10. **Roles**: cambiar estados requiere `operator|supervisor|admin`; registrar producción requiere `operator`.
11. **Ancla temporal**: `sessionStartTime` es la fuente de verdad de duración de sesión (sobrevive pérdidas de WiFi); se limpia al pausar/completar, se conserva al editar la orden.
12. **Cascade delete**: borrado permanente de orden limpia MaterialConsumo, ProductionLog y QualityRecord para no corromper OEE/costes.
13. **Cap de turnos**: sesiones > 14 h se truncan a 8 h estándar en totalHours.
14. **Velocidad teórica**: `unitsPerHour` es la referencia de capacidad; si `productionUnit === 'meters'`, todo valor producido se convierte a metros con `piezas * largoMm / 1000` antes de comparar contra `unitsPerHour`.

## 5. Casos límite conocidos

- **Órdenes sin orderNumber**: se genera `TMP-<timestamp>`; el índice `{tenantId, orderNumber}` es único, así que dos TMP en el mismo ms colisionarían (improbable, sin manejo explícito).
- **`efficiency > 100`**: se registra audit log crítico (modelo desconfigurado o piezas mal contadas); el valor se almacena igual (no se clamp en línea, aunque sí en el trend horario de OEE con cap 115).
- **Consumo fallido en modo simple**: producción registrada sin descuento de stock; `consumedAmount = 0` para no inventar consumos; se avisa por consola. Esto puede descuadrar stock real vs sistema (requiere conciliación manual posterior).
- **`getLastActiveSessionStart` devuelve null** si hubo `pause`/`finish`/`stopped` posterior al último start: no se cobra coste de sesión ni OEE en ese caso.
- **`capacity <= 0`** (unitsPerHour = 0 o duración 0): efficiency = 0 en sesión; en eficiencia acumulada no se calcula si `realTime <= 0`.
- **Modo auditoría sin bobina al registrar**: error 400 explícito; la producción no avanza.
- **Guardia de kilos disparada**: bloquea la producción con mensaje que muestra teórico, real y margen (el operario debe registrar material).
- **Líneas legacy sin targetMaterialQty**: se repara en `recordProduction` a partir de `kgPorPieza` o del ratio de consumo real; también se actualiza `targetMaterialUnit`.
- **updateOrder con totalQuantity aumentado**: la línea `completed` vuelve a `stopped` (reabierta) conservando progreso; con total reducido por debajo de lo producido, `completed`.
- **updateOrder sin preservar `sessionStartTime`**: infla el OEE de la sesión activa (bug conocido y corregido con preservación explícita).
- **undoProduction de la última pieza**: la línea vuelve a `in_progress` SIEMPRE que haya cambios financieros, incluso si `producedQuantity` siguiera >= total (la línea no se re-marca completed; quirk aceptado).
- **Borrado de MaterialConsumo legacy sin IDs**: ventana de ±30 s por `createdAt` + coincidencia de campos; puede no acertar en logs muy antiguos (modo enterprise preferido).
- **Material sin `costPerUnit`**: `incrementalMaterialCost = 0`; la producción sigue.
- **Turno stale > 14 h**: auto-cierre en login con `totalHours` = tiempo real o 8.0; evita que sesiones perdidas distorsionen la disponibilidad del OEE hacia arriba.
- **Densidad por defecto**: 7850 kg/m3 (acero) si `Material.density` no está definido, tanto en BOM como en consumo.
- **Dimensiones del código de material**: el regex `(\d{2,4})[xX](\d{1,3}(?:[,.]\d+)?)` solo aplica con `ancho <= 2500` y `espesor <= 25`; si no casa, se usa el rate BOM estático.

## 6. Requisitos para el modelo relacional (PostgreSQL)

Convenciones: `BIGSERIAL`/`UUID` para PK; `tenant_id BIGINT NOT NULL REFERENCES tenants(id)` en todas las tablas raíz; `timestamptz` para fechas; dinero como `NUMERIC(12,2)`; cantidades como `NUMERIC(12,4)`; porcentajes como `NUMERIC(6,2)`; JSONB para `custom_fields`, `specifications`, `metadata`, `technical_specs`.

### 6.1 Tablas

**`manufacturing_models`**
- `id BIGSERIAL PK`, `tenant_id FK`, `code TEXT NOT NULL`, `name TEXT NOT NULL`, `description TEXT`, `material_code TEXT`, `default_quantity NUMERIC(12,4) NOT NULL DEFAULT 1`, `units_per_hour NUMERIC(12,4) NOT NULL DEFAULT 0 CHECK (units_per_hour >= 0)`, `production_unit TEXT NOT NULL DEFAULT 'units' CHECK (production_unit IN ('units','meters'))`, `technical_specs JSONB NOT NULL DEFAULT '{}'`, `predefined_lengths JSONB NOT NULL DEFAULT '[]'`, `quality_plan JSONB NOT NULL DEFAULT '[]'`, `is_active BOOLEAN NOT NULL DEFAULT true`, `created_at`, `updated_at`.
- Constraints: `UNIQUE (tenant_id, code)`; CHECK técnico: `technical_specs->>'pesoUnitario' >= 0` (validación app).
- Índices: `(tenant_id, workstation_ids)` con `workstation_ids TEXT[]` (columna array o tabla puente `manufacturing_model_workstations(model_id, workstation_id)`; recomendada la puente para FK/consulta limpia).

**`production_orders`**
- `id BIGSERIAL PK`, `tenant_id FK NOT NULL`, `order_number TEXT NOT NULL`, `client TEXT`, `priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low','medium','high','urgent'))`, `status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','completed','cancelled'))`, `has_ral BOOLEAN NOT NULL DEFAULT false`, `ral_code TEXT`, `custom_fields JSONB NOT NULL DEFAULT '{}'`, `specifications JSONB NOT NULL DEFAULT '[]'`, `estimated_total_cost NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (estimated_total_cost >= 0)`, `real_total_cost NUMERIC(12,2) NOT NULL DEFAULT 0`, `estimated_margin NUMERIC(12,2) NOT NULL DEFAULT 0`, `created_by BIGINT REFERENCES users(id)`, `is_deleted BOOLEAN NOT NULL DEFAULT false`, `created_at`, `updated_at`.
- Constraints: `UNIQUE (tenant_id, order_number)`; CHECK `real_total_cost >= 0` (los $inc negativos de undo no deben llevarlo bajo cero en un flujo correcto; decidir si CHECK estricto o tolerancia: legacy permitía negativos transitorios, recomendar CHECK >= 0 y gestionar en app).
- Índices: `(tenant_id, status, created_at DESC)`, `(tenant_id, is_deleted, created_at DESC)`.

**`order_lines`** (desnormalización del array embebido)
- `id BIGSERIAL PK`, `order_id BIGINT NOT NULL REFERENCES production_orders(id) ON DELETE CASCADE`, `sequence INT NOT NULL`, `workstation_id TEXT NOT NULL`, `workstation_name TEXT`, `material_code TEXT`, `metros NUMERIC(12,4) NOT NULL DEFAULT 0`, `total_quantity NUMERIC(12,4) NOT NULL CHECK (total_quantity >= 0)`, `produced_quantity NUMERIC(12,4) NOT NULL DEFAULT 0 CHECK (produced_quantity >= 0)`, `status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','in_progress','completed','stopped'))`, `visibility TEXT NOT NULL DEFAULT 'list' CHECK (visibility IN ('list','queue'))`, `custom_fields JSONB NOT NULL DEFAULT '{}'`, `specifications JSONB NOT NULL DEFAULT '[]'`, `estimated_cost NUMERIC(12,2) NOT NULL DEFAULT 0`, `real_cost NUMERIC(12,2) NOT NULL DEFAULT 0`, `estimated_time NUMERIC(12,4) NOT NULL DEFAULT 0` (minutos), `real_time NUMERIC(12,4) NOT NULL DEFAULT 0`, `target_material_cost NUMERIC(12,2) NOT NULL DEFAULT 0`, `target_material_qty NUMERIC(12,4) NOT NULL DEFAULT 0`, `target_material_unit TEXT NOT NULL DEFAULT 'uds'`, `real_material_cost NUMERIC(12,2) NOT NULL DEFAULT 0`, `real_material_qty NUMERIC(12,4) NOT NULL DEFAULT 0`, `scrap_material_qty NUMERIC(12,4) NOT NULL DEFAULT 0`, `efficiency NUMERIC(6,2)` (nullable, sin CHECK de tope: legacy permite > 100), `manufacturing_model_id BIGINT REFERENCES manufacturing_models(id)` (nullable), `session_start_time TIMESTAMPTZ` (nullable), `active_operator_id BIGINT REFERENCES users(id)` (nullable), `active_operator_first_name TEXT`, `active_operator_last_name TEXT`.
- Constraints: `UNIQUE (order_id, sequence)`; CHECK `produced_quantity <= total_quantity OR status = 'in_progress'` NO se puede imponer estrictamente (la edición de órdenes puede dejarlo temporalmente inconsistente; validar en app); CHECK `real_time >= 0`, `real_cost >= 0`.
- Índices: `(order_id)`, `(workstation_id, status)`, `(manufacturing_model_id)`, `(order_id, status)`.

**`production_logs`** (auditoría)
- `id BIGSERIAL PK`, `tenant_id FK`, `order_id BIGINT NOT NULL REFERENCES production_orders(id) ON DELETE CASCADE`, `line_id BIGINT NOT NULL REFERENCES order_lines(id) ON DELETE CASCADE`, `operator_id BIGINT NOT NULL REFERENCES users(id)`, `timestamp TIMESTAMPTZ NOT NULL DEFAULT now()`, `action TEXT NOT NULL CHECK (action IN ('start','pause','resume','finish','produce','scrap','setup_start','setup_finish','close_shift','undo_produce'))`, `quantity NUMERIC(12,4) NOT NULL DEFAULT 0`, `metadata JSONB NOT NULL DEFAULT '{}'`, `shift TEXT CHECK (shift IN ('morning','afternoon','night'))` (nullable, sin uso en legacy), `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
- **Inmutabilidad**: trigger `BEFORE UPDATE` que lanza excepción; `DELETE` solo permitido por el flujo de anulación (en PostgreSQL, implementar como función `undo_production()` con permisos restringidos en vez de DELETE genérico).
- Índices: `(tenant_id, timestamp DESC)`, `(order_id, timestamp)`, `(operator_id, timestamp DESC)`, `(order_id, line_id, action, timestamp)` (soporta `getLastActiveSessionStart`).

**`material_consumos`**
- `id BIGSERIAL PK`, `tenant_id FK`, `order_id BIGINT NOT NULL REFERENCES production_orders(id) ON DELETE CASCADE`, `workstation_id TEXT NOT NULL`, `material_id BIGINT NOT NULL REFERENCES materials(id)`, `stock_item_id BIGINT REFERENCES stock_items(id)` (nullable), `lote TEXT`, `consumed_quantity NUMERIC(12,4) NOT NULL CHECK (consumed_quantity >= 0)`, `unit TEXT NOT NULL DEFAULT 'm'`, `produced_quantity NUMERIC(12,4) NOT NULL`, `meters_per_piece NUMERIC(12,4)`, `kg_por_pieza NUMERIC(12,4) NOT NULL DEFAULT 0`, `calculation_method TEXT NOT NULL DEFAULT 'none' CHECK (calculation_method IN ('density_formula','model_override','meters_legacy','bom_static','manual','coil_end_scrap','manual_late_registration','none'))`, `cost_per_unit NUMERIC(12,4) NOT NULL DEFAULT 0`, `total_cost NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (total_cost >= 0)`, `tipo TEXT NOT NULL DEFAULT 'automatico' CHECK (tipo IN ('automatico','manual','ajuste','auto_audit','merma_puntas','salida_produccion'))`, `observaciones TEXT`, `operator_id BIGINT REFERENCES users(id)`, `date TIMESTAMPTZ NOT NULL DEFAULT now()`, `created_at`, `updated_at`.
- **Roll-up**: el hook post-save de Mongo se sustituye por lógica transaccional en la app (mismo `BEGIN/COMMIT` que la inserción) o trigger PostgreSQL que hace `UPDATE production_orders SET real_material_cost = real_material_cost + NEW.total_cost, real_total_cost = real_total_cost + NEW.total_cost WHERE id = NEW.order_id` solo cuando `tipo IN ('automatico','manual','ajuste')`. El trigger es preferible por atomicidad garantizada; debe duplicarse la lógica inversa en `BEFORE DELETE`.
- Índices: `(order_id)`, `(stock_item_id)`, `(tenant_id, date)`.

**`user_shifts`**
- `id BIGSERIAL PK`, `tenant_id FK`, `operator_id BIGINT NOT NULL REFERENCES users(id)`, `login_time TIMESTAMPTZ NOT NULL DEFAULT now()`, `logout_time TIMESTAMPTZ`, `total_hours NUMERIC(8,2) CHECK (total_hours IS NULL OR (total_hours > 0 AND total_hours <= 14))`, `status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed'))`, `global_efficiency NUMERIC(6,2)`, `metadata JSONB NOT NULL DEFAULT '{}'`, `created_at`, `updated_at`.
- Tabla puente: `user_shift_orders (shift_id BIGINT REFERENCES user_shifts(id) ON DELETE CASCADE, order_id BIGINT REFERENCES production_orders(id), PRIMARY KEY (shift_id, order_id))`.
- Constraints: un solo turno `active` por `(tenant_id, operator_id)` -> índice único parcial `CREATE UNIQUE INDEX uq_shift_active ON user_shifts (tenant_id, operator_id) WHERE status = 'active'`.
- Índices: `(tenant_id, login_time DESC)`, `(operator_id, status)`.

### 6.2 Reglas de integridad a nivel de BD

- `order_lines.total_quantity > 0` (la app nunca crea líneas con objetivo 0; CHECK recomendado).
- `production_logs` sin UPDATE (trigger) y sin DELETE público (solo vía función de anulación).
- `material_consumos.total_cost = round(consumed_quantity * cost_per_unit, 2)` garantizado por trigger `BEFORE INSERT OR UPDATE` (equivalente al `pre('save')`).
- FK `order_lines.manufacturing_model_id` sin `ON DELETE` restrictivo: el borrado de un modelo con líneas activas debe bloquearse (`ON DELETE RESTRICT`) para no romper eficiencias históricas.
- `production_orders` con RLS por `tenant_id` (según ADR-002).
- Transacciones: `recordProduction` debe ser UNA transacción (producción + consumos FIFO + costes + logs + desgaste herramienta); en legacy Mongo esto era atómico por documento pero los efectos secundarios (MaterialConsumo, StockItem, Tooling) no eran transaccionales; PostgreSQL permite hacerlo ACID completo.
- El `undoProduction` debe ser transacción única (stock + material_consumos + kardex + orden + logs).
