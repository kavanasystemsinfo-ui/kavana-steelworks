import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { SupervisorPage } from '../pages/SupervisorPage'
import { reiniciarOpciones } from '../panel/opciones'

// La opción de costes se lee una vez por carga: cada prueba empieza de cero
beforeEach(() => reiniciarOpciones())

/** Las herramientas (informe, órdenes, trazabilidad, incidencias) viven en Gestión. */
function renderPage(url = '/supervisor?vista=gestion') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <SupervisorPage />
    </MemoryRouter>,
  )
}

const renderTurno = () => renderPage('/supervisor')

const turnoBody = {
  turno: {
    codigo: 'B',
    inicio: '2026-10-27T19:00:00+00:00',
    fin: '2026-10-28T03:00:00+00:00',
    transcurrido_min: 240,
    duracion_min: 480,
  },
  piezas: 1180,
  plan_turno: 2000,
  plan_ahora: 1000,
  prevision_cierre: 1940,
  serie: [
    { minuto: 0, piezas: 0 },
    { minuto: 240, piezas: 1180 },
  ],
  eficiencia: { oee: 71, disponibilidad: 90, rendimiento: 82, calidad: 97.9, mas_resta: 'rendimiento' },
  paradas: {
    minutos: 46,
    numero: 3,
    mayor: { puesto: 'PUNZ-1', motivo: 'falta de material', descripcion: 'Bobina agotada', minutos: 23, abierta: true },
  },
  chatarra: { kg: 186, pct: 2.1 },
  objetivos: { oee: 75, disponibilidad: 90, rendimiento: 88, calidad: 95, chatarra_max_pct: 3 },
  puestos: [
    {
      code: 'PUNZ-1', name: 'Punzonado', grupo: 'Punzonado', estado: 'parado',
      motivo: 'Falta de material', minutos: 23, ritmo_nominal: 40,
      orden: { numero: '2602', producto: 'Lateral 900', piezas: 48, objetivo: 120 },
    },
    {
      code: 'CORTE-1', name: 'Corte', grupo: 'Corte', estado: 'en_marcha',
      motivo: null, minutos: 2, ritmo_nominal: 60,
      orden: { numero: '2603', producto: 'Larguero 2000', piezas: 310, objetivo: 400 },
    },
  ],
  ordenes: [
    {
      numero: '2602', producto: 'Lateral 900', puesto: 'PUNZ-1', piezas: 48, objetivo: 120,
      entrega: '2026-10-28T03:00:00+00:00', horas_faltan: 3.6, horas_quedan: 3.3, estado: 'retraso',
    },
  ],
  pendientes: [
    {
      urgencia: 'urgente', titulo: 'PUNZ-1 parado · falta de material', detalle: 'Bobina agotada',
      minutos: 23, accion: 'incidencia', ref: 'i1',
    },
    {
      urgencia: 'hoy', titulo: 'Orden 2602 va con retraso', detalle: 'Necesita 3,6 h.',
      minutos: null, accion: 'orden', ref: '2602',
    },
  ],
}

const plantaBody = {
  periodo: 'semana',
  desde: '2026-10-26T05:00:00+00:00',
  hasta: '2026-10-28T17:00:00+00:00',
  piezas: 38400,
  plan: 42000,
  eficiencia: { oee: 69, disponibilidad: 84, rendimiento: 86, calidad: 96 },
  paradas: {
    minutos: 445,
    numero: 24,
    media_min: 19,
    por_causa: [
      { causa: 'falta de material', minutos: 190, pct: 43 },
      { causa: 'avería', minutos: 120, pct: 27 },
    ],
  },
  chatarra_pct: 4,
  puestos: [
    { puesto: 'PUNZ-1', oee: 58, disponibilidad: 70, rendimiento: 85, calidad: 97 },
    { puesto: 'LINEA-1', oee: 81, disponibilidad: 95, rendimiento: 88, calidad: 97 },
  ],
  detalle_puestos: [
    {
      puesto: 'PUNZ-1',
      piezas: 9000,
      plan: 12000,
      eficiencia: { oee: 58, disponibilidad: 70, rendimiento: 85, calidad: 97 },
      paradas_min: 300,
      paradas_n: 10,
      kg_material: 800,
      chatarra_kg: 24,
      chatarra_pct: 3,
    },
  ],
  anterior: { eficiencia: 66, piezas: 35000, paradas_min: 505 },
  entregas: { total: 17, a_tiempo: 14, tarde: ['2591', '2594', '2598'] },
  tendencia: [
    { semana: 'S43', oee: 66 },
    { semana: 'S44', oee: 69 },
  ],
  ordenes: [],
  objetivos: { oee: 75, disponibilidad: 90, rendimiento: 88, calidad: 95, chatarra_max_pct: 3 },
}

