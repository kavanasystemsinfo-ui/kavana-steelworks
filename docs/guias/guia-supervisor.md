# Guía rápida del supervisor

Para quien lleva la planta. Una pantalla: Supervisor, de arriba abajo.

## Material y costes: qué se ve por defecto

El panel enseña por defecto lo que la planta mide: **kilos transformados, chatarra y
merma** (pestaña **Material**). Los euros (€/kg, coste por orden, mano de obra,
desviación en euros, coste de las incidencias) dependen de precios y costes por hora que
cada empresa tiene que cargar, y el MES no lleva contabilidad. Por eso la pestaña
**Costes** y los importes en euros están **desactivados** hasta que un administrador los
active en Administración, Empresa, "Mostrar costes en euros en el panel del supervisor".

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

## Costes del periodo

Entre las tarjetas y el coste por orden. Eliges **Semana**, **Mes** o
**Trimestre**; la ventana es la de planta: de lunes a lunes, del día 1 al 1 y
trimestre natural (agosto y septiembre son el tercer trimestre; octubre abre
el cuarto). Una orden cuenta en el periodo en que se tocó por última vez.

- **€/kg del periodo**, partido en sus dos mitades: **material** (lo que
  cuesta el acero, con la merma ya dentro) y **transformación** (mano de obra).
  Las dos cifras suman el €/kg. Sirve para saber si el problema es que se
  compró caro o que la planta va lenta: el material es la mayor parte del
  coste y no lo controla la planta; la transformación sí. Debajo, el €/kg del
  periodo anterior y el objetivo de la empresa si lo has configurado en Admin
  (Empresa). Sin objetivo, lo dice: no enseña un cero que parezca un objetivo.
- **Coste total**, kilos valorados y órdenes completadas. Solo las líneas
  medidas en kilos entran en el €/kg; las líneas en metros se cuentan aparte
  para no mezclar unidades. El coste total sí las incluye.
- **Chatarra**: euros y porcentaje sobre el material cargado. No se cuenta dos
  veces: en el reparto, el material va ya sin la chatarra.
- **Desviación sobre lo estimado**: euros y porcentaje de las órdenes
  completadas que tienen estimado. Sin órdenes con estimado no hay
  comparación que enseñar.
- **Reparto del coste**: material, mano de obra y chatarra. Suma el coste
  total.
- **Coste por familia de material**: galvanizado, decapado, aluminio y «sin
  clasificar». Cada fila lleva kilos, €/kg de material, €/kg de transformación,
  merma sobre el material y número de órdenes. La familia se deduce del código
  o del nombre del material (FLEJE-G, FLEJE-D, ALU, galva, decapado, DC01,
  DX51D); lo que no se reconoce aparece como «sin clasificar» en vez de
  suponerse. Sirve para ver si un mes se va en acero caro o en planta lenta sin
  que el mix de materiales engañe.
- **Coste de paradas**: incidencias del periodo valoradas a €/h del puesto (o
  al coste global de la empresa), desglosadas por tipo.
- **Tendencia**: €/kg de las últimas ocho semanas.
- **Órdenes con más desviación**: como mucho diez, ordenadas por desviación.
  La causa la calcula el sistema: chatarra alta, paradas, mejor
  aprovechamiento, dentro de lo normal o sin causa clara.

"Descargar CSV de costes" baja el mismo contenido en CSV para Excel español
(separador punto y coma, coma decimal).

## Puestos en planta y modo Andon

Una tarjeta por puesto: orden, bobina vinculada, piezas, última actividad y
quién la hizo. Rojo = incidencia abierta; verde = en curso; ámbar = parado.
"Modo Andon" pone el mismo monitor a pantalla completa para una TV de planta
(Esc para salir).

## Comparativa de puestos

En la pestaña **Planta**, antes de las entregas: una fila por puesto (también los que no
han producido) con piezas, plan, eficiencia, paradas (tiempo y número) y chatarra (kg y %).
Pulsa el título de una columna para ordenar (otra vez para invertir); por defecto va primero
el puesto de menor eficiencia, y los que no tienen dato quedan al final. Pulsa el puesto para
abrir su ficha. Cada puesto usa su propia chatarra para su calidad.

## Ficha de puesto: qué ha hecho cada operario

Desde la pestaña **Planta** (pulsa el nombre del puesto en «¿Qué puesto frena la
planta?») o desde la pestaña **Turno** («Ver ficha» en la tarjeta del puesto). Elige
Hoy, Esta semana o Últimas 8 semanas.

- **Arriba:** estado ahora (orden, bobina, último registro e incidencia abierta), piezas
  contra plan, eficiencia (en marcha, velocidad, piezas buenas), tiempo parado y kilos
  de chatarra. Sin euros, aunque la opción de costes esté activada.
- **¿Por qué para este puesto?:** paradas e incidencias del puesto, por causa.
- **Sesiones:** una sesión es el trabajo seguido de un operario en una línea de orden.
  Se abre una nueva si cambia el operario, si cambia la línea o si pasan más de 4 horas
  sin registros (así un operario que vuelve al día siguiente no suma una sesión de 20 h).
  Cada sesión muestra operario, horario, orden, piezas, chatarra y bobinas; púlsala para
  ver cada registro con su hora, cantidad y bobina activa. La más reciente va primero.

## Informe de turno

Elige fecha y turno (A 06-14, B 14-22, C 22-06). Por puesto: piezas,
consumo, merma, autocontroles (y no conformes) e incidencias con su tiempo de
parada. "Descargar CSV" lo abre en Excel; "Imprimir / PDF" lo guarda en PDF.

## Órdenes, trazabilidad, calidad e incidencias

Debajo puedes crear y lanzar órdenes, ver la trazabilidad ISO 9001 de cada
orden (eventos inmutables), la bandeja de autocontroles y resolver
incidencias. El botón naranja de acción rápida lleva a cada sección.
