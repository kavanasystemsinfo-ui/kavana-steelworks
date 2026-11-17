import type { TourStep } from '../components/Tour'
import type { Role } from './roles'

type Acciones = {
  /** Va a otra ruta (por ejemplo, '/supervisor?vista=planta'). */
  ir: (ruta: string) => void
}

const A = (nombre: string) => `[data-tour-step="${nombre}"]`

/** Recorrido con el que se abre cada rol la primera vez. */
export const TOUR_INICIAL: Record<Role, string> = {
  operator: 'operario-puesto',
  supervisor: 'turno',
  materials: 'materias',
  admin: 'admin',
}

/** Recorrido del operario según la pantalla en la que está (lo dice la URL: ?ws=puesto&order=orden). */
export function tourDelOperario(params: URLSearchParams): string {
  if (!params.get('ws')) return 'operario-puesto'
  if (!params.get('order')) return 'operario-cola'
  return 'operario-bobina'
}

/** Recorrido de cada pestaña del panel del supervisor. */
export const TOUR_DE_VISTA: Record<string, string> = {
  turno: 'turno',
  planta: 'planta',
  material: 'material',
  gestion: 'gestion',
}

/**
 * Los recorridos de Steelworks: uno por rol y, en el supervisor, uno por pestaña
 * encadenados. Las anclas son los `data-tour-step` de las pantallas, los `aria-label`
 * de sus secciones y algún id que ya existía.
 */
