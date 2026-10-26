# ADR-021: Adopción selectiva del legacy (kavanasystems v2) sin volver a sobredimensionar

Estado: Aceptado
Fecha: 2026-10-26
Autor: Jorge Adán (KAVANA Systems)

## Contexto

El legacy (`kavanasystems`, v2, MongoDB) tenía unas 45 pantallas y gustaba
por cómo estaba pensado: centro de mando de "un vistazo", monitor de puestos,
coste real por orden, Andon, informes, guías por rol. Pero en la reunión con
un lean manager quedó claro que era difícil de entender. Y al recorrerlo
aparecieron números que no cuadraban entre pantallas: "6 materiales bajo
mínimos" en el panel frente a 0 en Stock, un OEE del 130 %, órdenes activas
con 0/0 piezas y un "coste real" que cambiaba sin actividad.

Steelworks ya tenía el núcleo de dominio (FIFO, reconciliación, OEE,
trazabilidad, calidad), pero con dos huecos de coste:

- La mano de obra estaba fijada a 0 en `record_production`, aunque el
  puesto tenía `hourly_cost`.
- `Order.estimado_total_cost` no se calculaba en ningún flujo, y la semilla
  escribía costes a mano en la cabecera de la orden (no en sus líneas).

## Decisión

Matriz de adopción: se adopta lo que responde a una pregunta del usuario de
planta con un dato que el sistema ya registra. Cada rol mantiene una
pantalla principal.

1. **Frontera MES/ERP (ISA-95).** El MES valora la producción con dos tablas
   de precios que ya existen (€/kg del material, €/h del puesto, con el coste
   global de la empresa como respaldo). No factura, no lleva contabilidad ni
   compras. Por eso no hay "coste de reposición".
2. **Una sola fuente para el coste.** Todo sale de las líneas de orden
   (`services/costes.py`): las 4 tarjetas, la tabla de coste por orden y los
   KPIs. Así siempre cuadran entre sí.
3. **Desviación solo en órdenes completadas.** En curso, la bobina está
   cargada entera por el cobro bulk (spec 01 §3.6) y se reembolsa al
   cerrarla; comparar antes sería engañoso. Sin estimado, se muestra "sin
   estimado", nunca 0.
4. **Monitor de puestos y Andon.** Andon = el mismo monitor a pantalla
   completa, sin datos nuevos. Estado derivado de los datos (incidencia
   abierta > en curso > parado > pendiente > libre) con la última actividad
   al lado.
5. **Informe de turno** sobre `ProductionLog` (eventos inmutables) por fecha
   y turno A/B/C, exportable a CSV e imprimible. Es el único "por turno" real;
   las tarjetas dicen "acumulado".
6. **Alertas** con la misma regla que su pantalla de detalle.
7. **Simulador de demo** con los servicios reales (`link_coil` +
   `record_production`), marcado en la trazabilidad, más la etiqueta
   "DATOS DE DEMO" en la interfaz (claim `demo` en el JWT).
8. **Guías por rol** cortas en `docs/guias/`, dentro del corpus del asistente
   RAG, en lugar de manuales largos.

Pospuesto o descartado:

- Mantenimiento preventivo: `accumulated_hours` no se incrementa en ningún
  flujo; mostrarlo sería inventar. Va primero a manufacturing (genérico).
- Asistente sobre datos en tiempo real, utillaje, planes comerciales en
  código, doble interfaz clásico/PC, banners decorativos, academia y
  landings: fuera del producto.

## Consecuencias

- La semilla de la demo pasa a sembrar el objetivo de material en kg (antes,
  piezas) y a derivar los costes históricos de consumos y tiempos.
  `reparar_costes_demo` corrige de forma idempotente las siembras ya
  desplegadas, y solo en el tenant demo.
- Corregido de paso: `log_event` perdía en silencio los eventos con un UUID
  en el metadata (p. ej. `manufacturingModel`).
- **Una bobina, un solo sitio** (decisión Jorge 2026-10-26). `link_coil`
  permitía vincular la misma bobina a dos líneas y cobraba la bobina entera
  en cada una, duplicando el coste de material. Ahora rechaza una bobina
  activa en otra línea (de otra máquina o de la misma) e indica en qué orden
  y puesto está. Para moverla se desvincula (reembolso de lo no consumido,
  ADR-019) y se vincula. La bobina se bloquea con FOR UPDATE para que dos
  vinculaciones simultáneas no pasen a la vez. De paso, `link_coil`
  comprueba que la bobina y la orden son del mismo tenant.
- **Simulador dentro del backend** (Jorge: "lo que sea más estable"). Un
  bucle asyncio arrancado en el lifespan de FastAPI, activado con
  `STEELWORKS_SIMULADOR_MINUTOS` (5 en `fly.toml`, 0 por defecto). Solo
  actúa en horario laboral de planta (lunes a viernes, turnos A y B) y
  mientras la máquina de Fly está despierta, es decir, cuando alguien usa la
  demo. Se descartó GitHub Actions cron (retrasos, desactivación tras 60
  días sin actividad, token expuesto) y la máquina programada de Fly
  (imagen desfasada en cada despliegue). Asume una sola instancia, igual que
  el resto de la demo (ADR-016).
- Para que la demo no se agote, el simulador repone por los flujos reales:
  órdenes nuevas copiando completadas (con la secuencia real), recepción de
  bobinas (`receive_coil`, con kardex), fin de bobina con radio 0 al
  agotarse y cierre con faltante de un paso que ya no puede recibir piezas.
- La semilla tenía órdenes imposibles de terminar (un paso pedía más piezas
  que el anterior). Se corrige para bases nuevas; en la demo ya desplegada,
  el simulador las cierra con faltante.
