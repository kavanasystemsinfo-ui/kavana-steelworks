# Spec 03 - OEE, costes y KPIs

Dominio: MES/MOM metalúrgico KAVANA. Contrato de comportamiento extraído del
backend legacy v2 (Express + Mongoose + MongoDB) para la reconstrucción
FastAPI + PostgreSQL con TDD. Complementa a la spec 02 (órdenes de producción),
de la que depende para los cálculos de coste real y eficiencia.

## 1. Fuente legacy

| Archivo | Rol |
|---|---|
| `/root/kavanasystems/backend/src/services/OEEService.js` (296 líneas) | Cálculo de OEE por rango (today/week/month), tendencia horaria, caché local en archivo. |
| `/root/kavanasystems/backend/src/controllers/LeanMetricsController.js` (294 líneas) | Métricas Lean agregadas (Takt Time, SMED, OEE mensual, MTBF, MTTR, turnos, stock). Comentado como fuente única de verdad unificada con OEEService (AUDIT FIX 2.1+2.4). |
| `/root/kavanasystems/backend/src/services/KPIService.js` (191 líneas) | KPIs financieros agregados con pipeline de agregación MongoDB y caché en memoria. |
| `/root/kavanasystems/backend/src/services/OrderCostCalculator.js` (144 líneas) | Calculador de costes de órdenes. **HUÉRFANO**: no es referenciado por ningún otro archivo runtime (solo por sí mismo). |
| `/root/kavanasystems/backend/src/services/CalculationEngine.js` (238 líneas) | Evaluación segura de fórmulas de campos calculados (mathjs). **HUÉRFANO**: no es referenciado por ningún otro archivo runtime. |
| `/root/kavanasystems/backend/src/services/ValidationService.js` (100 líneas) | Aliasing de campos, cálculo de metros/kg y costes de línea (usado por OrderCostCalculator y por OrderService para `findValueByAlias`). |
| `/root/kavanasystems/backend/src/services/OrderService.js` | Rutas REALES de coste y eficiencia en vivo (sesión, acumulada, live OEE), ver spec 02. |
| Modelos: `Order.js`, `ProductionLog.js`, `UserShift.js`, `Incidencia.js`, `MaterialConsumo.js`, `Material.js`, `StockItem.js`, `Tooling.js` | Fuentes de datos de todos los cálculos. |

Nota de arquitectura: `OrderCostCalculator` y `CalculationEngine` existen en el
legacy pero no están cableados al runtime. Sus fórmulas se documentan aquí como
contrato (son las que el v3 podría adoptar), pero el comportamiento observado en
producción es el de `OrderService.calculateOrderLines` + `OrderService` (spec 02)
y de los dos agregadores (`OEEService`/`LeanMetricsController`/`KPIService`).

## 2. Entidades y relaciones

### 2.1 Resultado de OEE (`OEEService.calculateOEE`)

```
{
  availability: Number,   // % (0-100, clamp)
  performance: Number,    // % (0-100, clamp)
  quality: Number,        // % (0-100, clamp)
  oee: Number,            // % (0-100, clamp)
  trend: [                // últimas 8 horas
    {
      hour: "HH:00",
      oee: Number|null, availability: Number|null,
      performance: Number|null, quality: Number|null,
      hasData: Boolean
    }
  ],
  raw: { totalPieces, scrapPieces, totalDisponibleMinutos, totalDowntimeMin, range },
  _fallback?: Boolean, _fallbackReason?: String, _error?: String
}
```

### 2.2 Métricas Lean (`LeanMetricsController.calculateLeanMetrics`)

```
{
  taktTime: { value: Number|null, unit: 'min/pieza', timestamp },
  smed: { count, totalTime, avgTime, unit: 'min' },
  oee: { availability, performance, quality, oee, label },
  mtbf: { value: Number|null, unit: 'min entre fallos', incidents },
  mttr: { value: Number|null, unit: 'min para reparar', totalDowntime },
  shifts: { activos, completadosHoy },
  stock: { alertas, lotesActivos },
  ordenes: { activas, total }
}
```

### 2.3 KPIs financieros (`KPIService.getFinancialMetrics`)

```
{
  ordersTotal, ordersActive, ordersCompleted,
  estimatedCost, realCost, costVariance, costEfficiency,     // % (1 decimal)
  targetMaterialCost, realMaterialCost, materialVariance,
  materialEfficiency, scrapRate,                              // % (1 decimal)
  materialCostSource: 'line_level' | 'material_consumo_fallback'
}
```

### 2.4 Fuentes de datos