const informeBody = {
  fecha: '2026-10-26',
  turno: 'A',
  inicio: '2026-10-26T06:00:00-05:00',
  fin: '2026-10-26T14:00:00-05:00',
  puestos: [
    {
      puesto: 'DOBL-1', ordenes: 1, piezas: 42, consumo_kg: 470.4, consumo_m: 0,
      merma_kg: 3.2, merma_coste: 4, autocontroles: 3, autocontroles_nok: 1,
      incidencias: 1, parada_min: 15,
    },
  ],
  totales: {
    piezas: 42, consumo_kg: 470.4, consumo_m: 0, merma_kg: 3.2, merma_coste: 4,
    autocontroles: 3, autocontroles_nok: 1, incidencias: 1, parada_min: 15,
  },
}

const ordersBody = [
  { id: 'OP1', numero: 'OP-DEMO-001', estado: 'active', cliente: 'Cliente demo', fecha_entrega: '2026-08-22T00:00:00Z' },
  { id: 'OP2', numero: 'OP-DEMO-002', estado: 'completed', cliente: 'Cliente demo', fecha_entrega: '2026-08-18T00:00:00Z' },
]

function fichaDe(
  numero: string,
  eventos: unknown[],
  resumen: Record<string, unknown> = {},
) {
  return {
    resumen: {
      numero,
      estado: 'active',
      cliente: null,
      piezas_producidas: 10,
      piezas_objetivo: 100,
      merma_kg: 0,
      kg_consumidos: 12.5,
      kg_por_bobina: [
        {
          stock_item_id: 's1',
          coil_id: 'COIL-DEMO-001',
          lote: 'L1',
          kg: 12.5,
          origen: 'alta_manual',
          pendiente_verificacion: true,
        },
      ],
      personas: [{ id: 'u1', nombre: 'Operario Demo', eventos: 3, piezas: 10 }],
      paradas_minutos: 0,
      paradas_abiertas: 0,
      incidencias: 0,
      eficiencia_media_uds_h: null,
      lineas: [],
      generada_en: '2026-08-15T10:00:00Z',
      ...resumen,
    },
    linea_tiempo: eventos,
    categorias: ['produccion', 'calidad', 'bobina', 'parada', 'incidencia', 'estado'],
  }
}

const traceOP1 = fichaDe('OP-DEMO-001', [
  {
    id: 'e3',
    timestamp: '2026-08-15T09:00:00Z',
    categoria: 'estado',
    titulo: 'Línea terminada',
    detalle: '',
    quien: 'Operario Demo',
    cantidad: null,
    unidad: null,
  },
  {
    id: 'e2',
    timestamp: '2026-08-15T08:01:00Z',
    categoria: 'produccion',
    titulo: 'Producción',
    detalle: 'bobina COIL-DEMO-001 · 12,5 kg consumidos',
    quien: 'Operario Demo',
    cantidad: 10,
    unidad: 'uds',
  },
  {
    id: 'e1',
    timestamp: '2026-08-15T08:00:00Z',
    categoria: 'bobina',
    titulo: 'Bobina COIL-DEMO-001 dada de alta a mano',
    detalle: 'en LINEA-1 · pendiente de verificar',
    quien: 'Operario Demo',
    cantidad: 500,
    unidad: 'kg',
  },
])

const traceOP2 = fichaDe(
  'OP-DEMO-002',
  [
    {
      id: 'f1',
      timestamp: '2026-08-15T14:00:00Z',
      categoria: 'estado',
      titulo: 'Cierre de turno',
      detalle: 'motivo: fin de jornada',
      quien: 'Operario Demo',
      cantidad: null,
      unidad: null,
    },
  ],
  { kg_por_bobina: [], personas: [] },
)

