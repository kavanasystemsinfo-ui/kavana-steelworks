# Anexo B: Conexión del módulo de recepción con el flujo existente

Este anexo complementa la spec 06 y el anexo A (flujo del operario). Define
cómo encaja la recepción de materiales con el motor FIFO, los picos y las
sugerencias de consumo que ya están implementados o especificados.

## 1. Recepción → stock → FIFO

La cadena completa queda así:

```
Materias Primas                  Operario
─────────────                    ────────
1. Recibe bobina (peso real)
2. Crea stock_item + lote
3. Etiqueta QR
4. Asigna ubicación  ────────▶  5. Escanea etiqueta (auto-relleno)
                                6. Vincula a orden (linkCoil, cobro BULK)
                                7. Produce: FIFO consume kg
                                8. Fin de bobina: mide resto, crea retal/pico
                                9. Pico vuelve a stock (visible para reuso)
```

## 2. Picos: recomendación, no imposición (visión Jorge)

Cuando el operario va a vincular una bobina nueva, el sistema consulta si
existen **picos** (retales ≤10% del original) de ese material en el almacén.
Si existen, muestra un aviso no bloqueante:

> "Existen 2 picos de ACERO-01 en ALMACEN-3 (120 kg y 45 kg).
> ¿Usar uno antes de abrir bobina nueva? [Usar pico] [Continuar]"

La decisión es siempre del operario. El sistema nunca impone el pico ni lo
prioriza automáticamente en el FIFO (corrección documentada en anexo A).

## 3. Etiquetado con estándar GS1 (opcional, Fase 3)

La investigación confirma que las plantas usan etiquetas GS1-128 o códigos de
barras/QR para escanear en recepción, movimiento y consumo. Para el v4:

- La etiqueta de bobina usa QR con: coil_id, lote, material, peso, ancho,
  espesor, ubicación.
- El escaneo alimenta los formularios automáticamente (cero tecleo).
- GS1 completo (AI + data matrix) se puede añadir más adelante sin romper el
  diseño: el QR interno es suficiente para el flujo de planta.

## 4. Sugerencia de consumo por FIFO dentro de grado/dimensiones

La investigación indica que en plantas de bobinas el FIFO se aplica "dentro de
un mismo grado, espesor, ancho y calidad". Implicación para el v4:

- El FIFO actual ya ordena por `fecha_entrada` ASC dentro del material.
- Si un material tiene variantes (mismo code, distinto ancho), la sugerencia
  al operario debe priorizar la bobina con las dimensiones que la orden
  requiere (el ancho del modelo), tal como hacía el v2 con el filtro por
  ancho de `MaterialScanner.jsx:197`.
- Esto NO cambia la lógica FIFO: añade un orden de preferencia por ancho en
  la sugerencia visible, manteniendo FIFO dentro del ancho correcto.

## 5. Trazabilidad ISO 9001 (lo que ya tenemos vs lo que falta)

| Requisito ISO 9001 | Estado en Steelworks |
|---|---|
| Identificación de cada bobina | ✅ stock_items con coil_id + lote |
| Registro de recepción (Kardex) | ✅ material_transactions tipo entrada_compra |
| Genealogía bobina → piezas | ✅ material_consumos + production logs (Fase 2/3) |
| Registro de retales con padre | ⚠️ stock_items guarda el pico; falta campo `parent_coil_id` |
| Certificados/heat number digitales | ❌ Falta (campo opcional en stock_items) |

**Acción para Fase 2**: añadir a `stock_items` los campos `heat_number`,
`grado_acero`, `supplier_coil_id` y `parent_coil_id` (para retales), que la
investigación marca como atributos obligatorios de una bobina. Son opcionales
en el alta, no rompen el modelo actual.

## 6. Fuentes de la investigación (verificadas 2026-08-14)

- SAP/EWM: recepción ligada a ASN/inbound delivery, creación de batch en GRN,
  putaway con tareas de almacén y escaneo RF (SAP EWM receiving with/without
  ASN).
- Oracle: etiquetas GS1/barcode, putaway con documentos escaneables, recepción
  separada de ubicación.
- Buenas prácticas de bobinas: coil ID único + heat number + MTR, atributos
  mínimos (peso, ancho, espesor, grado), remanentes clasificados (retales,
  sobrantes, picos), no mezclar heats/grados, reconciliación de stock tras
  cambios de bobina y scrap.
- Roles: recepción = materias primas/almacén, no el operario de producción.
- Términos en plantas españolas: retales, sobrantes, remanentes, picos
  (varía por planta; lo importante es clasificarlos de forma consistente).

## 7. Decisiones de Jorge (resueltas 2026-08-14)

1. Registro cuando llega: NO albarán previo en flujo mínimo (`receiving_asn`
   solo en plan industrial, ADR-003).
2. Entrada directa a producción: bobina entra `activo` sin cuarentena
   (`receiving_quality_check` solo en plan industrial, ADR-003).
3. Ambos costes: `costing_method` soporta `standard` y `real`; el coste real
   de compra se introduce en recepción si se conoce, si no se usa el estándar.

El sistema de planes (básico/pro/industrial) se describe en la spec 06
sección 8 y en el ADR-003.