- `ProductionLog` (acciones `produce`/`scrap`, metadata.efficiency): producción y merma (spec 02).
- `Order.lines[].efficiency`: rendimiento por línea (se rellena en OrderService).
- `UserShift` (status `completed`/`active`, totalHours, loginTime, logoutTime): tiempo disponible real.
- `Incidencia` (`createdAt`, `resolucion.tiempoParada` en minutos): downtime.
- `Order` (status, estimatedTotalCost, realTotalCost, createdAt) + `Order.lines[]` (targetMaterialCost, realMaterialCost, efficiency): KPIs financieros.
- `MaterialConsumo` (`totalCost`, `date`): fallback de coste real de material en modo auditoría.
- `Material` (`stock.current`, `stock.minimum`, `code`, `name`): alertas de stock.
- `StockItem` (estado `activo`/`pico`): lotes activos.
- `Tooling` (status `Mantenimiento`, currentCycles, maxCycles): alertas Andon.

### 2.5 Mapa de costes (OrderCostCalculator, huérfano)

- `workstationConfig: {workstationId -> {hourlyCost, materialBOM}}` desde `tenant.workstations` (standalone + grupos).
- `materialCostMap: {materialCode -> costPerUnit}` desde `Material.find({tenantId, code: {$in: codes}})`.

## 3. Operaciones clave

### 3.1 `OEEService.calculateOEE(tenantId, range = 'today', workstationId = null)` -> resultado OEE

Comportamiento:
1. **Rango**: `startDate` = inicio del día (00:00:00.000). `week` -> lunes de la semana actual (`diff = fecha - día + (día === 0 ? -6 : 1)`; domingo retrocede 6 días); `month` -> día 1. Filtro de logs: `tenantId + timestamp >= startDate && <= now`. Nota: el parámetro `workstationId` se acepta pero NO se usa en el filtrado (quirk legacy).
2. **Producción y merma desde logs**: `totalPieces = Σ quantity` de logs `produce`; `scrapPieces = Σ quantity` de logs `scrap` (ordenados por timestamp ascendente, aunque el orden no afecta a la suma).
3. **Rendimiento (P)**: `averageEfficiency` = media aritmética de `lines[].efficiency > 0` de las órdenes con `updatedAt >= startDate` (todas las líneas, sin filtrar por estado). Si no hay eficiencias, 0.
4. **Disponibilidad (A)**:
   - Turnos completados del periodo: `UserShift.find({tenantId, status: 'completed', logoutTime: {$gte: startDate}})`; minutos por turno = `totalHours * 60` si existe y > 0, si no `min(max(logoutTime - loginTime, 0), 14 * 60)`.
   - Turnos activos: `UserShift.find({tenantId, status: 'active'})`; minutos = `min(max(now - loginTime, 0), 14 * 60)`.
   - `totalDisponibleMinutos = Σ` de ambos.
   - Downtime: `totalDowntimeMin = Σ incidencias.resolucion.tiempoParada` de `Incidencia.find({tenantId, createdAt: {$gte: startDate}})` (valor ausente cuenta como 0).
   - **Fallback**: si `totalDisponibleMinutos === 0`, se usa default: `480` (today), `480 * 5 = 2400` (week), `480 * 22 = 10560` (month), `480` (resto).
   - `availability = max(0, (effectiveAvailableMinutes - totalDowntimeMin) / effectiveAvailableMinutes)`, decimal; si minutos <= 0, 1.0.
5. **Calidad (Q)**: `totalProduction = totalPieces + scrapPieces`; `quality = totalProduction > 0 ? totalPieces / totalProduction : 1.0`.
6. **Rendimiento (P)**: `performance = averageEfficiency > 0 ? averageEfficiency / 100 : 0`.
7. **OEE**: `oee = availability * performance * quality` (decimal).
8. **Resultado**: multiplica por 100 y clamp a 100: `availability = min(A*100, 100)`, `performance = min(P*100, 100)`, `quality = min(Q*100, 100)`, `oee = min(OEE*100, 100)`. Añade `raw` con `totalPieces`, `scrapPieces`, `totalDisponibleMinutos`, `totalDowntimeMin`, `range`.
9. **Tendencia horaria** (últimas 8 horas, incluyendo la hora actual): para cada hora `[horaInicio, horaInicio+1h)`:
   - `hourProduce`/`hourScrap` = sumas de logs de la hora; `effSum`/`effCount` = media de `log.metadata.efficiency` (solo si es number) de los logs `produce` de la hora.
   - `hourHasData = hourProduce > 0 || hourScrap > 0 || effCount > 0`. Horas sin datos -> todos los valores `null` y `hasData: false` (AUDIT FIX 2.3: ya NO se generan datos aleatorios).
   - `hourAvailability = availability` global del periodo (decimal); `hourQuality = (hourProduce + hourScrap) > 0 ? hourProduce / (hourProduce + hourScrap) : 1.0`; `hourPerformance = effCount > 0 ? (effSum / effCount) / 100 : performance`.
   - `hourOee = hourAvailability * hourPerformance * hourQuality`.
   - Clamps del trend (1 decimal): `oee <= 115`, `performance <= 115`, `availability <= 100`, `quality <= 100`.