export function crearTours({ ir }: Acciones): Record<string, TourStep[]> {
  const vista = (v: string) => () => ir(`/supervisor?vista=${v}`)
  return {
    'operario-puesto': [
      {
        id: 'op-guia',
        anchor: A('op-guia'),
        title: 'Tres pasos y a producir',
        content:
          'El operario trabaja en tres pantallas sencillas: elegir el puesto, elegir la orden y vincular la bobina.\nEs una pantalla con pocos botones y muy grandes, para usarla de pie junto a la máquina.',
      },
      {
        id: 'op-puestos',
        anchor: A('op-puestos'),
        title: 'Elige tu puesto',
        content:
          'Cada tarjeta es una máquina de la planta. Pulsa la tuya para pasar a la cola de órdenes.\nCuando quieras la ayuda de la siguiente pantalla, pulsa «Tour» arriba.',
      },
    ],
    'operario-cola': [
      {
        id: 'op-cola',
        anchor: A('op-cola'),
        title: 'La cola de órdenes',
        content: 'Las órdenes pendientes de este puesto, con su número, su estado y su cliente. Pulsa la que vas a fabricar.',
      },
      {
        id: 'op-volver',
        anchor: A('op-volver'),
        title: '¿Te has equivocado de puesto?',
        content: 'Con este botón vuelves a la lista de puestos.\nCuando elijas orden, pulsa «Tour» arriba para ver la pantalla de trabajo.',
      },
    ],
    'operario-bobina': [
      {
        id: 'op-paso',
        anchor: A('op-paso'),
        title: 'Siempre sabes qué toca',
        content:
          'Arriba pone el paso actual: vincular bobina, producir piezas o, si hay una avería, máquina parada.',
      },
      {
        id: 'op-orden',
        anchor: [A('op-orden'), A('op-puesto')],
        title: 'Tu orden y tu puesto',
        content: 'Cambia de orden o de puesto desde aquí. Si no eliges ninguno, trabaja en el puesto por defecto.',
      },
      {
        id: 'op-ficha',
        anchor: '[aria-label="Orden en curso"]',
        title: 'La orden en curso',
        content: 'El cliente, el modelo, el material, el largo de pieza, el ritmo previsto y cuántas piezas lleva hechas, de un vistazo.',
      },
      {
        id: 'op-bobina',
        anchor: A('op-bobina'),
        title: 'Vincula la bobina',
        content:
          'Escanea la etiqueta o escribe el código de la bobina que montas en la máquina. Hasta entonces no se puede registrar producción.\nSi la bobina no está dada de alta, puedes registrarla a mano justo debajo.',
      },
      {
        id: 'op-disponibles',
        anchor: A('op-disponibles'),
        title: 'Las bobinas disponibles',
        content: 'Las bobinas que valen para esta orden. Toca una para vincularla sin escribir nada; las que ya están en tu puesto salen primero.',
      },
      {
        id: 'op-cerrar',
        anchor: A('op-cerrar'),
        title: 'Cerrar la jornada',
        content: 'Al acabar el turno se cierra desde aquí. Si te queda una bobina sin medir, te pide medirla antes de salir.',
      },
      {
        id: 'op-alertas',
        anchor: A('op-alertas'),
        title: 'Avisos de almacén',
        content: 'Las alertas de almacén llegan en tiempo real, sin tener que preguntar a nadie.',
      },
      {
        id: 'op-fin',
        title: 'Y después, a producir',
        content:
          'Con una orden y una bobina vinculada, esta pantalla pasa a «Producir piezas»: un teclado numérico para registrar lo fabricado y un botón para parar la máquina si hay una avería.\nPara ver otro rol, pulsa Salir arriba y elige Supervisor, Materias Primas o Admin: cada uno tiene su propio tour.',
      },
    ],

    turno: [
      {
        id: 'sv-pestanas',
        anchor: '[aria-label="Vistas del panel"]',
        title: 'Una pestaña por pregunta',
        content:
          'Turno: ¿llego al plan?\nPlanta: ¿cómo va la planta esta semana?\nMaterial: ¿cuánta merma hay y qué restos de bobina quedan?\nGestión: informe de turno, órdenes, trazabilidad, calidad e incidencias.',
        action: vista('turno'),
      },
      {
        id: 'sv-kpis',
        anchor: A('sv-kpis'),
        title: 'Las cifras del turno',
        content:
          'Piezas buenas, eficiencia, tiempo parado y chatarra, cada una comparada con su plan u objetivo y con una etiqueta de color que dice cómo va.',
      },
      {
        id: 'sv-plan',
        anchor: '[aria-label="¿Llego al plan del turno?"]',
        title: '¿Llego al plan?',
        content: 'Las piezas buenas acumuladas frente al plan, con la previsión de cierre del turno.',
      },
      {
        id: 'sv-pendiente',
        anchor: '[aria-label="Pendiente de actuar"]',
        title: 'Lo que pide atención',
        content: 'Los avisos, ordenados por urgencia. Cada uno lleva un botón para ir directo al puesto afectado.',
      },
      {
        id: 'sv-puestos',
        anchor: '[aria-label="Puestos ahora"]',
        title: 'Los puestos, ahora',
        content: 'Una tarjeta por puesto con su estado y el avance de su orden. «Ver la ficha» abre el detalle.',
        siguiente: 'planta',
      },
    ],
    planta: [
      {
        id: 'sv-oee',
        anchor: '[aria-label^="¿De dónde sale"]',
        title: '¿De dónde sale la eficiencia?',
        content:
          'Eficiencia = tiempo en marcha × velocidad × piezas buenas. La barra más corta frente a su objetivo es la que más resta.',
        action: vista('planta'),
      },
      {
        id: 'sv-paradas',
        anchor: '[aria-label="¿Por qué paramos?"]',
        title: 'Por qué se para la planta',
        content: 'El tiempo parado en el periodo, repartido por causa.',
      },
      {
        id: 'sv-cuello',
        anchor: '[aria-label="¿Qué puesto frena la planta?"]',
        title: 'El cuello de botella',
        content: 'La eficiencia de cada puesto frente al objetivo. Pulsa uno para ver su ficha.',
      },
      {
        id: 'sv-entregas',
        anchor: '[aria-label="¿Qué entregas están en peligro?"]',
        title: 'Las entregas en peligro',
        content: 'Las horas de trabajo que le faltan a cada orden frente a las horas que quedan hasta su entrega.',
        siguiente: 'material',
      },
    ],
    material: [
      {
        id: 'sv-material-uso',
        anchor: '[aria-label="¿Qué material se ha usado?"]',
        title: 'Material y merma',
        content: 'Los kilos y la merma de cada familia de material en las órdenes cerradas del periodo.',
        action: vista('material'),
      },
      {
        id: 'sv-picos',
        anchor: '[aria-label="Picos acumulados"]',
        title: 'Los picos',
        content: 'Los restos de bobina que quedan por material. Los operarios los ven primero al elegir bobina, para gastarlos antes.',
        siguiente: 'gestion',
      },
    ],
    gestion: [
      {
        id: 'sv-informe',
        anchor: '#informe',
        title: 'Informe de turno',
        content: 'Piezas, consumo, merma, autocontroles e incidencias de cada puesto. Se descarga en CSV o se imprime en PDF.',
        action: vista('gestion'),
      },
      {
        id: 'sv-ordenes',
        anchor: '#ordenes',
        title: 'Gestión de órdenes',
        content: 'Crea, lanza, completa o descarta órdenes desde aquí.',
      },
      {
        id: 'sv-trazabilidad',
        anchor: A('sv-trazabilidad'),
        title: 'Trazabilidad ISO 9001',
        content: 'Elige una orden y verás su historial de eventos, que no se pueden modificar.',
      },
      {
        id: 'sv-incidencias',
        anchor: '#incidencias',
        title: 'Incidencias de planta',
        content: 'Las incidencias reportadas, para revisarlas y resolverlas.',
      },
      {
        id: 'sv-fin',
        title: 'Hasta aquí el supervisor',
        content:
          'Puedes repetir este recorrido en cada pestaña con el botón «Tour» de arriba.\nPara ver otro rol, pulsa Salir y elige Operario, Materias Primas o Admin.',
      },
    ],

    materias: [
      {
        id: 'mp-cab',
        anchor: A('mp-cab'),
        title: 'Recepción de material',
        content: 'Aquí entra la bobina que llega a la planta. Es el primer eslabón de la trazabilidad.',
      },
      {
        id: 'mp-form',
        anchor: A('mp-form'),
        title: 'Registrar una bobina',
        content:
          'Elige el material y apunta lote o etiqueta, peso, ancho, espesor y ubicación. La bobina queda registrada en el almacén.\nPara ver otro rol, pulsa Salir arriba y elige Operario, Supervisor o Admin.',
      },
    ],

    admin: [
      {
        id: 'ad-tabs',
        anchor: A('ad-tabs'),
        title: 'La configuración de la planta',
        content: 'Empresa, usuarios, secuencias, puestos, productos y roles: lo que se configura una vez y luego va solo.',
      },
      {
        id: 'ad-empresa',
        anchor: `${A('ad-tabs')} ~ *`,
        title: 'Empresa',
        content:
          'Nombre, color y nombre mostrado de la empresa, y el coste global de la mano de obra.\nEl interruptor «Mostrar costes en euros» decide si el panel del supervisor enseña euros o solo kilos y merma.',
      },
      {
        id: 'ad-fin',
        title: 'Lo demás, en sus pestañas',
        content:
          'Cada pestaña de arriba abre su configuración. Es una demo con datos ficticios: puedes mirar sin miedo.\nPara ver otro rol, pulsa Salir y elige Operario, Supervisor o Materias Primas.',
      },
    ],
  }
}