function stubApi(opts: { orders?: unknown; trace?: Record<string, unknown>; costes?: boolean } = {}) {
  const { orders = ordersBody, trace = {}, costes = true } = opts
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (url.includes('/supervisor/panel/opciones')) {
      return Promise.resolve({ ok: true, json: async () => ({ mostrar_costes: costes }) })
    }
    if (url.includes('/supervisor/planta')) {
      return Promise.resolve({ ok: true, json: async () => ({ ...plantaBody, periodo: url.split('periodo=')[1] }) })
    }
    if (url.includes('/supervisor/turno')) {
      return Promise.resolve({ ok: true, json: async () => turnoBody })
    }
    if (url.includes('/supervisor/panel/costes')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          periodo: 'mes',
          desde: '2026-10-01T05:00:00+00:00',
          hasta: '2026-11-01T05:00:00+00:00',
          coste_kg: {
            valor: 3.2,
            periodo_anterior: 3.5,
            objetivo: null,
            material: 2.4,
            transformacion: 0.8,
          },
          coste_total: 640,
          kg_total: 200,
          lineas_metros_excluidas: 0,
          ordenes_completadas: 2,
          desviacion: { pct: null, euros: null, ordenes_con_estimado: 0 },
          chatarra: { euros: 0, pct_material: 0 },
          por_familia: [
            {
              familia: 'sin_clasificar',
              etiqueta: 'Sin clasificar',
              kg: 200,
              material: 2.4,
              transformacion: 0.8,
              merma_pct: 0,
              ordenes: 2,
            },
          ],
          reparto: [{ clave: 'material', etiqueta: 'Material', euros: 640, pct: 100 }],
          coste_paradas: { total: 0, por_tipo: [], horas: 0 },
          tendencia: [{ semana: '2026-10-26', valor: 3.2 }],
          ordenes: [],
        }),
      })
    }
    if (url.includes('/supervisor/informe-turno')) {
      return Promise.resolve({ ok: true, json: async () => informeBody })
    }
    if (url.includes('/api/v1/orders')) {
      return Promise.resolve({ ok: true, json: async () => orders })
    }
    if (url.includes('/api/v1/trace/orders/')) {
      const partes = url.split('/')
      const id = partes[partes.length - 2]
      return Promise.resolve({
        ok: true,
        json: async () => trace[id ?? ''] ?? fichaDe('vacía', []),
      })
    }
    return Promise.resolve({ ok: false, status: 404, json: async () => ({}) })
  }))
}