10. **Caché de resiliencia**: guarda el resultado en `oee_cache/oee_<tenantId>_<range>.json` con timestamp. En `catch` (fallo de MongoDB), si la caché tiene menos de 30 minutos se devuelve con `_fallback: true` y `_fallbackReason`; si no, estructura vacía con `_error` y `_fallback: true`.

Invariantes: OEE = A x P x Q siempre; ningún componente puede superar 100 en el resultado principal; la tendencia puede superar 100 (hasta 115) para OEE y performance; sin producción en una hora no se inventan datos.

### 3.2 `LeanMetricsController.calculateLeanMetrics(tenantId)` -> métricas Lean (fuente unificada mensual)

Comportamiento:
1. **Takt Time**: `tiempoDisponibleMinutos = 480` (fijo, 8 h); `taktTime = 480 / activeOrders.length` (min/pieza, 1 decimal); `null` si no hay órdenes activas.
2. **SMED** (últimas 24 h): logs `setup_start`; `count`; `totalTime = Σ metadata.smedMinutes` (ausente = 0); `avgTime = totalTime / count` (1 decimal, 0 si count 0).
3. **OEE mensual** (desde `mesStart` = día 1 del mes):
   - Órdenes del mes: `Order.find({tenantId, status: {$in: ['active','completed']}, updatedAt: {$gte: mesStart}})`.
   - `totalEfficiency/effCount`: media de `lines[].efficiency` (valores truthy) de esas órdenes.
   - `totalProduced = Σ lines[].producedQuantity`; `totalProducedFromLogs = Σ produce logs`; **`effectiveProduced = max(totalProduced, totalProducedFromLogs)`** (los logs son más precisos, pero puede haber producción registrada directamente en la orden sin log).
   - `totalScrap = Σ scrap logs` (action `scrap`, timestamp >= mesStart).
   - `totalDowntimeMin = Σ incidencias.resolucion.tiempoParada` (createdAt >= mesStart).
   - Tiempo operativo: turnos completados con `logoutTime >= mesStart` (totalHours*60 o diff cap 14 h) + turnos activos (now - loginTime cap 14 h); `effectiveAvailableMinutes = totalOperativoMin > 0 ? totalOperativoMin : 480 * 22`.
   - `availability = max(0, (available - downtime) / available) * 100` (1 decimal).
   - `performance = min(avgEfficiency, 100)` (1 decimal).
   - `quality = totalProd > 0 ? (effectiveProduced / (effectiveProduced + totalScrap)) * 100 : 100` (1 decimal).
   - `oee = (A/100) * (P/100) * (Q/100) * 100` (1 decimal); `label = "<oee>% (A:<A>% x P:<P>% x Q:<Q>%)"`.
4. **MTBF/MTTR**: `incidenciasPeriodo = incidenciasMes.length`; `mtbf = incidenciasPeriodo > 0 ? effectiveAvailableMinutes / incidenciasPeriodo : null` (min entre fallos, 1 decimal); `mttr = incidenciasPeriodo > 0 ? totalDowntimeMin / incidenciasPeriodo : null` (min para reparar, 1 decimal).
5. **Turnos**: `completadosHoy = count UserShift(status completed, logoutTime >= hoyStart)`; `activos = count UserShift(status active)`.
6. **Stock**: `alertas = count Material(isActive, stock.current <= stock.minimum)`; `lotesActivos = count StockItem(estado in ['activo','pico'])`.
7. **Órdenes**: `activas = activeOrders.length`, `total = ordersDelMes.length`.
8. Caché por tenant en Map, TTL 2 minutos; `source: 'cache' | 'db'` en la respuesta HTTP.

Invariantes: OEE mensual usa `updatedAt` para filtrar órdenes (no createdAt); la producción efectiva es el MAX entre líneas y logs; el tiempo disponible se basa en turnos reales con cap de 14 h, con fallback 480 x 22 min/mes.

### 3.3 `KPIService.getFinancialMetrics(tenantId, range = 'month')` -> KPIs financieros

