# Especificación del Dominio: INVENTARIO y BOBINAS (MES Metalúrgico Legacy)

Documento de contrato para la reconstrucción FastAPI + PostgreSQL con TDD.
Este documento captura la lógica de negocio EXACTA del sistema legacy (JavaScript, Express + Mongoose + MongoDB) para que ningún comportamiento se pierda en el portado.

---

## 1. Fuente legacy

Rutas y archivos consultados (todos dentro de `/root/kavanasystems/`):

| Archivo | Rol en el dominio |
|---|---|
| `backend/src/services/InventoryService.js` (810 líneas) | Servicio principal de inventario y bobinas. Todas las operaciones de stock, FIFO, vinculación de bobinas, retales, mermas y Kardex. |
| `backend/src/models/StockItem.js` | Modelo de lote/bobina (la unidad física de inventario). |
| `backend/src/models/Material.js` | Material maestro (catálogo): código, nombre, densidad, dimensiones, coste estándar, stock agregado. |
| `backend/src/models/MaterialConsumo.js` | Registro de consumo de material por orden (roll-up a la orden vía hooks). |
| `backend/src/models/MaterialTransaction.js` | Kardex: bitácora inmutable de movimientos de stock (entradas, salidas, traslados, mermas, ajustes). |
| `backend/src/controllers/MaterialController.js` | CRUD de materiales y alertas de stock bajo. |
| `backend/src/controllers/StockMovementController.js` | Recepción masiva ACID, borrado y edición de lotes. |
| `backend/src/routes/inventory.js` | Endpoints REST del módulo (contrato HTTP de entrada/salida). |
| `backend/src/services/OrderService.js` | Motor de auto-consumo por producción: cálculo de kg por pieza con fórmula de densidad, invocación del FIFO, guard de seguridad teórico vs real. |
| `backend/src/services/StockAlertService.js` | Alertas de stock mínimo. |
| `_KAVANA_SYSTEMS_DOCS/DECISIONES_ESTRATEGICAS.md` | Decisiones de negocio: Densidad Calibrada Kavana 7.7807 (Decisión 92), Burbuja de Vinculación (Decisión 90), No-Kill Policy, herencia FIFO, atomicidad con `$inc`. |

Regla de oro: NO se modificó nada del código legacy; solo lectura.

---

## 2. Entidades y relaciones

### 2.1 Material (catálogo maestro)

Material genérico (acero galvanizado, inox, aluminio...). Unidad base de stock: `kg` para bobinas, `uds` para componentes, también `m` y `litros`.

- `code`: código único por tenant (índice único `{tenantId, code}`).
- `name`: nombre legible.
- `stock.current`: stock total agregado (caché desnormalizada; se recalcula con `updateMaterialAggregates`).
- `stock.minimum`: umbral de stock mínimo para alertas.
- `costPerUnit`: coste unitario estándar en EUR (NO se sobrescribe automáticamente; es "Standard Cost").
- `dimensions.ancho` (mm) y `dimensions.espesor` (mm): dimensiones nominales de la banda (ej: "Galva 100x0.60").
- `density`: obligatorio, default 7850, rango [100, 30000] kg/m³. Referencias: Acero=7850, Aluminio=2700, Inox=7930, Cobre=8960. **La densidad calibrada de fábrica para bobinas de acero es 7.7807 (kg/dm³), ver Decisión 92.**
- `externalLinks`: enlaces externos opcionales.
- `isActive`: archivado lógico (el borrado físico está prohibido para preservar trazabilidad).

Reglas del controller:
- `createMaterial`: código único por tenant (400 si existe). `density` por defecto 7850 si no se envía.
- `updateMaterial`: si cambia el código, validar unicidad excluyendo el propio id.
- `deleteMaterial`: archivado lógico (`isActive: false`), nunca borrado físico.
- `getMaterials`: por defecto solo activos; `?includeArchived=true` muestra todos.
- Alertas (`StockAlertService.getMaterialAlerts`): materiales activos con `stock.current <= stock.minimum` (comparación de campos con `$expr`). Severidad: `critical` si current=0, `high` si current < minimum*0.5, si no `warning`. Devuelve `deficit` y `costImpact` (= deficit * costPerUnit).

### 2.2 StockItem (Lote / Bobina) - la entidad central

Cada documento = un lote físico de material. Para bobinas, es UNA bobina física (número de bobina en `coilId`).

- `tenantId` (ObjectId ref Tenant, requerido, indexado).
- `materialId` (ObjectId ref Material, requerido, indexado).
- `lote` (String, requerido, trim): código de lote (ej: `L-2024-001`, `PROV-X-99`). Se permiten duplicados de nombre de lote para el mismo material (un mismo lote puede llegar en varios palets); la distinción real es por `_id`.
- `coilId` (String, opcional, indexado): número de bobina. En bobinas virtuales es idéntico a `lote`.
- `cantidadInicial` (Number, requerido, min 0): lo que entró originalmente.
- `cantidadDisponible` (Number, requerido, SIN min: **puede ser negativo** por tolerancia de superávit / merma inversa).
- `unidad` (String, default `'uds'`): `m`, `kg`, `uds`, `litros`. **Se hereda del Material maestro al crear el lote, nunca del input.**
- `width` (Number, mm): validación de esquema. Rango físico industrial 10-2500 mm. Valores < 10 mm lanzan error ("físicamente imposible"); valores 1-9 mm solo advierten (parece estar en metros); 0/null/undefined pasan. Validación de negocio: los valores sospechosos en metros se advierten pero no se bloquean.
- `thickness` (Number, mm): validación de esquema. Rango 0.1-25 mm. Valores > 25 mm lanzan error; valores 0<v<0.1 advierten (parecen metros).
- `costePorUnidad` (Number, requerido, min 0): precio REAL de compra de este lote (clave del costeo FIFO).
- `costingMethod` (enum `['standard','real']`, default `'standard'`).
- `moneda` (String, default `'EUR'`).
- `fechaEntrada` (Date, default now, indexado): **clave de ordenamiento FIFO**.
- `fechaCaducidad` (Date, opcional).
- `ubicacion` (String, trim): ubicación física (ej: `Estantería A`, `corte-01`, `LÍNEA PRODUCCIÓN`, `Retales`).
- `estado` (enum `['activo','agotado','cuarentena','bloqueado','pico']`, default `'activo'`).
- `esPico` (Boolean, default false): true si es retal de bobina parcialmente consumida (menos del 10% del original).
- `notas`, `creadoPor` (ref User), `timestamps`.

Índices compuestos:
- `{tenantId, materialId, cantidadDisponible, fechaEntrada}`: soporta la query FIFO.
- `{tenantId, materialId, lote}`: búsqueda por lote.

**Estados y su semántica:**
- `activo`: stock consumible.
- `pico`: retal, queda <= 10% del original, consumible y elegible en FIFO.
- `agotado`: cantidadDisponible = 0 (o negativo). NO es elegible en consultas de consumo.
- `cuarentena`, `bloqueado`: definidos en el enum pero no usados por InventoryService (reservados).

**Elegibilidad para consumo: `estado in ['activo','pico']` y (según operación) `cantidadDisponible > 0`.**

### 2.3 MaterialTransaction (Kardex)

Bitácora inmutable de movimientos. Cada movimiento guarda snapshot del stock antes y después (auditoría).

- `tenantId`, `materialId`, `stockItemId` (ref StockItem, requerido): el lote afectado.
- `tipo` (enum `['entrada_compra','salida_produccion','ajuste_inventario','merma','devolucion','reservado','merma_puntas','traslado']`, requerido).
- `cantidad` (Number, requerido): cuánto se movió (valor absoluto; el tipo define el signo).
- `cantidadAnterior` (Number, requerido): snapshot del stock antes (auditoría).
- `cantidadNueva` (Number, requerido): snapshot del stock después.
- `ordenId` (ref Order, opcional), `lineaOrdenId` (String, opcional): contexto de producción.
- `motivo` (String), `documentoReferencia` (String).
- `realizadoPor` (ref User, requerido).
- Índice cronológico por material: `{tenantId, materialId, createdAt: -1}` (Kardex).

**Uso especial: el registro de vinculación de bobina.** El conjunto de transacciones con `tipo='salida_produccion'` que referencian `ordenId + lineaOrdenId` y motivo que casa con `/Bobina vinculada a la Línea/i` define la "burbuja de vinculación" (bobinas explícitamente vinculadas a la orden). Además, `findLotByCode`/`linkCoil`/`unlinkCoil` escriben `tipo='traslado'` con `cantidad: 0` y `cantidadAnterior === cantidadNueva` para registrar cambios de ubicación.

### 2.4 MaterialConsumo (Consumo por orden)

Registro de consumo de material asociado a una orden, con contexto de producción y coste (snapshot al momento del consumo).

- `tenantId`, `orderId` (ref Order, requerido), `workstationId` (String, requerido; ej: `'corte-01'`). Valor especial `'reconciliacion'` para mermas de fin de bobina.
- `materialId`, `stockItemId` (ref StockItem, opcional), `lote` (String): snapshot para trazabilidad.
- `consumedQuantity` (Number, requerido): cantidad REAL descontada del stock.
- `unit` (String, default `'m'`).
- `producedQuantity` (Number, requerido): piezas fabricadas con ese consumo.
- `metersPerPiece` (Number): medida de la pieza (si aplica).
- `kgPorPieza` (Number, default 0): kg consumidos por pieza (auto-calculado).
- `calculationMethod` (enum `['density_formula','model_override','meters_legacy','bom_static','manual','coil_end_scrap','manual_late_registration','none']`, default `'none'`).
- `costPerUnit` (Number, default 0), `totalCost` (Number, default 0): snapshot de costes.
- `tipo` (enum `['automatico','manual','ajuste','auto_audit','merma_puntas','salida_produccion']`, default `'automatico'`).
- `observaciones`, `operatorId`, `date`.