describe('Panel de Supervisor (planta en un vistazo)', () => {
  it('Turno abre por defecto con la frase de estado y sus cuatro indicadores', async () => {
    stubApi()

    renderTurno()

    const estado = await screen.findByRole('region', { name: 'Estado' })
    expect(estado).toHaveTextContent('En ritmo, pero con 1 puesto parado')
    expect(estado).toHaveTextContent('cerrarás el turno en 1.940 de 2.000 piezas (97 %)')
    expect(estado).toHaveTextContent('PUNZ-1 lleva 23 min parado por falta de material')
    expect(screen.getByText('Piezas buenas').closest('article')).toHaveTextContent('1.180de 2.000')
    expect(screen.getByText('Eficiencia del turno').closest('article')).toHaveTextContent('Por debajo')
    expect(screen.getByText('Tiempo parado').closest('article')).toHaveTextContent('3 paradas')
    expect(screen.getByText('Chatarra').closest('article')).toHaveTextContent('Correcto')
    vi.unstubAllGlobals()
  })

  it('Turno muestra pendientes, puestos y órdenes', async () => {
    stubApi()

    renderTurno()

    const pendientes = await screen.findByRole('region', { name: 'Pendiente de actuar' })
    expect(pendientes).toHaveTextContent('Urgente')
    expect(pendientes).toHaveTextContent('PUNZ-1 parado · falta de material')
    expect(screen.getByRole('article', { name: 'PUNZ-1: Parado' })).toHaveTextContent('2602 · Lateral 900')
    expect(screen.getByRole('article', { name: 'CORTE-1: En marcha' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Órdenes en curso' })).toHaveTextContent('Retraso')
    vi.unstubAllGlobals()
  })

  it('un aviso de incidencia lleva a Gestión', async () => {
    stubApi()
    const user = userEvent.setup()

    renderTurno()
    await user.click(await screen.findByRole('button', { name: 'Ver incidencia' }))

    expect(screen.getByRole('link', { name: 'Gestión' })).toHaveAttribute('aria-current', 'page')
    vi.unstubAllGlobals()
  })

  it('sin ritmo en los puestos lo dice en vez de inventar un plan', async () => {
    stubApi()
    const original = { ...turnoBody }
    Object.assign(turnoBody, { plan_turno: null, plan_ahora: null, eficiencia: null })

    renderTurno()

    expect(await screen.findByText('Sin plan del turno')).toBeInTheDocument()
    expect(screen.getByText('Eficiencia del turno').closest('article')).toHaveTextContent('--')
    Object.assign(turnoBody, original)
    vi.unstubAllGlobals()
  })

  it('la vista de costes vive en su pestaña, con el €/kg del backend', async () => {
    stubApi()
    const user = userEvent.setup()

    renderTurno()

    // En la pestaña Turno no aparece la vista de costes
    expect(screen.getByRole('link', { name: 'Turno' })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByText('Cuánto cuesta producir')).not.toBeInTheDocument()

    await user.click(await screen.findByRole('link', { name: 'Costes' }))

    expect(screen.getByRole('link', { name: 'Costes' })).toHaveAttribute('aria-current', 'page')
    const titulo = await screen.findByText('Coste por kilo')
    expect(titulo.closest('article')).toHaveTextContent('3,20')
    expect(screen.getByRole('button', { name: 'Exportar informe' })).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('sin costes activados no hay pestaña Costes: el enlace cae en Material, con kilos y merma y sin euros', async () => {
    stubApi({ costes: false })

    renderPage('/supervisor?vista=costes')

    expect(await screen.findByText('Material y merma')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Material' })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByRole('link', { name: 'Costes' })).not.toBeInTheDocument()
    expect(await screen.findByText('Kilos transformados')).toBeInTheDocument()
    const cuerpo = document.body.textContent ?? ''
    expect(cuerpo).not.toContain('€')
    expect(cuerpo).not.toContain('Exportar informe')
    vi.unstubAllGlobals()
  })

  it('con costes activados aparecen las dos pestañas, Material y Costes', async () => {
    stubApi({ costes: true })

    renderTurno()

    expect(await screen.findByRole('link', { name: 'Costes' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Material' })).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('abre la vista pedida en la URL: Planta con su frase de estado', async () => {
    stubApi()

    render(
      <MemoryRouter initialEntries={['/supervisor?vista=planta']}>
        <SupervisorPage />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: 'Planta' })).toHaveAttribute('aria-current', 'page')
    const estado = await screen.findByRole('region', { name: 'Estado' })
    expect(estado).toHaveTextContent('Eficiencia 69 %, mejorando, pero 6 puntos por debajo del objetivo')
    expect(estado).toHaveTextContent('paradas por falta de material')
    expect(estado).toHaveTextContent('El cuello de botella es PUNZ-1 (58 %)')
    expect(screen.getByText('Entregas a tiempo').closest('article')).toHaveTextContent('Tarde: 2591, 2594, 2598')
    expect(screen.getByRole('region', { name: '¿Qué puesto frena la planta?' })).toHaveTextContent('PUNZ-1')
    vi.unstubAllGlobals()
  })

  it('Planta cambia de periodo con el selector', async () => {
    stubApi()
    const user = userEvent.setup()
    renderPage('/supervisor?vista=planta')

    await screen.findByRole('region', { name: 'Estado' })
    await user.click(screen.getByRole('button', { name: 'Hoy' }))

    expect(screen.getByRole('button', { name: 'Hoy' })).toHaveAttribute('aria-pressed', 'true')
    expect((await screen.findAllByText(/vs ayer/)).length).toBeGreaterThan(0)
    vi.unstubAllGlobals()
  })

  it('el botón Modo TV abre la pantalla de planta y Esc la cierra', async () => {
    stubApi()
    const user = userEvent.setup()

    renderTurno()
    await screen.findByRole('region', { name: 'Estado' })
    await user.click(screen.getByRole('button', { name: 'Modo TV' }))

    const tv = screen.getByRole('dialog', { name: 'Modo TV' })
    expect(tv).toHaveTextContent('Turno B')
    expect(tv).toHaveTextContent('1.180')
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'Modo TV' })).not.toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('muestra el informe de turno por puesto con totales', async () => {
    stubApi()

    renderPage()

    expect(await screen.findByText('DOBL-1')).toBeInTheDocument()
    expect(screen.getByText('(1 NOK)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Descargar CSV' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Imprimir / PDF' })).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('sin conexión lo dice, no inventa valores', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
    }))
    renderTurno()
    expect(await screen.findByText(/No se pudo cargar el turno/)).toBeInTheDocument()
    vi.unstubAllGlobals()
  })
})

describe('Trazabilidad ISO 9001 en el panel Supervisor', () => {
  it('carga la primera orden y muestra su ficha con el resumen y la línea de tiempo', async () => {
    stubApi({ trace: { OP1: traceOP1 } })

    renderPage()

    expect(await screen.findByText('OP-DEMO-001 · active')).toBeInTheDocument()
    const resumen = await screen.findByRole('region', { name: 'Resumen de la orden' })
    expect(resumen).toHaveTextContent('10 de 100')
    expect(resumen).toHaveTextContent('12,5 kg')
    expect(screen.getByRole('region', { name: 'Bobinas de la orden' })).toHaveTextContent(
      'Alta manual · sin verificar',
    )
    expect(screen.getByRole('region', { name: 'Personas que intervinieron' })).toHaveTextContent('Operario Demo')
    expect(screen.getByText('10 uds')).toBeInTheDocument()
    expect(screen.getByText(/bobina COIL-DEMO-001 · 12,5 kg consumidos/)).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('la línea de tiempo va de más reciente a más antiguo', async () => {
    stubApi({ trace: { OP1: traceOP1 } })

    renderPage()

    const lineaTiempo = await screen.findByRole('region', { name: 'Línea de tiempo' })
    const titulos = Array.from(lineaTiempo.querySelectorAll('li p:first-child')).map((p) => p.textContent)
    expect(titulos).toEqual([
      'Línea terminada',
      'Producción',
      'Bobina COIL-DEMO-001 dada de alta a mano',
    ])
    vi.unstubAllGlobals()
  })

  it('filtrar por categoría deja solo esos eventos y Todo los devuelve', async () => {
    stubApi({ trace: { OP1: traceOP1 } })

    renderPage()

    await screen.findByText('Línea terminada')
    fireEvent.click(screen.getByRole('button', { name: /Bobinas \(1\)/ }))
    expect(screen.getByText('Bobina COIL-DEMO-001 dada de alta a mano')).toBeInTheDocument()
    expect(screen.queryByText('Línea terminada')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Todo \(3\)/ }))
    expect(screen.getByText('Línea terminada')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('al cambiar de orden carga la ficha de la nueva orden', async () => {
    stubApi({ trace: { OP1: traceOP1, OP2: traceOP2 } })

    renderPage()

    await screen.findByText('Línea terminada')
    fireEvent.change(screen.getByLabelText('Orden'), { target: { value: 'OP2' } })

    expect(await screen.findByText('Cierre de turno')).toBeInTheDocument()
    expect(screen.queryByText('Línea terminada')).not.toBeInTheDocument()
    expect(screen.getByText(/fin de jornada/)).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('orden sin eventos muestra mensaje vacío, no inventa eventos', async () => {
    stubApi({ trace: { OP1: fichaDe('OP-DEMO-001', [], { kg_por_bobina: [], personas: [] }) } })

    renderPage()

    expect(await screen.findByText('Sin eventos de trazabilidad para esta orden.')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('sin órdenes muestra aviso y no intenta cargar traza', async () => {
    stubApi({ orders: [] })

    renderPage()

    expect(await screen.findByText('Sin órdenes disponibles.')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })
})

const incidenciaDemo = {
  id: 'INC-1',
  linea_id: 'LINEA-1',
  puesto: 'LINEA-1',
  descripcion: 'Atasco de bobina en la cizalla',
  tipo: 'maquina',
  estado: 'abierta',
  foto_data_url: null,
  resolucion_tipo: null,
  resolucion_descripcion: null,
  tiempo_parada_min: null,
  coste: null,
  created_at: '2026-08-15T10:00:00Z',
  operario: { id: 'u1', name: 'Operario Demo' },
  responsable: null,
  historial: [
    { estado: 'abierta', timestamp: '2026-08-15T10:00:00Z', comentario: 'Incidencia creada', usuario: 'Operario Demo' },
  ],
}

describe('Incidencias de planta en el Supervisor (spec 04 §3.3)', () => {
  function stubConIncidencias(
    fetchMock: (url: string, init?: RequestInit) => Promise<unknown>,
    costes = true,
  ) {
    const base = vi.fn((url: string, init?: RequestInit) => {
      if (url.includes('/supervisor/panel/opciones')) {
        return Promise.resolve({ ok: true, json: async () => ({ mostrar_costes: costes }) })
      }
      if (url.includes('/api/v1/incidencias')) return fetchMock(url, init)
      if (url.includes('/api/v1/orders')) {
        return Promise.resolve({ ok: true, json: async () => [] })
      }
      return Promise.resolve({ ok: false, status: 404, json: async () => ({}) })
    })
    vi.stubGlobal('fetch', base)
  }

  it('lista las incidencias abiertas con su estado', async () => {
    stubConIncidencias(
      vi.fn(() =>
        Promise.resolve({ ok: true, json: async () => ({ success: true, incidencias: [incidenciaDemo] }) }),
      ),
    )
    renderPage()

    expect(await screen.findByText('Incidencias de planta')).toBeInTheDocument()
    expect(screen.getByText('Atasco de bobina en la cizalla')).toBeInTheDocument()
    expect(screen.getByText('abierta')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /resolver/i })).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('sin costes activados la resolución de una incidencia no pide euros', async () => {
    const user = userEvent.setup()
    stubConIncidencias(
      vi.fn(() =>
        Promise.resolve({ ok: true, json: async () => ({ success: true, incidencias: [incidenciaDemo] }) }),
      ),
      false,
    )
    renderPage()

    await screen.findByText('Atasco de bobina en la cizalla')
    await user.click(screen.getByRole('button', { name: /resolver/i }))

    expect(screen.getByPlaceholderText(/minutos de parada/i)).toBeInTheDocument()
    expect(screen.queryByPlaceholderText(/coste.*€/i)).not.toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('resuelve una incidencia con cierre financiero vía PATCH', async () => {
    const user = userEvent.setup()
    stubConIncidencias(
      vi.fn((_url: string, init?: RequestInit) => {
        if (init?.method === 'PATCH') {
          const body = JSON.parse(init.body as string)
          expect(body.estado).toBe('cerrada')
          expect(body.resolucion_tipo).toBe('reparacion')
          expect(body.tiempo_parada_min).toBe(30)
          expect(body.coste).toBe(120)
          return Promise.resolve({
            ok: true,
            json: async () => ({ success: true, msg: 'Incidencia actualizada' }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, incidencias: [incidenciaDemo] }),
        })
      }),
    )
    renderPage()

    await screen.findByText('Atasco de bobina en la cizalla')
    await user.click(screen.getByRole('button', { name: /resolver/i }))
    await user.selectOptions(screen.getByLabelText(/estado final/i), 'cerrada')
    await user.selectOptions(screen.getByLabelText(/tipo de resolución/i), 'reparacion')
    await user.type(screen.getByPlaceholderText(/minutos de parada/i), '30')
    await user.type(screen.getByPlaceholderText(/coste.*€/i), '120')
    await user.click(screen.getByRole('button', { name: /confirmar resolución/i }))

    expect(await screen.findByText('Incidencia actualizada')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('muestra la evidencia fotográfica de la incidencia si existe', async () => {
    stubConIncidencias(
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            incidencias: [
              {
                ...incidenciaDemo,
                foto_data_url: 'data:image/png;base64,AAAA',
              },
            ],
          }),
        }),
      ),
    )
    renderPage()

    expect(
      await screen.findByAltText(/evidencia de atasco de bobina/i),
    ).toHaveAttribute('src', 'data:image/png;base64,AAAA')
    vi.unstubAllGlobals()
  })
})