Comportamiento:
1. **Caché en memoria** (instancia singleton): clave `"<tenantId>_<range>"`, TTL 5 minutos (300000 ms). Si es válida, devuelve `cached.data`.
2. **Filtro de fechas** (`_getDateFilter`): `today` -> inicio de hoy; `week` -> lunes de la semana; `month` -> día 1; `year` -> 1 de enero; `all` o default -> `null` (sin filtro).
3. **Pipeline de agregación** (compute close to data, en MongoDB):
   - `$match`: `tenantId`, `status: {$in: ['active','completed']}`, y `createdAt >= startDate` si aplica. (Usa `createdAt`, no `updatedAt`.)
   - Rama `orderMetrics` ($group _id null): `count = Σ 1`, `activeCount = Σ (status == 'active' ? 1 : 0)`, `completedCount = Σ (status == 'completed' ? 1 : 0)`, `totalEstimatedCost = Σ estimatedTotalCost`, `totalRealCost = Σ realTotalCost`.
   - Rama `lineMetrics` ($unwind lines + $group): `totalTargetMaterialCost = Σ lines.targetMaterialCost`, `totalRealMaterialCost = Σ lines.realMaterialCost`.
4. **Fallback modo auditoría** (AUDIT FIX 1.5): si `totalRealMaterialCost === 0 && totalRealCost > 0`, consulta `MaterialConsumo.aggregate([{$match: {tenantId, date >= startDate}}, {$group: {total: Σ totalCost}}])`; si `total > 0`, `effectiveRealMaterialCost = total` y `materialCostSource = 'material_consumo_fallback'`. Si no, `effectiveRealMaterialCost = linesData.totalRealMaterialCost` y `materialCostSource = 'line_level'`.
5. **Derivados**:
   - `costVariance = totalRealCost - totalEstimatedCost` (positivo = sobrecoste).
   - `costEfficiency = totalEstimatedCost > 0 ? (totalEstimatedCost / (totalRealCost || 1)) * 100 : 0` (INVERTIDO: > 100 significa coste real menor que el estimado; divisor con `|| 1` para evitar división por cero).
   - `materialVariance = effectiveRealMaterialCost - totalTargetMaterialCost`.
   - `materialEfficiency = totalTargetMaterialCost > 0 ? (totalTargetMaterialCost / (effectiveRealMaterialCost || 1)) * 100 : 0` (también invertido).
   - `scrapRate = effectiveRealMaterialCost > 0 ? (materialVariance / effectiveRealMaterialCost) * 100 : 0` (tasa de merma financiera: % del material real que excede el teórico).
6. **Redondeos**: costes y varianzas a 2 decimales; eficiencias y scrapRate a 1 decimal. Guarda en caché y devuelve.

Invariantes: solo cuentan órdenes `active`/`completed`; el coste real de material puede venir de dos fuentes (líneas o MaterialConsumo) y se expone `materialCostSource` para depuración; los ratios nunca lanzan división por cero (fallback `|| 1` o guard de > 0).

### 3.4 `OrderCostCalculator` (huérfano, contrato de fórmulas)

- `buildWorkstationConfigMap(tenantConfig)`: itera `workstations.standalone` y `workstations.groups[].workstations` -> `{id: {hourlyCost: w.hourlyCost || 0, materialBOM: w.materialBOM || null}}`. Sin config -> `{}`.
- `buildMaterialCostMap(tenantId, materialCodes)`: `Material.find({tenantId, code: {$in: uniqueCodes}})` -> `{code: m.costPerUnit || 0}`. Sin códigos -> `{}`.
- `calculateLaborCost(hourlyCost, estimatedTime)` = `(estimatedTime / 60) * hourlyCost` (minutos a horas por coste horario).
- `calculateBOMCost(bom, quantity, materialCostPerUnit)`: si falta bom o quantity -> `{targetMaterialQty: 0, targetMaterialCost: 0, unit: 'uds'}`; si no `targetMaterialQty = quantity * (bom.consumptionRate || 0)`, `targetMaterialCost = targetMaterialQty * materialCostPerUnit`, `unit = bom.unit || 'uds'`.
- `calculateRealTimeCost(hourlyCost, realTimeMinutes)` = `round((realTimeMinutes / 60) * hourlyCost, 2)`.
- `calculateLineCosts(lineData, wsConfig, materialCost)`: delega en `ValidationService.calculateLineCosts` con `{materialCost, hourlyCost: wsConfig.hourlyCost || 0, estimatedTime: lineData.estimatedTime || 0}`.
- `calculateOrderTotalCost(lines)` = `Σ (line.estimatedCost + line.targetMaterialCost)`.
  - **INCONSISTENCIA CONOCIDA**: en `OrderService.calculateOrderLines` (spec 02) el `estimatedCost` de línea YA incluye `targetMaterialCost`, por lo que sumar ambos aquí duplicaría el material. Este método no se usa en runtime; la reconstrucción debe usar la semántica de `calculateOrderLines` (total = Σ estimatedCost de línea) y descartar o corregir este método.