Hooks (patrón Master-Detail):
- `pre('save')`: `totalCost = round(consumedQuantity * costPerUnit * 100) / 100` (redondeo a 2 decimales).
- `post('save')` roll-up a la orden: SOLO si `totalCost > 0 && orderId && tipo in ['automatico','manual','ajuste']` → `Order.$inc { realMaterialCost: +totalCost, realTotalCost: +totalCost }`. **Los tipos `auto_audit` y `merma_puntas` NO hacen roll-up** porque en modo auditoría el cobro del material ya se hizo por adelantado en `linkCoil`.
- `post('findOneAndDelete')`: resta `totalCost` de la orden si el tipo está en `['automatico','manual','ajuste']`.

### 2.5 Order (contexto de cobro; NO es entidad de inventario pero se escribe desde aquí)

Campos de la línea de orden (`lines[]`) que el módulo de inventario modifica:

- `lines.$.realMaterialQty`: peso real de material cargado a la línea (kg).
- `lines.$.realMaterialCost`: coste real de material de la línea.
- `lines.$.realCost`: coste real total de la línea (material + mano de obra + máquina).
- `lines.$.scrapMaterialQty`: merma acumulada (kg) registrada en fin de bobina / cambio de bobina.
- `lines.$.customFields.activeCoilId` y `activeCoilCode`: bobina activa en la línea (modo auditoría).
- `lines.$.workstationId` / `workstationName`: puesto de trabajo de la línea (usado para ubicar la bobina y filtrar el FIFO por puesto).
- `realTotalCost` (nivel orden): total de costes reales.

### 2.6 Diagrama de relaciones

```
Material 1 ────< StockItem (lote/bobina) >──── 1 MaterialTransaction (Kardex)
   │                    │      │
   │                    │      └─── 1..* MaterialConsumo (consumos por orden)
   │                    │
   │            (ubicacion = workstation)
   │                    │
   └── stock.current (agregado desnormalizado)
Order 1 ────< OrderLine (customFields.activeCoilId -> StockItem._id)
```

- Un Material tiene muchos StockItem (lotes).
- Un StockItem tiene muchas MaterialTransaction (Kardex cronológico).
- Un StockItem tiene muchos MaterialConsumo (uso histórico por orden, ver endpoint `/stock/:id/usage`).
- Un StockItem puede estar vinculado a una línea de orden vía `Order.lines.customFields.activeCoilId`.
- El `lote` y el `coilId` de un StockItem pueden ser idénticos (bobinas virtuales); el `coilId` es el identificador que escanea el operario.

---

## 3. Operaciones clave

Todas las funciones de `InventoryService` reciben `tenantId` (aislamiento multi-tenant obligatorio en TODAS las queries) y `userId` (autoría). A menos que se indique, cada `save()` es atómico individual pero NO hay transacción global entre pasos (riesgo conocido a documentar en el portado).

### 3.1 `addStock(tenantId, userId, { materialId, lote, coilId, cantidad, costePorUnidad, ubicacion, notas, width, thickness })`

Registra una ENTRADA de material (nuevo lote). Devuelve el `StockItem` creado.

Comportamiento exacto:
1. `material = Material.findById(materialId)`; `unit = material?.unit || 'uds'`. Si el material no existe, la unidad cae a `'uds'` (no lanza error; el `materialId` referencial no se valida).
2. Crea `StockItem`:
   - `cantidadInicial = cantidad`, `cantidadDisponible = cantidad` (al entrar está entero).
   - `unidad = unit` (HEREDADA DEL MATERIAL, nunca del input).
   - `coilId = coilId || null`, `width = width || null`, `thickness = thickness || null`.
   - `estado = 'activo'`, `creadoPor = userId`.
3. `save()`.
4. `logTransaction` con `tipo: 'entrada_compra'`, `cantidadAnterior: 0`, `cantidadNueva: cantidad`, `motivo: 'Entrada Inicial'`, `documentoReferencia: notas`. Invariante: el Kardex por lote empieza en 0.
5. `updateMaterialAggregates(tenantId, materialId)` (recalcula `stock.current`).
6. Devuelve `newStockItem`.

Variante de recepción masiva (`StockMovementController.receiveStock`, con transacción ACID de Mongo):
- Recibe `{ items[], provider, invoice, date, costingMode, invoiceTotal }`.
- Si `costingMode === 'real' && invoiceTotal > 0`: calcula `realCostPerUnit = invoiceTotal / suma(qty de todos los items)` y lo aplica a TODOS los lotes (costeo real por factura). Error 400 si el peso total es <= 0.
- Si no, cada lote usa `Number(item.cost) || material.costPerUnit || 0` (costeo estándar).
- Crea cada StockItem con `lote: item.batch || 'BATCH-' + Date.now()`, `coilId: item.coilId || item.numeroBobina`, `ubicacion: item.location || 'Recepción'`, `notas` con proveedor/factura, `fechaEntrada: date || now`, `estado: 'activo'`.
- `Material.$inc { 'stock.current': qty }` por item (incremento atómico, no recálculo).
- Si cualquier item falla, ROLLBACK completo de la transacción (todo o nada).
- **Importante**: esta ruta NO genera MaterialTransaction (no hay Kardex para recepciones masivas), a diferencia de `addStock`. Discrepancia conocida del legacy.

Otras rutas de mantenimiento (`StockMovementController`):
- `deleteStockItem(id)`: borra físicamente el StockItem y hace `Material.$inc { 'stock.current': -cantidadInicial }`. Sin protección de lotes consumidos (comentario del código reconoce la debilidad).
- `updateStockItem(id, { cantidad, lote, ubicacion, notas })`: recalcula `cantidadDisponible += (nuevaInicial - viejaInicial)` y ajusta `stock.current` con `$inc` si hay diff.

### 3.2 `consumeStockFIFO(tenantId, userId, { materialId, cantidadRequerida, ordenId, orderId, lineaOrdenId, motivo, workstationId, priorityStockItemId })`

Consume stock con estrategia FIFO (First In, First Out) por `fechaEntrada` ASC. Devuelve el coste real total de la operación y los lotes utilizados. Es EL motor central del módulo.

**Parámetros:**
- `materialId`: material a consumir.
- `cantidadRequerida`: kg/unidades a consumir.
- `ordenId` / `orderId`: alias intercambiables; `validOrderId = ordenId || orderId`.
- `lineaOrdenId`: línea de la orden.
- `motivo`: texto para el Kardex.
- `workstationId`: puesto de trabajo (activa el filtro de ubicación o la burbuja de auditoría).
- `priorityStockItemId`: bobina activa (prioritaria). Su presencia junto con `workstationId`, `validOrderId` y `lineaOrdenId` activa el MODO AUDITORÍA.

**Fase 0 - Construcción de la query base:**
```
{ tenantId, materialId, cantidadDisponible: { $gt: 0 }, estado: { $in: ['activo','pico'] } }
```

**Fase 1 - MODO AUDITORÍA (Burbuja de Vinculación):** se activa solo si `priorityStockItemId && workstationId && validOrderId && lineaOrdenId`. Todo dentro de try/catch: si algo falla, se loguea warning y se CONTINÚA sin restricción (la burbuja se desactiva silenciosamente):
1. **JIT Move**: busca la bobina prioritaria (`StockItem.findOne({ _id: priorityStockItemId, tenantId })`). Si `ubicacion !== workstationId`, la reubica en el puesto (`ubicacion = workstationId; save()`) SIN transacción de traslado (solo console.log).
2. **Extraer bobinas vinculadas**: busca en `MaterialTransaction`:
   ```
   { tenantId, ordenId: validOrderId,
     $or: [ { lineaOrdenId: lineaOrdenId }, { lineaOrdenId: /^<lineaOrdenId>$/i } ],  // tolerancia a variaciones de string
     tipo: 'salida_produccion' }
   ```
   Toma los `stockItemId` únicos.
3. **Garantizar la bobina actual en la lista**: si `priorityStockItemId` no está entre las vinculadas, se añade. (La bobina activa SIEMPRE es elegible, aunque el vínculo no se haya registrado.)
4. `query._id = { $in: vinculadasIds }`: **solo las bobinas vinculadas explícitamente a esta orden (o la prioritaria) son elegibles para consumo**. Esto aísla la orden de bobinas fantasma de turnos anteriores (Decisión 90: "Burbuja de Vinculación").

**Fase 1b - Filtro por puesto (modo no auditoría):** si solo hay `workstationId`:
```
query.$or = [
  { ubicacion: workstationId },
  { ubicacion: /^<workstationId sin espacios con \s*>$/i },
  { ubicacion: workstationId sin espacios en mayúsculas }
]
```
Busca material ubicado físicamente en el puesto, tolerando variaciones de formato (espacios, mayúsculas).

**Fase 2 - FIFO estricto:**
- `lotes = StockItem.find(query).sort({ fechaEntrada: 1 })`.
- **NO se modifica el orden ni se eliminan bobinas del array** (bug fix de herencia: el `splice` anterior eliminaba la bobina prioritaria sin reinsertarla y rompía la herencia entre múltiples bobinas vinculadas en la misma sesión; ver Decisión "Integridad de Cascada FIFO (Inheritance Fix)"). La cascada natural consume la bobina más antigua primero y salta a la siguiente cuando se agota.
- Si `lotes.length === 0` → `throw new Error('No hay stock disponible para este material' + (priorityStockItemId ? ' (bobina vinculada no encontrada o agotada)' : ''))`.

