# Spec 06: Módulo de Recepción de Materiales (Materias Primas)

Estado: Propuesta para revisión de Jorge
Fecha: 2026-08-14
Basada en: investigación externa verificada (Perplexity Sonar, 2026-08-14)
sobre flujos estándar de recepción en ERP/MES (SAP, Oracle, Infor) y buenas
prácticas en plantas de bobinas de acero.

## Objetivo

Definir el rol de **Materias Primas** (hoy inexistente en el v2) con el flujo
de registro de material entrante, de forma que cualquier empresa industrial
reconozca el proceso y la terminología. La investigación confirma que el
estándar de la industria es una cadena controlada:

**ASN/albarán → recepción física → GRN (entrada en almacén) → identificación
de lote → etiquetado → control de calidad → ubicación (putaway)**

## 1. Vocabulario estándar (lo que reconoce cualquier planta)

| Término | Significado | Equivalente en Steelworks |
|---|---|---|
| **ASN** (Advanced Shipping Notice) | Aviso previo del proveedor: qué llega, cuánto, packaging | Albarán de entrada / aviso de expedición |
| **GRN** (Goods Receipt Note) | Confirmación oficial de que el material entró en stock | Entrada en almacén / parte de recepción |
| **Recepción** | Proceso físico de descarga, conteo y verificación | Recepción de materiales |
| **Lote / batch** | Unidad de trazabilidad con identidad propia | Lote de bobina |
| **Etiqueta** | Identificación física escaneable del material | Etiqueta de bobina (código QR/barras) |
| **Putaway / ubicación** | Asignación del material a una ubicación de almacén | Ubicación en almacén |
| **Picking** | Preparación de material para producción | Sugerencia de bobina al operario |
| **Inspection / bloqueo** | Estado de calidad: material retenido o libre para uso | Estado cuarentena/bloqueado (ya existe) |

## 2. Flujo estándar de recepción (paso a paso)

### Paso 1: Aviso de llegada (ASN/albarán)
- El proveedor envía el albarán con: proveedor, material, cantidad, bobinas
  esperadas (número de bobina del proveedor, si existe), fecha.
- El responsable de Materias Primas crea o recibe el aviso en el sistema
  ANTES de que llegue el camión. En el v4 esto es un registro opcional de
  entrada esperada (YAGNI: no requiere módulo de compras completo).

### Paso 2: Recepción física (descarga y verificación)
- Se descarga la bobina, se pesa en báscula y se verifican los datos del
  albarán contra la realidad física.
- Se capturan los atributos obligatorios de la bobina (según investigación):
  peso real, ancho, espesor, grado/calidad del acero, número de calor (heat
  number) si existe, número de bobina del proveedor, y fecha de recepción.

### Paso 3: GRN (entrada en almacén)
- El sistema registra la entrada como transacción `entrada_compra` en el
  Kardex inmutable (ya modelado en `material_transactions`).
- Se crea el `stock_item` con su lote, peso inicial = peso real de báscula,
  y coste real de compra (si se conoce) o coste estándar del material.

### Paso 4: Identificación y etiquetado
- El sistema genera una etiqueta escaneable por bobina (QR con el coil_id y
  lote). El operario escanea esa etiqueta al vincular, en lugar de teclear.
- El coil_id autogenerado o el del proveedor queda como identidad física.

### Paso 5: Control de calidad en recepción
- Opcional (YAGNI): si la empresa lo usa, la bobina entra en estado
  `cuarentena` hasta inspección, luego pasa a `activo` o `bloqueado`.
- El estado ya está modelado en `stock_items.estado`.
- Por defecto (sin inspección): la bobina entra directamente `activo`.

### Paso 6: Ubicación (putaway)
- El responsable asigna la ubicación física (estantería, zona, pasillo) o el
  sistema la sugiere por tipo de material.
- La ubicación es la clave que usa el modo simple del operario (filtro por
  puesto) y el JIT Move (mover la bobina al puesto cuando se necesita).

## 3. Separación de roles (hallazgo clave de la investigación)

La investigación confirma la intuición de Jorge: **recepción y producción son
roles distintos y deben estar separados.**

| Rol | Responsabilidad | NO debe hacer |
|---|---|---|
| **Materias Primas** (nuevo) | Recibir, pesar, etiquetar, ubicar, crear lotes, control de calidad de entrada | Consumir material ni registrar producción |
| **Operario** | Vincular bobina al puesto, producir, registrar consumo, fin de bobina | Crear lotes ni dar de alta material (salvo modo manual de emergencia) |

Esto elimina la fricción actual del v2, donde el operario tenía que teclear
peso y lote a mano porque no existía el rol de recepción.

## 4. Modo automático vs manual (mantiene la visión de Jorge)

- **Automático**: Materias Primas ya registró la bobina con todos sus datos.
  El operario escanea la etiqueta y el sistema auto-rellena material,
  dimensiones y peso. Cero tecleo.
- **Manual (emergencia)**: si la bobina no está registrada, el sistema
  auto-rellena material y dimensiones desde el nombre (parseo existente) y el
  operario introduce peso y lote de la etiqueta física. Queda marcada como
  entrada manual pendiente de confirmación por Materias Primas (auditoría).

## 7. Decisiones de Jorge (2026-08-14)

1. **Registro cuando llega**: NO se implementa albarán previo (ASN) en el
   flujo mínimo. La bobina se registra directamente al recibirla. El ASN
   queda como feature `receiving_asn` del plan industrial (ADR-003).
2. **Entrada directa a producción**: la bobina entra en estado `activo` sin
   cuarentena. El control de calidad en recepción queda como feature
   `receiving_quality_check` del plan industrial (cuarentena → inspección →
   liberación), desactivada por defecto.
3. **Ambos costes**: el sistema soporta coste real de compra por lote
   (`costing_method='real'`, feature `coste_real`) y coste estándar del
   material (`costing_method='standard'`, feature `coste_estandar`, activa
   en todos los planes). El modelo ya lo soporta: `stock_items.costing_method`.

## 8. Sistema de planes (básico, pro, industrial)

El módulo de recepción, como todo el flujo de planta, se gobierna por feature
flags por tenant (ADR-003). La misma instalación sirve a una planta pequeña
(manual) y a una gran (automatizada):

- **Básico**: recepción simple, coste estándar, vinculación manual, Kardex.
  Para plantas pequeñas que prefieren control manual del operario.
- **Pro**: añade auto-vinculación de bobinas, burbuja FIFO, sugerencias de
  picos, coste real, OEE/KPIs. Para plantas medianas que quieren
  automatización sin dejar de verlo todo.
- **Industrial**: añade albarán previo (ASN), control de calidad en
  recepción, trazabilidad ISO 9001 completa (heat number, certificados).
  Para plantas grandes con requisitos de calidad y auditoría.

El plan es un punto de partida: un tenant puede activar features concretas
de otro plan sin cambiar de plan completo (override individual).

## 9. Endpoints del módulo (borrador)

| Método | Ruta | Función |
|---|---|---|
| POST | `/api/v1/receiving/entries` | Crear aviso de llegada (albarán) |
| POST | `/api/v1/receiving/entries/{id}/receive` | Confirmar recepción física + GRN |
| POST | `/api/v1/stock-items` | Alta de bobina con atributos completos |
| POST | `/api/v1/stock-items/{id}/label` | Generar etiqueta QR escaneable |
| PATCH | `/api/v1/stock-items/{id}/location` | Asignar ubicación (putaway) |
| GET | `/api/v1/receiving/pending` | Cola de recepciones pendientes |