### 3.5 `ValidationService` (fórmulas de apoyo)

- `findValueByAlias(data, fieldName)`: busca con alias case-insensitive. Aliases: `totalQuantity: ['cantidadTotal','cantidad_total','cantidad','qty','quantity']`; `materialCode: ['material','material_asociado','tipo_material','materialCode','code']`; `measure: ['largo','longitud','medida_corte','medida','length']`; `color: ['ral','color','acabado','pintura']`; `totalWeight: ['peso_total_pedido','peso_total','kilos_totales','totalWeight']`. Orden: match exacto -> match lowercase -> alias lowercase. Devuelve `null` si no hay.
- `performCalculations(lineData)`: si `quantity > 0 && measure > 0`: `meters = round(quantity * measure / 1000, 2)` (piezas x mm a metros). Si `totalWeight > 0 && meters > 0`: `weightPerMeter = round(totalWeight / meters, 3)` (kg/m). Normaliza `totalQuantity`.
- `calculateLineCosts(processedLine, costs)`: `costMat = totalQuantity * materialCost` (ambas ramas, con o sin metros calculados, son idénticas: precio por unidad base); `costLabor = (estimatedTime / 60) * hourlyCost`; `estimatedCost = round(costMat + costLabor, 2)`.

### 3.6 `CalculationEngine` (huérfano, evaluación segura de fórmulas)

- `evaluate(formula, values)`: reemplaza cada `{fieldName}` por su valor; valores ausentes/null/vacío -> `0`; strings -> `parseFloat(valor.replace(',', '.')) || 0`; evalúa con **mathjs** (sandbox, sin `eval()`); si el resultado no es finito -> `null`; redondea a 4 decimales. Errores -> `null`.
- `recalculate(fieldDefs, currentValues)`: filtra campos `isCalculated && formula`, los ordena topológicamente por `dependencies` (los que tienen menos dependencias primero) y evalúa en orden, actualizando `newValues`. Campos sin resultado válido conservan su valor.
- `validateFormula(formula)`: reemplaza `{...}` por `1` y parsea con mathjs; `{valid, error?}`.
- `detectCircularDependencies(fieldDefs)`: grafo dirigido de dependencias (solo campos `isCalculated` con `dependencies`); DFS con pila de recursión; devuelve `{hasCycle, cycle?}`.
- `extractDependencies(formula)`: lista de nombres de `{placeholders}`.
- `_topologicalSort(fields)`: visit DFS visitando dependencias primero.

Invariantes: nunca se ejecuta código arbitrario (mathjs); fórmulas inválidas devuelven `null`/`{valid: false}` sin lanzar; el redondeo estándar es 4 decimales.

### 3.7 Coste real vs estimado (rutas vivas, resumen de spec 02)

- **Coste estimado (línea)**: `estimatedCost = (estimatedTime/60) * hourlyCost(puesto) + targetMaterialQty * costPerUnit(material)`; `estimatedTotalCost = Σ estimatedCost`. `targetMaterialQty` puede venir de BOM estático (`consumptionRate`) o de cálculo dinámico por dimensiones (largo x ancho x espesor x densidad 7850) cuando el materialCode casa con el regex de dimensiones.
- **Coste real (acumulación)**:
  1. Cierre de sesión (`updateLineStatus` a `completed`/`stopped`): `incrementalCost = durationHours x (machineHourlyCost + operatorHourlyCost + overheadHourlyCost)`; `$inc lines.realCost`, `order.realTotalCost`, `lines.realTime` (minutos).
  2. Registro de producción (`recordProduction`): `incrementalLaborCost = hoursWorked x (machine + operator + overhead)`; `incrementalMaterialCost = consumedAmount x material.costPerUnit` (solo modo simple se suma a `lines.realCost`; en auditoría solo labor).
  3. Roll-up de MaterialConsumo (post-save, tipos `automatico`/`manual`/`ajuste`): `order.realMaterialCost += totalCost` y `order.realTotalCost += totalCost`.
- **Varianza**: `costVariance = realTotalCost - estimatedTotalCost`; `materialVariance = realMaterialCost - targetMaterialCost`.
- **Merma**: en unidades, `scrapPieces` desde logs `scrap`; en material, `MaterialConsumo` con `calculationMethod = 'coil_end_scrap'`/tipo `merma_puntas` (puntas de bobina, NO desperdicio de proceso); en línea, `scrapMaterialQty`; financieramente, `scrapRate` de KPIService (ver 3.3).