**Fase 3 - Verificación de stock total (atomicidad optimista):**
- `totalDisponible = sum(cantidadDisponible de todos los lotes)`.
- Si `totalDisponible < cantidadRequerida`:
  - Con `priorityStockItemId` → `allowedToGoNegative = true` (TOLERANCIA DE SUPERÁVIT: la bobina real rinde más de lo teórico; se permite dejar el stock en negativo). Solo warning.
  - Sin `priorityStockItemId` → `throw new Error('Stock FIFO insuficiente. Disponible: X.XX, Requerido: Y.YY')`.

**Fase 4 - Cascada de consumo (por cada lote, en orden FIFO):**
```
si cantidadPendiente <= 0 → break
cantidadA_Tomar = min(lote.cantidadDisponible, cantidadPendiente)
si (allowedToGoNegative && lote._id es la bobina prioritaria) → cantidadA_Tomar = cantidadPendiente  // puede dejar negativo
costeLote = cantidadA_Tomar * lote.costePorUnidad
costeTotalOperacion += costeLote
stockAnterior = lote.cantidadDisponible
stockNuevo = lote.cantidadDisponible - cantidadA_Tomar
lote.cantidadDisponible = stockNuevo
si stockNuevo === 0 → lote.estado = 'agotado'
lote.save()
logTransaction(tipo 'salida_produccion', cantidad: cantidadA_Tomar, cantidadAnterior: stockAnterior,
              cantidadNueva: stockNuevo, ordenId, lineaOrdenId, motivo: motivo || `Consumo FIFO (Parte de ${cantidadRequerida})`)
lotesAfectados.push({ stockItemId, lote: lote.lote, cantidad: cantidadA_Tomar, costeUnitario: lote.costePorUnidad, costeTotal: costeLote })
cantidadPendiente -= cantidadA_Tomar
```

**Fase 5 - Cierre:**
- `updateMaterialAggregates(tenantId, materialId)`.
- Retorna `{ success: true, costeRealTotal: costeTotalOperacion, cantidadConsumida: cantidadRequerida, lotesUtilizados: lotesAfectados }`. Nota: `cantidadConsumida` reporta lo requerido, no lo realmente tomado (si se agotó el stock, difiere; el detalle real está en `lotesUtilizados`).

**Invariantes:**
- FIFO estricto por `fechaEntrada` ASC.
- Costeo por el `costePorUnidad` REAL del lote (no del material maestro).
- Solo estados `activo`/`pico` con stock > 0 son elegibles.
- En modo auditoría, SOLO las bobinas de la burbuja + la prioritaria son elegibles (la burbuja se calcula por transacciones de tipo `salida_produccion` existentes).
- El saldo negativo solo se permite en la bobina prioritaria y solo cuando el stock total no alcanza.
- Sin transacción global: cada `lote.save()` es atómico individual; un fallo a mitad de cascada deja lotes parcialmente consumidos y transacciones ya registradas (a documentar en v2).

### 3.3 `consumeFromSpecificLot(tenantId, userId, { stockItemId, cantidadRequerida, orderId, lineId, motivo })`

Consume de un LOTE ESPECÍFICO (Modo Auditoría, el operario escanea la bobina exacta).

1. `lote = StockItem.findOne({ _id: stockItemId, tenantId, estado: { $in: ['activo','pico'] } })`. Si no existe → `throw new Error('Lote no encontrado o inactivo')`.
2. `stockAnterior = cantidadDisponible`; `stockNuevo = cantidadDisponible - cantidadRequerida` (**permitiendo saldo negativo**); `costeLote = cantidadRequerida * costePorUnidad`.
3. `lote.cantidadDisponible = stockNuevo`.
4. Transición de estado:
   - Si `stockNuevo <= 0` → `estado = 'agotado'`, `esPico = false`.
   - Si no, si `stockNuevo <= (cantidadInicial * 0.10)` → `estado = 'pico'`, `esPico = true` (queda menos del 10% del original → retal/pico).
   - (Si queda más del 10%, el estado NO cambia.)
5. `lote.save()`.
6. `logTransaction(tipo 'salida_produccion', cantidad: cantidadRequerida, cantidadAnterior, cantidadNueva, ordenId: orderId, lineaOrdenId: lineId, motivo: motivo || 'Consumo manual de lote ' + lote.lote)`.
7. `updateMaterialAggregates`.
8. Retorna `{ success, lote: lote.lote, stockItemId, cantidadConsumida: cantidadRequerida, cantidadRestante: stockNuevo, esPico: lote.esPico, costeTotal: Math.round(costeLote*100)/100, costeUnitario: lote.costePorUnidad }`.

**Invariantes:** regla del 10% para marcar pico/retal; admite saldo negativo; la cantidad restante puede ser negativa en la respuesta.

### 3.4 `createVirtualCoil(tenantId, userId, { materialId, customWidth, customThickness, provider, originalId, initialWeight, ubicacion })`

Crea una "Bobina Virtual" a partir de un registro manual del operario (paperless). Delega en `addStock`.

1. `material = Material.findById(materialId)`; si no existe → `throw new Error('Material base no encontrado')`.
2. Genera IDs legibles para el operario:
   - `timestampCode = new Date().toISOString().replace(/[-:T]/g, '').slice(2, 14)` → formato `YYMMDDHHMMSS`.
   - `generatedLote = originalId ? originalId.trim().toUpperCase() : 'M-' + timestampCode`.
   - `generatedCoilId = generatedLote` (consistencia lote=coilId para búsqueda rápida por scanner).
3. `notasFormato = 'Bobina Manual' + (' | Prov: ' + provider si existe) + (' | Ancho: ' + customWidth + 'mm' si existe) + (' | Espesor: ' + customThickness + 'mm' si existe)`.
4. Llama a `addStock` con: `lote: generatedLote`, `coilId: generatedCoilId`, `cantidad: initialWeight`, `width: customWidth`, `thickness: customThickness`, `costePorUnidad: material.costPerUnit || 0` (usa el coste MAESTRO, no un coste de compra), `ubicacion: ubicacion || 'LÍNEA PRODUCCIÓN'` (se asume que está en uso), `notas: notasFormato`.
5. Devuelve el StockItem de `addStock` (incluye entrada Kardex + recálculo de agregados).

Validación en ruta: `materialId` e `initialWeight > 0` obligatorios (400).

### 3.5 `findLotByCode(tenantId, code, newLocation = null)`

Busca un lote por código (para el scanner del operario). Devuelve el StockItem poblado con `materialId` (campos `code name unit costPerUnit dimensions`).

1. **Prioridad ALTA**: `StockItem.findOne({ tenantId, coilId: code, estado: { $in: ['activo','pico'] } })`.
2. **Fallback**: si no hay resultado por coilId, busca por código de lote (traspaso de lote genérico): `StockItem.find({ tenantId, lote: { $regex: /^<code>$/i }, estado: { $in: ['activo','pico'] } }).sort({ fechaEntrada: 1 })` y toma el PRIMERO (el más antiguo).
3. **Auto-ubicación (JIT Move)**: si hay lote y `newLocation` es string:
   - `trimmedLocation = newLocation.trim()`; si no está vacío y `lote.ubicacion !== trimmedLocation`:
     - `lote.ubicacion = trimmedLocation; await lote.save()`.
     - `logTransaction(tenantId, null, { tipo: 'traslado', cantidad: 0, cantidadAnterior: cantidadDisponible, cantidadNueva: cantidadDisponible, motivo: 'Ubicada en X (Escaneada para producción)' })` **con `.catch()`** (el log de traslado es best-effort; si falla no bloquea; nótese que `realizadoPor: null` viola el `required` del modelo y el error se traga el catch, ver casos límite).
4. Devuelve `lote` (o null).

El endpoint `GET /lot/:code?workstation=...` devuelve 404 con `'Lote "X" no encontrado o sin stock'` si es null, y emite por sockets `stockUpdated { type: 'location_change' }` si hubo cambio de ubicación.

### 3.6 `linkCoil(tenantId, userId, { stockItemId, orderId, lineId })`

VINCULA una bobina a una orden. **Cobra el peso TOTAL de la bobina a la orden POR ADELANTADO (modelo BULK ENTRY)**. El stock físico NO se descuenta de la bobina (sigue "viva" en la máquina).

1. `coil = StockItem.findOne({ _id: stockItemId, tenantId, estado: { $in: ['activo','pico'] } })`. Si no → `throw new Error('Bobina no encontrada o inactiva')`.
2. Busca la orden (`Order.findOne({ _id: orderId, tenantId })`) y su línea (`line = orderDoc.lines.find(l => l._id.toString() === lineId.toString())`); `workstation = line.workstationName || line.workstationId`.
3. **Reubicación**: si `workstation && coil.ubicacion !== workstation` → `coil.ubicacion = workstation` + `logTransaction(tipo 'traslado', cantidad 0, motivo 'Ubicada en X (Vinculada a orden Y)')` con `.catch()` (best-effort).
4. **Check de idempotencia**: busca `MaterialTransaction.findOne({ tenantId, stockItemId: coil._id, ordenId, lineaOrdenId: lineId, tipo: 'salida_produccion', motivo: { $regex: /Bobina vinculada a la Línea/i } })`. Si existe → retorna `{ success: true, coilWeight: coil.cantidadDisponible, msg: 'Bobina ya estaba vinculada.' }` SIN volver a cobrar.
5. `coilWeight = coil.cantidadDisponible`; `coilCost = coilWeight * coil.costePorUnidad`.
6. Normaliza `lineId` a ObjectId si es string válido (para que el match de Mongoose funcione).
7. **Cobro por adelantado** (`Order.findOneAndUpdate` con `{ _id: orderId, tenantId, 'lines._id': safeLineId }`):
   ```
   $inc: {
     'lines.$.realMaterialQty': coilWeight,
     'lines.$.realMaterialCost': coilCost,   // KPIService lo necesita para varianza y scrapRate
     'lines.$.realCost': coilCost,
     'realTotalCost': coilCost
   }
   $set: {
     'lines.$.customFields.activeCoilId': coil._id,
     'lines.$.customFields.activeCoilCode': coil.coilId || coil.lote
   }
   ```
