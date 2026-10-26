# Guía rápida del operario

Para quien trabaja en el puesto con la tablet. Una pantalla: la de Operario.

## Empezar el turno

1. Entra con tu usuario. El turno (A mañana, B tarde, C noche) se asigna solo.
2. Selecciona tu puesto de trabajo. Verás la cola de órdenes de ese puesto.
3. Elige la orden que vas a fabricar.

## Vincular la bobina

1. Pulsa "Escanear bobina" y escanea la etiqueta (o escribe el ID).
2. Comprueba material, lote, peso y dimensiones.
3. Pulsa "Vincular a mi orden". Desde ese momento el consumo de esa bobina
   se carga a tu orden (consumo FIFO).

Si la bobina no es del material que pide la orden, el sistema avisa y no la
vincula.

Una bobina solo puede estar en un sitio. Si ya está vinculada a otra orden
(en otra máquina o en la tuya), el sistema te dice en qué orden y puesto
está. Para usarla aquí, primero hay que desvincularla allí: se devuelve a
esa orden lo que no se ha consumido y la tuya paga solo lo que queda.

## Registrar producción

En "Registrar producción" indica las piezas buenas y las horas trabajadas.
El sistema descuenta los kilos de la bobina con la fórmula de densidad
(ancho x espesor x largo). Si los kilos teóricos superan a los reales de la
bobina más el margen, la producción se bloquea: suele significar que falta
vincular material.

## Fin de bobina

Cuando la bobina se acaba o la cambias, mide con el metro el radio que queda
en milímetros y escríbelo en "Fin de bobina". El sistema calcula los kilos
que quedan, registra la merma real y, si queda un pico aprovechable, puedes
pulsar "Retirar pico a inventario".

## Autocontrol de calidad

Rellena las mediciones del plan de autocontrol de la pieza. Cada valor se
compara con su nominal y tolerancias; el resultado queda en la trazabilidad.

## Incidencias

Pulsa "Incidencia", elige el tipo (máquina, material, seguridad u otro) y
descríbela. Puedes añadir una foto escaneando el QR con el móvil. El
supervisor la ve al momento en su panel y en el monitor de puestos.

## Cerrar la jornada

Al terminar, cierra la jornada. Quedan registradas tus horas de turno.
