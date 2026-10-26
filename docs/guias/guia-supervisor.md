# Guía rápida del supervisor

Para quien lleva la planta. Una pantalla: Supervisor, de arriba abajo.

## Centro de mando: cuatro tarjetas

- **OEE global**: disponibilidad x rendimiento x calidad. Sin datos muestra
  0, nunca una cifra inventada.
- **Consumo de material**: kilos consumidos y merma en kg, en % y en euros.
- **Coste de producción**: material + mano de obra de las órdenes activas y
  completadas.
- **Material real vs estimado**: solo en órdenes completadas. En una orden en
  curso la bobina se carga entera al vincularla, así que comparar antes de
  cerrarla engañaría.

Las cifras son el acumulado de las órdenes activas y completadas. Para un
turno concreto, usa el informe de turno.

## De dónde sale el coste

- Material: kilos consumidos x precio de la bobina (o el €/kg estándar del
  material).
- Mano de obra: horas declaradas x €/h del puesto. Si el puesto no tiene
  coste, se usa el coste global de la empresa (Admin, Empresa).
- Estimado: objetivo de material de la orden x €/kg estándar.

El MES valora la producción; no factura ni lleva contabilidad, eso es del
ERP.

## Alertas

Encima de las tarjetas aparecen las incidencias abiertas y los materiales
bajo mínimos. Cada contador sale del mismo dato que su pantalla de detalle.

## Coste por orden

Tabla con material, mano de obra, total, estimado, desviación y merma de cada
orden. Su suma cuadra con las tarjetas.

## Puestos en planta y modo Andon

Una tarjeta por puesto: orden, bobina vinculada, piezas, última actividad y
quién la hizo. Rojo = incidencia abierta; verde = en curso; ámbar = parado.
"Modo Andon" pone el mismo monitor a pantalla completa para una TV de planta
(Esc para salir).

## Informe de turno

Elige fecha y turno (A 06-14, B 14-22, C 22-06). Por puesto: piezas,
consumo, merma, autocontroles (y no conformes) e incidencias con su tiempo de
parada. "Descargar CSV" lo abre en Excel; "Imprimir / PDF" lo guarda en PDF.

## Órdenes, trazabilidad, calidad e incidencias

Debajo puedes crear y lanzar órdenes, ver la trazabilidad ISO 9001 de cada
orden (eventos inmutables), la bandeja de autocontroles y resolver
incidencias. El botón naranja de acción rápida lleva a cada sección.