8. Si el update no encuentra la línea → `throw new Error('No se pudo vincular la bobina: línea no encontrada. <diagnóstico con IDs reales de la BD>')`.
9. `logTransaction(tipo 'salida_produccion' /* salida virtual: el material está en la línea */, cantidad: coilWeight, cantidadAnterior: coilWeight, cantidadNueva: coilWeight /* emula que el stock sigue vivo en la bobina física hasta que produzca piezas */, motivo: 'Bobina vinculada a la Línea. Carga total de Entrada: X.XXkg')`.
10. `coil.updatedAt = new Date(); await coil.save()` (refresca updatedAt para priorizar la bobina como la última activa en el puesto).
11. Retorna `{ success: true, coilWeight, order: updatedOrder }`.

**Invariantes clave:**
- Idempotente por (stockItemId, ordenId, lineaOrdenId, motivo patrón).
- Cobro BULK: la orden paga TODA la bobina al vincular; los consumos FIFO posteriores NO vuelven a sumar coste a la orden en modo auditoría (solo descuentan el stock del lote).
- El `realMaterialQty` de la línea se usa como "kilos reales vinculados" en el guard de seguridad de OrderService.
- La transacción de vinculación es la que crea la "burbuja" que hace elegible a la bobina en `consumeStockFIFO` (más la inyección directa de la prioritaria).

### 3.7 `switchCoil(tenantId, userId, { oldCoilId, orderId, lineId })`

Finaliza la bobina actual al cambiar a otra. **En el modelo BULK ENTRY la orden ya pagó por esta bobina entera**, así que el stock restante no consumido vía FIFO se registra como MERMA INDUSTRIAL explícita (reconciliación ISO 9001).

1. `coil = StockItem.findOne({ _id: oldCoilId, tenantId })`. Si no → `throw new Error('Bobina anterior no encontrada')`. (Nota: NO filtra por estado, acepta cualquier estado.)
2. `remainingStock = coil.cantidadDisponible`; `mermaCost = remainingStock * coil.costePorUnidad`.
3. **Matar el stock**: `cantidadDisponible = 0; estado = 'agotado'; esPico = false; save()`.
4. **Registrar la merma explícita** SOLO si `remainingStock > 0.01` (tolerancia de 10g para redondeos): crea `MaterialConsumo` con:
   - `workstationId: 'reconciliacion'` (partida especial), `consumedQuantity: remainingStock`, `unit: coil.unidad || 'kg'`, `producedQuantity: 0`, `kgPorPieza: 0`, `calculationMethod: 'coil_end_scrap'`, `costPerUnit: coil.costePorUnidad`, `totalCost: mermaCost`, `operatorId: userId`, `tipo: 'merma_puntas'`, `observaciones: 'Cambio de Bobina: <lote>. Sobrante abandonado: X.Xkg (Y.YY€). Registrado como merma industrial.'`.
5. **Trazabilidad**: `logTransaction(tipo 'merma_puntas', cantidad: remainingStock, cantidadAnterior: remainingStock, cantidadNueva: 0, motivo: 'Cambio de Bobina. Sobrante: X.XXkg registrado como merma industrial.')`.
6. `updateMaterialAggregates(tenantId, coil.materialId)`.
7. **Actualizar la orden** (`Order.findOneAndUpdate({ _id: orderId, tenantId, 'lines._id': lineId })`):
   - `$set: { 'lines.$.customFields.activeCoilId': null, 'lines.$.customFields.activeCoilCode': null }`.
   - Si `remainingStock > 0.01`: `$inc: { 'lines.$.scrapMaterialQty': +remainingStock, 'lines.$.realMaterialQty': -remainingStock, 'lines.$.realCost': -mermaCost, 'realTotalCost': -mermaCost }`. (Se quita de la línea lo no consumido y se mueve a scrap.)
   - NOTA: este update NO usa `{ new: true }`; después hace `Order.findById(orderId)` para devolver el documento.
8. Retorna `{ success: true, msg, mermaKg: remainingStock, mermaCost: parseFloat(mermaCost.toFixed(2)), coil, order }`.

**Invariantes:** el sobrante se contabiliza como merma (scrap), NO vuelve a inventario; la bobina queda agotada; la línea queda sin bobina activa.

**Relación con la No-Kill Policy (frontend)**: desde 2026-05-18 el frontend (MaterialScanner.jsx) NO llama a `switchCoil` automáticamente al escanear múltiples bobinas (las bobinas escaneadas se acumulan como activas en la estación). `switchCoil` queda reservado al botón explícito "Fin de Bobina" / chatarra real, mientras la reconciliación real de sobrantes la hace `createRetal`. La cascada FIFO con burbuja es la que drena el stock en modo auditoría.

### 3.8 `unlinkCoil(tenantId, userId, { coilId, orderId, lineId })`

DESVINCULA una bobina de una orden SIN crear merma (**Arrastre de Bobina / carry over**). Reembolsa a la orden el peso no consumido (según el consumo teórico FIFO). **La bobina se mantiene en el puesto de trabajo actual, activa y lista para la siguiente orden.**

1. `coil = StockItem.findOne({ _id: coilId, tenantId })`. Si no → `throw new Error('Bobina no encontrada')`.
2. Reubica en el puesto de la línea (igual que `linkCoil`): si `workstation && coil.ubicacion !== workstation` → `coil.ubicacion = workstation` + `logTransaction(tipo 'traslado', cantidad 0, motivo 'Ubicada en X (Desvinculada/Arrastrada por cierre de orden)')` con `.catch()`.
3. `systemRemaining = coil.cantidadDisponible` (lo que el FIFO del sistema ha calculado que queda).
4. `costeReembolso = systemRemaining * coil.costePorUnidad`.
5. **Trazabilidad**: `logTransaction(tipo 'salida_produccion' /* registro neutro */, cantidad: systemRemaining, cantidadAnterior: systemRemaining, cantidadNueva: systemRemaining, motivo: 'Arrastre de Bobina (Unlink). Orden cerrada. Peso remanente teórico: X.XXkg se mantiene en máquina.')`.
6. `coil.updatedAt = new Date(); await coil.save()` (prioridad como última activa en el puesto).
7. **Actualizar la orden** (`Order.findOneAndUpdate({ _id: orderId, tenantId, 'lines._id': lineId }, ..., { new: true })`):
   - `$inc: { 'lines.$.realMaterialQty': -systemRemaining, 'lines.$.realCost': -costeReembolso, 'realTotalCost': -costeReembolso }` (reembolso del peso teórico remanente para que la orden no lo pague).
   - `$set: { 'lines.$.customFields.activeCoilId': null, 'lines.$.customFields.activeCoilCode': null }`.
8. Retorna `{ success: true, msg: 'Bobina desvinculada. X.Xkg transferidos al puesto de trabajo.', coil, order: updatedOrder }`.

**Invariantes:**
- NO toca `scrapMaterialQty` (no hay merma), NO crea MaterialConsumo, NO cambia el estado de la bobina (sigue `activo`/`pico` en el puesto).
- El reembolso es por el peso TEÓRICO del sistema, no por medición física (esa es la diferencia con `createRetal`).
- Diferencias con `switchCoil`: unlink = carry over sin merma; switch = agotar con merma.

### 3.9 `createRetal(tenantId, userId, { coilId, remainingWeight, orderId, lineId })`

Genera un "Retal" (Fin de Bobina) al final de la jornada o producción. **Devuelve a inventario el peso sobrante real y detecta la "merma invisible"** (reconciliación ISO 9001): diferencia entre lo que el sistema cree que queda (FIFO) y lo que el operario mide físicamente.

1. `coil = StockItem.findOne({ _id: coilId, tenantId })`. Si no → `throw new Error('Bobina no encontrada')`.
2. `systemRemaining = coil.cantidadDisponible` (lo que el FIFO del sistema cree que queda); `realRemaining = Math.max(0, remainingWeight)` (lo que el operario mide físicamente; se clamp a >= 0).
3. **Reconciliación de merma industrial**:
   - `hiddenMerma = Math.max(0, systemRemaining - realRemaining)` (captura irregularidades de espesor, puntas inservibles, pérdidas de proceso).
   - `mermaCost = hiddenMerma * coil.costePorUnidad`.
4. Si `hiddenMerma > 0.01` (tolerancia de 10g para redondeos): crea `MaterialConsumo` con `workstationId: 'reconciliacion'`, `consumedQuantity: hiddenMerma`, `producedQuantity: 0`, `kgPorPieza: 0`, `calculationMethod: 'coil_end_scrap'`, `costPerUnit: coil.costePorUnidad`, `totalCost: mermaCost`, `tipo: 'merma_puntas'`, `observaciones: 'Merma de Fin de Bobina: <lote>. Sistema: X.Xkg → Real: Y.Ykg. Diferencia: Z.Zkg (W.WW€)'`.
5. **Actualizar la bobina física**:
   - `coil.cantidadDisponible = realRemaining`.
   - `coil.esPico = realRemaining > 0`.
   - `coil.ubicacion = realRemaining > 0 ? 'Retales' : coil.ubicacion` (el retal se mueve a la ubicación especial 'Retales').
   - Si `realRemaining <= 0` → `estado = 'agotado'; esPico = false`.
   - `save()`.