### 3.8 Velocidad teórica y conversión unidades/metros

- `ManufacturingModel.unitsPerHour` (piezas por hora o metros por hora según `productionUnit`).
- Conversión a tiempo estándar por pieza: `(1 / unitsPerHour) * 60` minutos; tiempo de línea = per-unit x cantidad (spec 02, BOM explosion).
- Conversión de producción a metros (cuando `productionUnit === 'meters'`): `actualProducedValue = piezas * largoMm / 1000` donde `largoMm = line.customFields.largo || model.technicalSpecs.largo || 0`. Se aplica en: OEE de sesión (`updateLineStatus`), eficiencia acumulada y live OEE (`recordProduction`).
- Fórmulas de eficiencia (todas con `% = (real / teórico) * 100`):
  - Sesión: `efficiency = (actualProducedValue / (unitsPerHour x durationHours)) * 100` (2 decimales); `capacity <= 0` -> 0.
  - Acumulada: `realPerHour = realValue / (realTime/60)`; `efficiency = (realPerHour / unitsPerHour) * 100`.
  - Live: `stabilizedHours = max(liveHours, 0.016)` (piso 1 minuto); `capacity = unitsPerHour x stabilizedHours`; `efficiency = (actual / capacity) * 100`.
- El modelo de resolución para eficiencia: `line.manufacturingModelId` > `customFields.manufacturingModel` (code/name) > primer modelo activo por workstation (spec 02, `_resolveManufacturingModel`).

## 4. Reglas de negocio críticas

1. **OEE = Disponibilidad x Rendimiento x Calidad** (A x P x Q), siempre. Ningún componente del resultado principal supera 100 (clamp); la tendencia horaria admite hasta 115 en OEE y performance (eficiencias anómalas se muestran, no se ocultan).
2. **Disponibilidad basada en turnos reales** (UserShift), no en 480 min fijos: turnos completados + activos, cada uno con cap de 14 h; fallback 480 (día), 2400 (semana), 10560 (mes), 480 x 22 (Lean mensual). El cap de 14 h evita que sesiones perdidas (timeout de 30 min) inflen el OEE.
3. **Downtime = Σ incidencias.resolucion.tiempoParada** (minutos) del periodo; la disponibilidad se calcula como `(disponible - downtime) / disponible`, nunca negativa (`max(0, ...)`).
4. **Rendimiento = media de eficiencias de línea / 100**: en OEEService las líneas se toman de órdenes con `updatedAt >= startDate`; en Lean, de órdenes `active|completed` con `updatedAt >= mesStart`. Las eficiencias se generan en OrderService (spec 02) contra `unitsPerHour`.
5. **Calidad = piezas buenas / (buenas + merma)** desde ProductionLogs (`produce` vs `scrap`); sin producción, calidad = 1.0 (100).
6. **Producción efectiva Lean = max(Σ lines.producedQuantity, Σ logs produce)** (los logs son inmutables y más precisos; las órdenes pueden tener producción sin log).
7. **Nunca datos aleatorios en tendencias**: horas sin producción -> `null` + `hasData: false`.
8. **Resiliencia a caída de BD**: OEE se sirve desde caché en archivo (< 30 min) con `_fallback: true`; KPIs desde caché en memoria (5 min).
9. **KPIs financieros**: solo órdenes `active|completed`; `createdAt` como filtro temporal; ratios protegidos contra división por cero con `|| 1` o guard `> 0`.
10. **costEfficiency y materialEfficiency están INVERTIDOS** respecto a la intuición: `estimado / real * 100`; > 100 = se gastó menos de lo estimado. Preservar la semántica en el portado o renombrar explícitamente.
11. **scrapRate = (realMaterialCost - targetMaterialCost) / realMaterialCost * 100**: proxy financiero de merma; 0 si no hay coste real de material.
12. **Doble fuente de coste real de material**: línea (`realMaterialCost`) o `MaterialConsumo` (modo auditoría, carga en bulk al vincular bobina); siempre exponer `materialCostSource`.
13. **Evaluación de fórmulas segura**: mathjs, sin eval; valores ausentes = 0; strings con coma decimal normalizadas; redondeo a 4 decimales; errores -> null (nunca excepciones).
14. **MTBF/MTTR solo si hay incidencias**: `null` con 0 incidencias; MTBF usa el tiempo operativo real, no 30 x 480 fijo.
15. **Semántica de coste de línea**: `estimatedCost` YA incluye material (spec 02); el total de orden = Σ estimatedCost. No duplicar (ver 3.4, inconsistencia de `calculateOrderTotalCost`).

