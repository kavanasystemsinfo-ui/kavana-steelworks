# Anexo A: Flujo real del operario (visión Jorge, 2026-08-14)

Este anexo documenta la visión de negocio del operario tal como la explicó
Jorge. Es la fuente de verdad para la UX de la Fase 3 y para validar la lógica
de la Fase 2. Reemplaza cualquier interpretación anterior que difiera.

## Roles

### Materias Primas (rol aún NO definido en el sistema)
Responsable de registrar el material que entra en la fábrica, identificando
cada bobina por: material, dimensiones (ancho/espesor) y peso. Este rol y su
flujo de recepción se definen como requisito pendiente (ver sección 6 de este
anexo).

### Operario de puesto
Entra en su puesto de trabajo y ejecuta el flujo descrito abajo.

## Flujo del operario

1. **Inicio en el puesto (empieza de cero)**: escanea o vincula la bobina
   metiendo su ID en el sistema.
   - **Modo automático**: el sistema auto calcula material, dimensiones y peso
     a partir del ID escaneado.
   - **Modo manual**: el sistema auto rellena material y dimensiones, y el
     operario introduce manualmente peso y número de lote (vienen en la
     etiqueta física de la bobina).
2. **Cobro por defecto**: al vincular la bobina, el sistema asume TODA la
   bobina (cobro BULK). Durante la producción la merma "se dispara" porque hay
   ​​0 piezas registradas: es material comprometido, no merma real.
3. **Producción durante el turno**: el operario gasta varias bobinas en su
   jornada. Registra cada una; el sistema va consumiendo los kg por FIFO.
   El total de piezas NO se revisa hasta el final del turno.
4. **Fin de bobina**: cuando una bobina queda a medias, antes de registrar la
   producción usa el flujo de fin de bobina: se miden los kg restantes
   ("la carne que queda") y el sistema calcula la realidad:
   piezas fabricadas VS kg consumidos.
5. **Cierre de turno**: se reconcilia el total. Es normal dejar una bobina
   empezada y no gastada; la usará el siguiente turno (queda como pico/retal
   en el puesto, elegible para continuar).

## Picos y retales (corrección de interpretación)

**NO es correcto** que el sistema "priorice el registro de picos" ni que los
consuma automáticamente antes que bobinas nuevas.

**Lo que sí quiere Jorge**: el sistema debe MOSTRAR al operario si existen
picos de bobina registrados en el almacén, para ACONSEJARLE usarlos antes de
empezar una bobina nueva. Es una recomendación visible (sugerencia), nunca una
imposición. El operario decide.

Requisito derivado (Fase 3, UX): al vincular una bobina nueva, el panel del
operario muestra un aviso no bloqueante: "Existen N picos de este material en
el almacén (ubicación X, Y kg). ¿Quieres usar uno antes de abrir bobina
nueva?" con acción opcional.

## Impacto en la lógica (Fase 2)

- El cobro BULK de `linkCoil` es correcto y se mantiene (spec 01, sección 3.3).
- La presentación del coste durante el turno debe etiquetarse como
  "material comprometido / pendiente de reconciliación", NO como merma
  (evita fricción y desconfianza del operario).
- La merma real solo se calcula en `createRetal` (fin de bobina) o cierre de
  turno (spec 01, secciones 3.5 y 3.6).
- Los picos se marcan con la regla del 10% (≤10% del original → `estado=pico`),
  pero su uso es decisión del operario con sugerencia del sistema.

## Requisito pendiente: rol de Materias Primas

- Flujo de recepción de material: registrar bobina entrante con material,
  dimensiones y peso real (báscula).
- Identificación por lote/etiqueta física.
- Sin este rol, el operario depende del modo manual para introducir peso y
  lote a mano.
- Estado: pendiente de diseño (fuera del alcance de la Fase 2 inicial).