6. `costeReembolso = realRemaining * coil.costePorUnidad`.
7. **Trazabilidad**: `logTransaction(tipo 'ajuste_inventario', cantidad: realRemaining, cantidadAnterior: systemRemaining, cantidadNueva: realRemaining, motivo: 'Fin de Bobina (Retal). Devuelto: X.XXkg. Merma detectada: Y.YYkg (Z.ZZ€).')`.
8. `updateMaterialAggregates(tenantId, coil.materialId)`.
9. **Actualizar la orden** (`Order.findOneAndUpdate({ _id: orderId, tenantId, 'lines._id': lineId }, ..., { new: true })`):
   - `$inc: { 'lines.$.realMaterialQty': -realRemaining, 'lines.$.realCost': -costeReembolso, 'realTotalCost': -costeReembolso }` (reembolsar el peso devuelto al inventario).
   - Si `hiddenMerma > 0.01`: `$inc` adicional `'lines.$.scrapMaterialQty': hiddenMerma` (la merma se suma al scrap de la línea).
   - `$set: { 'lines.$.customFields.activeCoilId': null, 'lines.$.customFields.activeCoilCode': null }`.
10. Retorna `{ success: true, msg (distingue retal devuelto vs bobina agotada), mermaKg: hiddenMerma, mermaCost: parseFloat(mermaCost.toFixed(2)), coil, order: updatedOrder }`.

**Invariantes:**
- El sobrante REAL vuelve a inventario (ubicación 'Retales', estado `activo` o `pico` si > 0); la diferencia sistema-vs-real se registra como merma.
- El `remainingWeight` del operario manda sobre el cálculo teórico (es un ajuste de inventario con autoridad física).
- Tolerancia de redondeo: merma solo si > 0.01 (10g).

### 3.10 `logTransaction(tenantId, userId, data)` (helper)

`return await MaterialTransaction.create({ tenantId, realizadoPor: userId, ...data })`.

- `data` contiene `materialId`, `stockItemId`, `tipo`, `cantidad`, `cantidadAnterior`, `cantidadNueva`, y opcionalmente `ordenId`, `lineaOrdenId`, `motivo`, `documentoReferencia`.
- El modelo exige `realizadoPor` (required). En `findLotByCode` se invoca con `userId = null` y `.catch()`: la creación falla por validación y el error se traga (el traslado se guarda igualmente porque el `save()` de la bobina ya se hizo antes). Caso límite conocido.
- En `linkCoil`/`unlinkCoil` el log de traslado también va con `.catch()`: la operación principal no debe fallar por un problema de logging.

### 3.11 `updateMaterialAggregates(tenantId, materialId)` (helper)

Recalcula los totales en el Material maestro. **Es el ÚNICO escritor de `stock.current` en el flujo normal.**

1. Aggregation Pipeline sobre StockItem:
   ```
   $match: { tenantId, materialId, estado: { $in: ['activo','pico'] } }
   $group: {
     _id: '$materialId',
     totalStock: { $sum: '$cantidadDisponible' },
     valorTotalStock: { $sum: { $multiply: ['$cantidadDisponible', '$costePorUnidad'] } }
   }
   ```
2. `totalStock = result[0]?.totalStock || 0`; `valorTotal = result[0]?.valorTotalStock || 0`; `precioMedio = totalStock > 0 ? valorTotal / totalStock : 0`.
3. `Material.updateOne({ _id: materialId }, { $set: { 'stock.current': totalStock } })`.
4. **DECISIÓN EXPLÍCITA: NO sobrescribe `costPerUnit`** con el precio medio ponderado (el código lo comenta y lo deja desactivado): `costPerUnit` del material es "Standard Cost" manual. El `precioMedio` se calcula pero se descarta.
5. Nota: `stock.minimum` nunca se toca aquí.

**Advertencia de consistencia:** `receiveStock`, `deleteStockItem` y `updateStockItem` actualizan `stock.current` con `$inc` directo, mientras que `addStock`/consumos/mermas usan `updateMaterialAggregates` (recalculo). Ambos mecanismos conviven en el legacy; el portado debería unificarlos (idealmente: `stock.current` como columna calculada o recalculada en la misma transacción).

### 3.12 Motor de auto-consumo de producción (OrderService, integración crítica)

Cuando se registra producción (`incrementalQuantity` piezas) en una línea, el sistema calcula el consumo de material y llama al FIFO. Reglas EXACTAS:

**A. Cálculo de kg por pieza (prioridades, en orden):**
1. **model_override**: si `manufacturingModel.technicalSpecs.pesoUnitario > 0` → `kgPorPieza = pesoUnitario`.
2. **density_formula**: si `kgPorPieza === 0` y hay ancho y espesor:
   - Dimensiones **Lote-First** (Decisión 92): `activeWidth = activeLot?.width || line.customFields?.ancho || order.customFields?.ancho || material.dimensions?.ancho`; `activeThickness` análogo. El ancho/espesor REAL grabado en el lote tiene prioridad sobre el catálogo.
   - `realMeters = manufacturingModel?.realUnitConsumptionMeters` (incluye scrapGap); si no, `fallbackLargoMm / 1000` (de customFields o technicalSpecs.largo).
   - `kgPorPieza = largo_m * (ancho_mm / 1000) * (espesor_mm / 1000) * densidad` con `densidad = material.density || 7850`.
   - `calculationMethod = 'density_formula'`.
   - **Factor de Densidad Calibrada Kavana = 7.7807 (kg/dm³)**: según la Decisión 92 (2026-04-09), la constante calibrada que compensa el factor de bobinado y el recubrimiento, logrando coincidencia con las básculas físicas de planta y eliminando inventario fantasma. La fórmula documentada es `largo x ancho x espesor x 7.7807`. El código actual del legacy usa `material.density || 7850` como densidad; el valor calibrado 7.7807 (kg/dm³, densidad efectiva del acero en bobina, menor que los 7.85 del acero macizo por el aire entre capas) debe ser la constante canónica del portado para bobinas de acero, aplicada con la misma fórmula geométrica.
3. **meters_legacy**: si `kgPorPieza === 0`, usa metros por pieza (`realUnitConsumptionMeters` o `line.metros` o `customFields.largo/1000`): `consumedAmount = incrementalQuantity * metersPerPiece`, unidad `'m'`.
4. **bom_static**: último recurso, `rate = line.targetMaterialQty / (line.totalQuantity || 1)`; `consumedAmount = incrementalQuantity * rate`, unidad `targetMaterialUnit`.

Si `kgPorPieza > 0` → `consumedAmount = parseFloat((incrementalQuantity * kgPorPieza).toFixed(4))`, unidad `'kg'`.

**B. Financiero:** `incrementalMaterialCost = parseFloat((consumedAmount * material.costPerUnit).toFixed(2))` (usa el coste del MAESTRO para el cálculo financiero del modo simple; el coste real del LOTE se usa en el MaterialConsumo por lote).

**C. Deducción de stock según modo de tracking** (`tenantConfig.plan.features.materialTrackingMode`):
- `'simple'`: `consumeStockFIFO` SIN `workstationId` ni `priorityStockItemId` (FIFO global del material).
- `'audit'`: `consumeStockFIFO` CON `workstationId: line.workstationId` y `priorityStockItemId: activeCoilId` (burbuja de vinculación + filtro de puesto). Si falla → THROW (bloquea la producción: `'Error en deducción de material (Modo Auditoría): ...'`).
- Por cada lote en `lotesUtilizados` crea un `MaterialConsumo` (trazabilidad real por bobina): `workstationId: line.workstationId`, `consumedQuantity: detail.cantidad`, `unit: consumptionUnit`, `producedQuantity: incrementalQuantity`, `kgPorPieza`, `calculationMethod`, `metersPerPiece: line.metros || 0`, `costPerUnit: detail.costeUnitario` (del LOTE), `totalCost: detail.costeTotal` (del LOTE), `tipo: trackingMode === 'audit' ? 'auto_audit' : 'automatico'`.
- Modo simple si falla el consumo: **NO bloquea la producción**; resetea `consumedAmount = 0`, `incrementalMaterialCost = 0`, `kgPorPieza = 0`, `calculationMethod = 'none'` y registra la producción SIN descuento de stock (fix anti "consumos fantasma"; la producción se registra igual, con warning).

**D. Guard de seguridad v2 (SECURITY GUARD, solo modo auditoría con bobina activa):**
- Si `activeCoilId && incrementalQuantity > 0`:
  - `kgPerUnit = (line.targetMaterialQty || theoreticalTotal) / (line.totalQuantity || 1)`.
  - `newTotalTheoretical = (line.producedQuantity + incrementalQuantity) * kgPerUnit`.
  - `realLimit = line.realMaterialQty` (kilos reales vinculados, cargados por linkCoil).
  - `tolerance = Math.max(realLimit * 0.15, 150)` (tolerancia proporcional: 15% del material vinculado o mínimo 150kg; cubre la tolerancia comercial negativa de espesor, donde el material rinde más metros por kg; la tolerancia fija de 0.1kg anterior causaba falsos positivos con múltiples bobinas).
  - Si `newTotalTheoretical > realLimit + tolerance` → `throw new Error('BLOQUEO DE SEGURIDAD: Los kilos teóricos acumulados (X.Xkg) superarían a los kilos reales vinculados (Y.Ykg) con margen de Z.Zkg. ¿Olvidó registrar material?')`.