## 5. Casos límite conocidos

- **Sin turnos registrados**: disponibilidad usa defaults (480/2400/10560); en Lean 480 x 22. Resultado documentado en `raw.totalDisponibleMinutos = 0`.
- **Sin producción en el periodo**: calidad = 1.0 (OEEService) o 100 (Lean); OEE = A x P (si P > 0), típicamente 0 si no hay eficiencias.
- **Sin eficiencias**: performance = 0 -> OEE = 0 aunque haya producción (quirk: producción sin modelo resuelto no puntúa rendimiento).
- **`efficiency > 100`**: en línea se almacena (OrderService emite audit crítico); en OEE principal se clamp a 100; en trend se admite hasta 115. Indica unitsPerHour desconfigurado.
- **Caída de MongoDB**: OEEService devuelve caché de archivo (< 30 min) con `_fallback`; sin caché, estructura de ceros con `_error`.
- **`realCost = 0` en KPIService**: `costEfficiency = estimatedCost * 100` (divisor `|| 1`); puede dar valores enormes con órdenes estimadas sin coste real. Documentar como artefacto.
- **`realMaterialCost = 0`**: `scrapRate = 0` y `materialEfficiency = 0` (o target x 100 si target > 0).
- **Modo auditoría**: `lines.realMaterialCost` queda en 0 (material cargado en bulk por linkCoil); el fallback de `MaterialConsumo` en KPIService existe exactamente para esto.
- **`workstationId` en calculateOEE se ignora**: la firma lo acepta pero el filtrado no lo usa (quirk a corregir o documentar en el portado).
- **Tendencia con logs de más de 8 horas atrás**: no aparecen (ventana fija de 8 horas).
- **SMED sin metadata.smedMinutes**: totalTime 0 con count > 0 -> avgTime 0.
- **Takt Time con 0 órdenes activas**: `null` (no división por cero).
- **Órdenes borradas (soft delete)**: NO se excluyen explícitamente de los agregados de OEE/KPI (los queries no filtran `isDeleted`); el cascade delete (spec 02) limpia los datos hijos en borrado permanente para no corromper métricas.
- **`calculateOrderTotalCost` (huérfano) duplicaría material** si se usara con líneas de `calculateOrderLines`: inconsistencia conocida, no usar.
- **`CalculationEngine` con placeholders duplicados**: `expression.replace(placeholder, value)` reemplaza solo la primera ocurrencia por placeholder; con el mismo campo repetido, la segunda ocurrencia ya no casa (quirk menor; en el portado usar replace global).
- **Horas de turno `totalHours` ausente**: se calcula por diff login/logout con cap 14 h; en closeShift, cap > 14 h -> 8.0.

## 6. Requisitos para el modelo relacional (PostgreSQL)

Convenciones: igual que spec 02 (`BIGSERIAL`/UUID, `tenant_id FK`, `NUMERIC(12,2)` dinero, `NUMERIC(12,4)` cantidades, `NUMERIC(6,2)` porcentajes, `TIMESTAMPTZ`, JSONB para metadata).

### 6.1 Tablas adicionales (las de órdenes/turnos/logs ya están en spec 02)

**`incidencias`** (downtime)
- `id BIGSERIAL PK`, `tenant_id FK NOT NULL`, `tipo TEXT`, `descripcion TEXT`, `estado TEXT`, `operario_id BIGINT REFERENCES users(id)`, `puesto TEXT`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `resolucion JSONB NOT NULL DEFAULT '{}'` (contiene `tiempoParada` en minutos).
- Índices: `(tenant_id, created_at)`.
- Constraint app: `COALESCE(resolucion->>'tiempoParada', '0') >= 0`.

**`oee_calculations`** (snapshots históricos; sustituye a la caché de archivo como historial durable)
- `id BIGSERIAL PK`, `tenant_id FK NOT NULL`, `range TEXT NOT NULL CHECK (range IN ('today','week','month'))`, `calculated_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `availability NUMERIC(6,2) NOT NULL`, `performance NUMERIC(6,2) NOT NULL`, `quality NUMERIC(6,2) NOT NULL`, `oee NUMERIC(6,2) NOT NULL`, `total_pieces NUMERIC(12,4) NOT NULL DEFAULT 0`, `scrap_pieces NUMERIC(12,4) NOT NULL DEFAULT 0`, `total_available_minutes NUMERIC(10,2) NOT NULL DEFAULT 0`, `total_downtime_min NUMERIC(10,2) NOT NULL DEFAULT 0`, `source TEXT NOT NULL DEFAULT 'computed'`.
- Índices: `(tenant_id, range, calculated_at DESC)`.
- Checks: `availability BETWEEN 0 AND 100`, `quality BETWEEN 0 AND 100`, `oee BETWEEN 0 AND 100`; `performance` permite hasta 115 en snapshots de tendencia (o usar tabla separada con check `<= 115`).

**`oee_hourly`** (tendencia horaria)
- `id BIGSERIAL PK`, `tenant_id FK`, `hour_start TIMESTAMPTZ NOT NULL`, `availability NUMERIC(6,2)`, `performance NUMERIC(6,2)`, `quality NUMERIC(6,2)`, `oee NUMERIC(6,2)`, `has_data BOOLEAN NOT NULL DEFAULT false`.
- Check: `oee <= 115 AND performance <= 115 AND availability <= 100 AND quality <= 100` (valores null permitidos).
- `UNIQUE (tenant_id, hour_start)`; upsert por hora.

**`kpi_financial_cache`** (o directamente vistas; recomendado: vistas materializadas)
- Si se conserva el TTL de 5 min, tabla `kpi_cache (tenant_id, range, calculated_at, payload JSONB)`.
- Preferible: **vistas SQL** `v_kpi_financials` que repliquen el pipeline: `COUNT(*) FILTER (WHERE status='active')`, `SUM(estimated_total_cost)`, `SUM(real_total_cost)`, `SUM(lines.target_material_cost)`, `SUM(lines.real_material_cost)` sobre `production_orders JOIN order_lines`, con `WHERE status IN ('active','completed') AND created_at >= $1`. El fallback de MaterialConsumo como UNION/COALESCE opcional.
- Las fórmulas derivadas (`cost_variance`, `cost_efficiency`, `material_variance`, `material_efficiency`, `scrap_rate`) se implementan como funciones SQL puras (deterministas) para testear con TDD.

**`material_density` y dimensiones**: `materials.density NUMERIC(10,4) NOT NULL DEFAULT 7850` (check > 0); dimensiones `ancho`/`espesor` en JSONB o columnas dedicadas (ver spec 02).

### 6.2 Vistas y funciones recomendadas

- Vista `v_oee_period` (equivalente a OEEService.calculateOEE en SQL):
  - Disponibilidad: `GREATEST(0, (LEAST(SUM(sh.total_hours)*60, SUM(LEAST(EXTRACT(EPOCH FROM (sh.logout_time - sh.login_time))/60, 840))) - downtime) / disponible)` con las reglas de cap 14 h y fallback por rango.
  - Calidad: `SUM(quantity) FILTER (WHERE action='produce') / NULLIF(SUM(quantity) FILTER (WHERE action IN ('produce','scrap')), 0)`.
  - Rendimiento: `AVG(l.efficiency) FILTER (WHERE l.efficiency > 0) / 100` sobre `order_lines l JOIN production_orders o ON ... WHERE o.updated_at >= $1`.
- Función `fn_material_rollup()` (trigger en `material_consumos`): replica los hooks post-save/findOneAndDelete (solo tipos `automatico`,`manual`,`ajuste`), actualizando `production_orders.real_material_cost` y `real_total_cost` en la misma transacción.
- Función `fn_order_estimated_cost()` para recalcular `order_lines.estimated_cost = (estimated_time/60)*hourly_cost + target_material_qty*cost_per_unit` (invariante de spec 02, sección 3.2).

### 6.3 Integridad y consistencia

- `manufacturing_models.units_per_hour NUMERIC(12,4) NOT NULL DEFAULT 0 CHECK (units_per_hour >= 0)`; `production_unit CHECK IN ('units','meters')`.
- `order_lines.efficiency NUMERIC(6,2)` sin CHECK superior (legacy admite > 100); validar en app, clamp solo en agregados.
- `production_logs.metadata JSONB` debe conservar `efficiency`, `incrementalCost`, `incrementalMaterialCost`, `incrementalLaborCost`, `consumedAmount`, `materialConsumoIds` (contrato de undo, spec 02).
- TTL/caché: la caché de archivo de OEE y la de memoria de KPIs se sustituyen por snapshots (`oee_calculations`) y por vistas con `REFRESH MATERIALIZED VIEW CONCURRENTLY` o cálculos a demanda; el TTL de 30 min/5 min puede modelarse como política de refresco, no como ficheros.
- RLS por `tenant_id` en todas las tablas (ADR-002).
- Tests TDD obligatorios: OEE = A x P x Q exacto; caps (100/115); fallback de disponibilidad por rango; inversión de costEfficiency; fallback MaterialConsumo; conversión unidades/metros; live OEE con piso de 0.016 h.