**E. Actualización de la línea de orden:**
- Con bobina activa (auditoría): `$inc { 'lines.$.realCost': incrementalLaborCost, 'realTotalCost': incrementalLaborCost }`. **NO suma `realMaterialQty`** (ya se cargó el peso total en linkCoil).
- Sin bobina activa (simple): `$inc { 'lines.$.realCost': incrementalMaterialCost + incrementalLaborCost, 'realTotalCost': incrementalLaborCost, 'lines.$.realMaterialQty': consumedAmount }`. El roll-up de `realMaterialCost` y `realTotalCost` lo hace el hook post-save de MaterialConsumo.
- Si `targetMaterialQty` falta o es 0 y hay `kgPorPieza > 0`: fija `targetMaterialQty = totalRequired * kgPorPieza` (redondeado a 4 decimales) y `targetMaterialUnit = 'kg'`.

---

## 4. Reglas de negocio críticas (no perder en el portado)

1. **Aislamiento multi-tenant**: TODA query de stock, transacción, lote, consumo y material filtra por `tenantId`. Sin excepción.
2. **Burbuja de Vinculación (Decisión 90)**: en modo auditoría, SOLO las bobinas vinculadas explícitamente a la orden (transacciones `salida_produccion` con ese `ordenId`+`lineaOrdenId`) son elegibles para consumo, más la bobina prioritaria (siempre inyectada). Esto elimina las "bobinas fantasma" de turnos anteriores olvidadas en el puesto. La burbuja se calcula con tolerancia de string en `lineaOrdenId` (match exacto o regex case-insensitive).
3. **FIFO estricto por `fechaEntrada` ASC** con herencia entre múltiples bobinas: la cascada recorre TODOS los lotes elegibles en orden cronológico sin sacar bobinas del array (Inheritance Fix). Cuando una bobina se agota, se salta a la siguiente. Prohibido reordenar o hacer splice de la bobina prioritaria.
4. **Cobro BULK por adelantado (linkCoil)**: la orden paga el peso TOTAL de la bobina al vincularla. Los consumos FIFO posteriores solo descuentan stock del lote, NO vuelven a cobrar a la orden en modo auditoría (por eso `auto_audit` no hace roll-up).
5. **Stock vivo hasta el fin de bobina**: en `linkCoil` la transacción registra `cantidadAnterior === cantidadNueva` (el stock no se descuenta); el material "vive" en la bobina física hasta `createRetal` o `switchCoil`.
6. **Reconciliación de merma (ISO 9001)**: `createRetal` calcula `hiddenMerma = max(0, systemRemaining - realRemaining)` y la registra como `MaterialConsumo` con `tipo: 'merma_puntas'`, `calculationMethod: 'coil_end_scrap'`, `workstationId: 'reconciliacion'`. `switchCoil` registra TODO el sobrante como merma. La medición física del operario manda sobre el cálculo teórico.
7. **Actualización atómica de stock**: las escrituras sobre la orden usan `$inc` (nunca `$set` de totales) para evitar condiciones de carrera con ráfagas de registros (Decisión del 2026-04-09: "Atomicidad de Registro ($inc)"). Los lotes se guardan con `save()` tras calcular el nuevo saldo.
8. **Costeo FIFO por coste real del lote**: cada consumo usa `costePorUnidad` del StockItem (precio real de compra del lote), no el coste estándar del material. El `costPerUnit` del material es solo Standard Cost (nunca se sobrescribe automáticamente con el precio medio).
9. **Tolerancia de superávit**: si el stock total no alcanza la cantidad requerida, en modo auditoría se permite dejar la bobina prioritaria en saldo NEGATIVO (el material real rinde más que el teórico); en modo simple se lanza error. `cantidadDisponible` puede ser negativa (el esquema no la limita a >= 0).
10. **Regla del 10% (pico/retal)**: si tras un consumo queda <= 10% de la cantidad inicial, el lote pasa a `estado: 'pico'` y `esPico: true`. Al agotarse (<= 0) pasa a `'agotado'`. Solo `activo` y `pico` son consumibles.
11. **Elegibilidad por estado y stock**: las queries de consumo exigen `estado in ['activo','pico']` y `cantidadDisponible > 0` (excepto el consumo de lote específico, que admite negativo).
12. **JIT Move / auto-ubicación**: al escanear una bobina (findLotByCode con workstation) o al vincular/desvincular, la bobina se reubica automáticamente en el puesto de trabajo de la línea, con transacción de traslado best-effort (`.catch()`, no bloqueante).
13. **Arrastre de bobina (carry over)**: `unlinkCoil` mantiene la bobina activa en el puesto para la siguiente orden, reembolsando a la orden el peso teórico remanente SIN merma ni cambio de estado. Diferente de `switchCoil` (agota + merma) y de `createRetal` (devuelve peso real + merma invisible).
14. **Idempotencia de linkCoil**: no se puede cobrar dos veces la misma bobina a la misma línea; el check se hace por transacción previa con motivo `/Bobina vinculada a la Línea/i`.
15. **Guard de seguridad teórico vs real**: el peso teórico acumulado no puede superar los kilos reales vinculados + `max(15% del real, 150kg)`; si lo supera, se bloquea la producción en modo auditoría.
16. **Roll-up Master-Detail**: los MaterialConsumo de tipo `automatico`/`manual`/`ajuste` actualizan `realMaterialCost` y `realTotalCost` de la orden (hook post-save y post-delete). `merma_puntas` y `auto_audit` quedan excluidos (cobro ya realizado por linkCoil).
17. **Modo simple tolerante vs modo auditoría estricto**: en modo simple, si falla la deducción de stock, la producción se registra igual SIN descuento (nunca consumos fantasmas con coste); en modo auditoría, el fallo de deducción BLOQUEA la producción.
18. **Unidad heredada del material**: el StockItem toma su `unidad` del Material maestro (`material.unit || 'uds'`), nunca del input de recepción.
19. **Densidad Calibrada Kavana 7.7807**: la constante calibrada de densidad efectiva de la bobina de acero (kg/dm³) usada en el motor geométrico `largo x ancho x espesor x densidad` (Decisión 92). Compensa el factor de bobinado y recubrimiento; su uso eliminó toneladas de inventario fantasma al coincidir con las básculas físicas. En el código legacy la fórmula usa `material.density || 7850`; el portado debe soportar la constante calibrada 7.7807 como densidad efectiva por defecto de bobinas de acero (ver sección 3.12).
20. **Archivado lógico**: los materiales nunca se borran físicamente (`isActive: false`); se preserva la trazabilidad histórica de órdenes.

---

## 5. Casos límite conocidos (errores que el v2 ya resuelve o debe resolver)

1. **Bobinas fantasma (Decisión 90)**: el FIFO global consumía bobinas de turnos anteriores olvidadas en el puesto, distorsionando el stock. Solución legacy: burbuja de vinculación (solo bobinas vinculadas a la orden actual + prioritaria). El v2 debe implementar el aislamiento por orden de forma estructural (FK a orden/línea con estado vinculado).
2. **Regresión de herencia FIFO (Inheritance Fix, 2026-04-08)**: un `splice` eliminaba la bobina prioritaria del array de procesamiento sin reinsertarla, rompiendo la herencia de material entre múltiples bobinas vinculadas en la misma sesión. El v2 debe garantizar que la cascada recorra todas las bobinas elegibles sin mutar la colección.
3. **Peso no numérico**: en `POST /coils/retal` el `remainingWeight` se convierte con `Number()`; si llega un string no numérico, `Math.max(0, NaN)` propaga `NaN` a `cantidadDisponible` y contamina el stock. El v2 debe validar numérico finito >= 0 en la capa de entrada (Pydantic).
4. **Lote no encontrado**: errores distintos según operación: `consumeFromSpecificLot` → `'Lote no encontrado o inactivo'`; `linkCoil` → `'Bobina no encontrada o inactiva'`; `switchCoil`/`unlinkCoil`/`createRetal` → `'Bobina ... no encontrada'` (estos tres NO filtran por estado activo); `findLotByCode` → null → 404 del controller. El v2 debe tipificar estos errores (404 vs 409 vs 422).
5. **Bobina en puesto de trabajo anterior**: sin el filtro de puesto/burbuja, el FIFO consumía material de otra máquina. El legacy lo resuelve con el `$or` de ubicación (3 variantes: exacta, regex sin espacios case-insensitive, normalizada en mayúsculas) y el JIT Move al escanear. El v2 debe normalizar la ubicación del puesto de forma determinista (FK a workstation o columna normalizada única).
6. **Consumos fantasmas en modo simple**: si la deducción de stock falla, el legacy registra la producción sin descuento y con `calculationMethod: 'none'` (fix explícito). El v2 debe decidir si replica esta tolerancia o exige consistencia transaccional (recomendado: transacción ACID que falle junto con la producción, o registro de excepción explícito).
7. **`logTransaction` con `userId = null`**: en `findLotByCode` el traslado se loguea con `realizadoPor: null`, violando el `required` del modelo; el `.catch()` traga el error y el traslado queda SIN Kardex. El v2 debe usar un usuario de sistema (ej: `system`) para movimientos automáticos.
8. **Kardex inexistente en recepción masiva**: `receiveStock` no genera MaterialTransaction (solo `addStock` lo hace). Inconsistencia de auditoría conocida. El v2 debe generar Kardex en todas las entradas.
9. **`stock.current` desincronizado**: coexisten dos mecanismos de escritura (`$inc` directo en recepción/borrado/edición vs recálculo por agregación en el flujo normal). El v2 debe unificar: `stock.current` como derivado transaccional o recalculado siempre en la misma transacción.
10. **`cantidadConsumida` reportada vs real**: `consumeStockFIFO` devuelve `cantidadConsumida: cantidadRequerida` aunque el stock se agote antes; el detalle verdadero está en `lotesUtilizados`. El v2 debe devolver la cantidad realmente consumida (o validar stock total antes).
11. **Tolerancia de redondeo de 10g**: mermas de `<= 0.01` kg se ignoran (`remainingStock > 0.01`, `hiddenMerma > 0.01`) para no ensuciar con ruido de redondeo. El v2 debe replicar el umbral como constante configurable.
12. **`esPico` vs `estado` duplicados**: el legacy mantiene dos flags paralelos (`estado='pico'` y `esPico=true`) con riesgo de divergencia (ej: `consumeFromSpecificLot` fija ambos, `switchCoil` fija `estado='agotado'` y `esPico=false`). El v2 debe derivar uno del otro (constraint CHECK) o eliminar la redundancia.
13. **Línea no encontrada en linkCoil**: el legacy lanza error con diagnóstico de IDs; el v2 debe validar la pertenencia (orderId, lineId) ANTES de cobrar, con FK compuesta.
14. **Bobina vinculada agotada**: si la bobina prioritaria está agotada, el FIFO lanza `'No hay stock disponible... (bobina vinculada no encontrada o agotada)'`. El v2 debe distinguir entre lote inexistente y lote sin stock.
15. **Actualizaciones sin transacción**: `consumeStockFIFO` hace saves individuales sin transacción global; un fallo intermedio deja lotes parciales. El v2 (PostgreSQL) debe envolver la cascada en una transacción ACID con `SELECT ... FOR UPDATE` de los lotes afectados.

---

## 6. Requisitos para el modelo relacional (PostgreSQL)

Esquema sugerido para la reconstrucción FastAPI + SQLAlchemy + PostgreSQL. Tipos y constraints mapeados 1:1 del legacy, con las mejoras estructurales que el v2 debe aportar.

### 6.1 Tabla `materials` (Material maestro)

| Campo | Tipo | Constraints |
|---|---|---|
| `id` | BIGSERIAL / UUID | PK |
| `tenant_id` | UUID | NOT NULL, FK `tenants.id` |
| `code` | VARCHAR(100) | NOT NULL |
| `name` | VARCHAR(255) | NOT NULL |
| `stock_current` | NUMERIC(14,4) | NOT NULL DEFAULT 0 (derivada, ver 6.7) |
| `stock_minimum` | NUMERIC(14,4) | NOT NULL DEFAULT 0 |
| `cost_per_unit` | NUMERIC(14,6) | NOT NULL DEFAULT 0 (Standard Cost, nunca sobrescrita automáticamente) |
| `dimension_ancho_mm` | NUMERIC(10,3) | NULL (mm) |
| `dimension_espesor_mm` | NUMERIC(10,3) | NULL (mm) |
| `density` | NUMERIC(12,4) | NOT NULL DEFAULT 7850, CHECK (density BETWEEN 100 AND 30000) (kg/m³) |
| `density_calibrada` | NUMERIC(12,4) | NULL DEFAULT 7.7807 (kg/dm³, Densidad Calibrada Kavana, Decisión 92) |
| `unit` | VARCHAR(10) | NOT NULL DEFAULT 'kg', CHECK (unit IN ('kg','uds','m','litros')) |
| `external_links` | JSONB | NULL |
| `is_active` | BOOLEAN | NOT NULL DEFAULT true (archivado lógico; prohibido DELETE físico) |
| `created_at`, `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() |

Constraints:
- `UNIQUE (tenant_id, code)`.
- Índice: `(tenant_id, is_active)`.
- Trigger de alerta (o vista): alerta cuando `stock_current <= stock_minimum`, severidad por reglas de 3.1 (`critical` si 0, `high` si < 50% del mínimo, si no `warning`).

### 6.2 Tabla `stock_items` (Lote / Bobina)

| Campo | Tipo | Constraints |
|---|---|---|
| `id` | BIGSERIAL / UUID | PK |
| `tenant_id` | UUID | NOT NULL, FK `tenants.id` |
| `material_id` | BIGINT / UUID | NOT NULL, FK `materials.id` |
| `lote` | VARCHAR(100) | NOT NULL (permite duplicados por política; la identidad es `id`) |
| `coil_id` | VARCHAR(100) | NULL (número de bobina escaneable; en virtuales = lote) |
| `cantidad_inicial` | NUMERIC(14,4) | NOT NULL, CHECK (cantidad_inicial >= 0) |
| `cantidad_disponible` | NUMERIC(14,4) | NOT NULL (SIN CHECK >= 0: puede ser negativa por tolerancia de superávit) |
| `unit` | VARCHAR(10) | NOT NULL DEFAULT 'uds', CHECK (unit IN ('kg','uds','m','litros')) (heredada del material al crear) |
| `width_mm` | NUMERIC(10,3) | NULL, CHECK (width_mm IS NULL OR width_mm = 0 OR width_mm BETWEEN 10 AND 2500) (rango industrial; 1-9 solo warning en legacy) |
| `thickness_mm` | NUMERIC(10,3) | NULL, CHECK (thickness_mm IS NULL OR thickness_mm = 0 OR thickness_mm BETWEEN 0.1 AND 25) |
| `coste_por_unidad` | NUMERIC(14,6) | NOT NULL, CHECK (coste_por_unidad >= 0) (precio REAL de compra del lote) |
| `costing_method` | VARCHAR(10) | NOT NULL DEFAULT 'standard', CHECK (costing_method IN ('standard','real')) |
| `moneda` | VARCHAR(3) | NOT NULL DEFAULT 'EUR' |
| `fecha_entrada` | TIMESTAMPTZ | NOT NULL DEFAULT now() (CLAVE FIFO) |
| `fecha_caducidad` | TIMESTAMPTZ | NULL |
| `ubicacion` | VARCHAR(255) | NULL (texto libre; idealmente FK `workstations.name` normalizada) |
| `estado` | VARCHAR(12) | NOT NULL DEFAULT 'activo', CHECK (estado IN ('activo','agotado','cuarentena','bloqueado','pico')) |
| `es_pico` | BOOLEAN | NOT NULL DEFAULT false (derivable: estado='pico'; mantener con CHECK de consistencia si se conserva) |
| `notas` | TEXT | NULL |
| `creado_por` | BIGINT / UUID | NULL, FK `users.id` |
| `created_at`, `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() |

Constraints e índices:
- Índice FIFO: `(tenant_id, material_id, cantidad_disponible, fecha_entrada)`.
- Índice burbuja/escaneo: `(tenant_id, coil_id)` y `(tenant_id, material_id, lote)`.
- Índice por puesto: `(tenant_id, ubicacion)` (normalizar mayúsculas/sin espacios para el match legacy).
- CHECK de consistencia pico: `(estado = 'pico') = es_pico` o derivar `es_pico` por vista.

### 6.3 Tabla `material_transactions` (Kardex, inmutable)

| Campo | Tipo | Constraints |
|---|---|---|
| `id` | BIGSERIAL / UUID | PK |
| `tenant_id` | UUID | NOT NULL, FK `tenants.id` |
| `material_id` | BIGINT / UUID | NOT NULL, FK `materials.id` |
| `stock_item_id` | BIGINT / UUID | NOT NULL, FK `stock_items.id` |
| `tipo` | VARCHAR(20) | NOT NULL, CHECK (tipo IN ('entrada_compra','salida_produccion','ajuste_inventario','merma','devolucion','reservado','merma_puntas','traslado')) |
| `cantidad` | NUMERIC(14,4) | NOT NULL |
| `cantidad_anterior` | NUMERIC(14,4) | NOT NULL (snapshot auditoría) |
| `cantidad_nueva` | NUMERIC(14,4) | NOT NULL (snapshot auditoría) |
| `orden_id` | BIGINT / UUID | NULL, FK `orders.id` |
| `linea_orden_id` | VARCHAR(64) | NULL (texto en legacy; en v2 FK a `order_lines.id` con normalización) |
| `motivo` | TEXT | NULL |
| `documento_referencia` | VARCHAR(255) | NULL |
| `realizado_por` | BIGINT / UUID | NOT NULL, FK `users.id` (usuario 'system' para movimientos automáticos) |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() |

Índices: `(tenant_id, material_id, created_at DESC)` (Kardex); `(tenant_id, orden_id, linea_orden_id, tipo)` (burbuja de vinculación). Inmutabilidad: sin UPDATE/DELETE (grant restrictivo o trigger de bloqueo).

### 6.4 Tabla `material_consumos` (Consumo por orden)

| Campo | Tipo | Constraints |
|---|---|---|
| `id` | BIGSERIAL / UUID | PK |
| `tenant_id` | UUID | NOT NULL, FK `tenants.id` |
| `order_id` | BIGINT / UUID | NOT NULL, FK `orders.id` |
| `order_line_id` | BIGINT / UUID | NULL, FK `order_lines.id` (v2: reemplaza `lineaOrdenId` string) |
| `workstation_id` | VARCHAR(100) | NOT NULL (valor especial 'reconciliacion' para mermas) |
| `material_id` | BIGINT / UUID | NOT NULL, FK `materials.id` |
| `stock_item_id` | BIGINT / UUID | NULL, FK `stock_items.id` |
| `lote` | VARCHAR(100) | NULL (snapshot trazabilidad) |
| `consumed_quantity` | NUMERIC(14,4) | NOT NULL |
| `unit` | VARCHAR(10) | NOT NULL DEFAULT 'm' |
| `produced_quantity` | NUMERIC(14,4) | NOT NULL |
| `meters_per_piece` | NUMERIC(14,4) | NULL |
| `kg_por_pieza` | NUMERIC(14,6) | NOT NULL DEFAULT 0 |
| `calculation_method` | VARCHAR(30) | NOT NULL DEFAULT 'none', CHECK (calculation_method IN ('density_formula','model_override','meters_legacy','bom_static','manual','coil_end_scrap','manual_late_registration','none')) |
| `cost_per_unit` | NUMERIC(14,6) | NOT NULL DEFAULT 0 |
| `total_cost` | NUMERIC(14,4) | NOT NULL DEFAULT 0 (calculado: round(consumed_quantity * cost_per_unit, 2)) |
| `tipo` | VARCHAR(20) | NOT NULL DEFAULT 'automatico', CHECK (tipo IN ('automatico','manual','ajuste','auto_audit','merma_puntas','salida_produccion')) |
| `observaciones` | TEXT | NULL |
| `operator_id` | BIGINT / UUID | NULL, FK `users.id` |
| `date` | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| `created_at`, `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() |

Reglas:
- `total_cost` por CHECK/computed o trigger: `total_cost = ROUND(consumed_quantity * cost_per_unit, 2)`.
- Roll-up a la orden: trigger AFTER INSERT/DELETE que hace `UPDATE orders SET real_material_cost = real_material_cost ± total_cost, real_total_cost = real_total_cost ± total_cost` SOLO si `tipo IN ('automatico','manual','ajuste')` (replica los hooks del legacy; `auto_audit` y `merma_puntas` excluidos).
- Índice: `(tenant_id, stock_item_id, date DESC)` (historial de uso de bobina); `(order_id)`.

### 6.5 Tabla `order_lines` (extensiones de inventario en la línea de orden)

Campos adicionales sobre la línea de orden existente:

| Campo | Tipo | Constraints |
|---|---|---|
| `id` | BIGINT / UUID | PK, FK `orders.id` (order_id) |
| `workstation_id` | VARCHAR(100) | NULL (nombre del puesto; fuente de JIT Move) |
| `real_material_qty` | NUMERIC(14,4) | NOT NULL DEFAULT 0 (kg cargados vía linkCoil) |
| `real_material_cost` | NUMERIC(14,4) | NOT NULL DEFAULT 0 |
| `real_cost` | NUMERIC(14,4) | NOT NULL DEFAULT 0 |
| `scrap_material_qty` | NUMERIC(14,4) | NOT NULL DEFAULT 0 (merma acumulada por fin de bobina) |
| `active_coil_id` | BIGINT / UUID | NULL, FK `stock_items.id` (bobina activa; SET NULL al agotar/desvincular) |
| `active_coil_code` | VARCHAR(100) | NULL (coilId o lote) |
| `target_material_qty` | NUMERIC(14,4) | NULL (teórico; se auto-rellena con kg_por_pieza si falta) |
| `target_material_unit` | VARCHAR(10) | NULL |
| `total_quantity` | NUMERIC(14,4) | NOT NULL (para el guard de seguridad: kgPerUnit = target/total) |
| `produced_quantity` | NUMERIC(14,4) | NOT NULL DEFAULT 0 |

Guard de seguridad en v2: trigger o validación de aplicación que bloquea `produced_quantity + incremental > (real_material_qty + MAX(real_material_qty*0.15, 150)) / kgPerUnit` cuando hay bobina activa.

### 6.6 Tabla `coil_links` (vinculación bobina-orden, mejora estructural v2)

El legacy deriva la burbuja de vinculación escaneando MaterialTransaction; el v2 debe modelarla explícitamente:

| Campo | Tipo | Constraints |
|---|---|---|
| `id` | BIGSERIAL / UUID | PK |
| `tenant_id` | UUID | NOT NULL, FK `tenants.id` |
| `stock_item_id` | BIGINT / UUID | NOT NULL, FK `stock_items.id` |
| `order_id` | BIGINT / UUID | NOT NULL, FK `orders.id` |
| `order_line_id` | BIGINT / UUID | NOT NULL, FK `order_lines.id` |
| `estado` | VARCHAR(12) | NOT NULL DEFAULT 'vinculada', CHECK (estado IN ('vinculada','consumida','retal','merma','desvinculada')) |
| `created_at`, `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() |

Constraints: `UNIQUE (tenant_id, stock_item_id, order_id, order_line_id)` (idempotencia de linkCoil). La burbuja de `consumeStockFIFO` = `SELECT stock_item_id FROM coil_links WHERE order_id = X AND order_line_id = Y AND estado IN ('vinculada','consumida')` + bobina prioritaria.

### 6.7 Resumen de reglas transaccionales para el portado (TDD)

1. `addStock`: INSERT stock_items + INSERT material_transactions (entrada_compra) + UPDATE materials.stock_current en UNA transacción.
2. `consumeStockFIFO`: `BEGIN; SELECT ... FOR UPDATE` de los lotes elegibles (burbuja + FIFO + estados); validar stock total; iterar cascada; UPDATE por lote; INSERT Kardex por lote; UPDATE material.stock_current; `COMMIT`. Lanzar `409` si stock insuficiente en modo simple; permitir negativo solo en bobina prioritaria (modo auditoría).
3. `consumeFromSpecificLot`: misma transacción, con la regla del 10% (pico) y transición a agotado.
4. `linkCoil`: INSERT coil_links (único) + UPDATE order_line (bulk charge con `real_material_qty += coilWeight`...) + INSERT Kardex + UPDATE stock_items.updated_at, todo atómico; si el unique constraint salta → respuesta idempotente "ya estaba vinculada".
5. `switchCoil`: UPDATE bobina a agotado + INSERT material_consumos (merma_puntas, si > 0.01) + UPDATE order_line (scrap += restante, real_material_qty -= restante, real_cost -= merma) + INSERT Kardex.
6. `createRetal`: UPDATE bobina (realRemaining, ubicacion 'Retales', estado pico/agotado) + INSERT material_consumos (merma invisible si > 0.01) + UPDATE order_line (reembolso + scrap) + INSERT Kardex (ajuste_inventario).
7. `unlinkCoil`: UPDATE order_line (reembolso teórico) + UPDATE coil_links estado 'desvinculada' + UPDATE bobina.ubicacion + INSERT Kardex; SIN tocar scrap.
8. Todas las operaciones de escritura: CHECK constraint de que `estado IN ('activo','pico')` es requisito de elegibilidad; `cantidad_disponible` sin límite inferior; `total_cost` calculado.
9. Test obligatorio (contrato TDD): la cascada FIFO con múltiples bobinas vinculadas respeta `fecha_entrada` ASC, hereda entre bobinas sin mutar el conjunto, deja negativo solo en la prioritaria, y calcula `costeRealTotal` como suma de `cantidad_tomada * coste_por_unidad` del lote.

---

## Apéndice: Endpoints REST del módulo (contrato HTTP legacy)

| Método | Ruta | Función |
|---|---|---|
| POST | `/api/inventory/receive` | Recepción masiva ACID (`receiveStock`) |
| GET | `/api/inventory/recent` | Últimas 100 recepciones |
| POST | `/api/inventory/receipt` | Entrada de material (`addStock`); obligatorios: materialId, lote, cantidad, costePorUnidad |
| GET | `/api/inventory/stock/:materialId` | Lotes activos/pico de un material, orden FIFO |
| GET | `/api/inventory/stock/:materialId/all` | Historial completo de lotes (incluye agotados) |
| GET | `/api/inventory/stock/:id/usage` | Historial de MaterialConsumo de una bobina (populado con operario, orden, modelo) |
| GET | `/api/inventory/stock-by-code/:materialCode` | Stock FIFO por código de material (picos primero: `sort({ esPico: -1, fechaEntrada: 1 })`) |
| GET | `/api/inventory/stock-by-workstation/:workstationName` | Stock activo en un puesto (regex case-insensitive) |
| GET | `/api/inventory/lot/:code?workstation=` | `findLotByCode` + auto-ubicación + socket `stockUpdated` |
| POST | `/api/inventory/virtual-coil` | `createVirtualCoil` (materialId + initialWeight > 0 obligatorios) |
| POST | `/api/inventory/consume-lot` | `consumeFromSpecificLot` (stockItemId + cantidad > 0 obligatorios) |
| POST | `/api/inventory/coils/link` | `linkCoil` (stockItemId, orderId, lineId obligatorios) + socket `order_updated` |
| POST | `/api/inventory/coils/switch` | `switchCoil` (oldCoilId, orderId, lineId obligatorios) + socket |
| POST | `/api/inventory/coils/unlink` | `unlinkCoil` (coilId, orderId, lineId obligatorios) + socket |
| POST | `/api/inventory/coils/retal` | `createRetal` (coilId + remainingWeight obligatorios) + socket |
| DELETE | `/api/inventory/stock/:id` | Borrado físico de lote + `$inc` negativo en stock.current |
| PUT | `/api/inventory/stock/:id` | Edición de lote (cantidad/lote/ubicacion/notas) |
| GET | `/api/materials` (MaterialController) | Listar materiales (activos por defecto) |
| POST | `/api/materials` | Crear material (código único por tenant) |
| PUT | `/api/materials/:id` | Actualizar material (validar unicidad de código si cambia) |
| DELETE | `/api/materials/:id` | Archivado lógico (`isActive: false`) |
| GET | `/api/materials/alerts` | Alertas de stock bajo (`StockAlertService`) |
