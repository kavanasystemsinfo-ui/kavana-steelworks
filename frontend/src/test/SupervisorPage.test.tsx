import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { SupervisorPage } from '../pages/SupervisorPage'

function renderPage() {
  return render(
    <MemoryRouter>
      <SupervisorPage />
    </MemoryRouter>,
  )
}

const oeeBody = {
  availability: 50,
  performance: 50,
  quality: 95,
  oee: 23.75,
  raw: {
    total_pieces: 10,
    total_objetivo: 20,
    total_tiempo_min: 240,
    scrap_kg: 5,
    material_kg: 100,
  },
}

const kpisBody = {
  orders_total: 1,
  orders_active: 1,
  orders_completed: 0,
  estimated_cost: 1000,
  real_cost: 900,
  cost_variance: -100,
  cost_efficiency: 111.1,
  material_variance: 0,
  material_efficiency: 0,
  scrap_rate: 5,
}

const ordersBody = [
  { id: 'OP1', numero: 'OP-DEMO-001', estado: 'active', cliente: 'Cliente demo', fecha_entrega: '2026-08-22T00:00:00Z' },
  { id: 'OP2', numero: 'OP-DEMO-002', estado: 'completed', cliente: 'Cliente demo', fecha_entrega: '2026-08-18T00:00:00Z' },
]

const traceOP1 = [
  {
    id: 'e1',
    action: 'start',
    quantity: '0.000',
    timestamp: '2026-08-15T08:00:00Z',
    metadata: {},
    shift: null,
    operator: { id: 'u1', name: 'Operario Demo' },
  },
  {
    id: 'e2',
    action: 'produce',
    quantity: '10.000',
    timestamp: '2026-08-15T08:01:00Z',
    metadata: { consumedAmount: '12.5', activeCoilCode: 'COIL-DEMO-001' },
    shift: null,
    operator: { id: 'u1', name: 'Operario Demo' },
  },
  {
    id: 'e3',
    action: 'finish',
    quantity: '0.000',
    timestamp: '2026-08-15T09:00:00Z',
    metadata: {},
    shift: null,
    operator: { id: 'u1', name: 'Operario Demo' },
  },
]

const traceOP2 = [
  {
    id: 'f1',
    action: 'close_shift',
    quantity: '0.000',
    timestamp: '2026-08-15T14:00:00Z',
    metadata: { reason: 'fin de jornada' },
    shift: 'afternoon',
    operator: { id: 'u1', name: 'Operario Demo' },
  },
]

function stubApi(opts: { orders?: unknown; trace?: Record<string, unknown> } = {}) {
  const { orders = ordersBody, trace = {} } = opts
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (url.includes('/supervisor/oee')) {
      return Promise.resolve({ ok: true, json: async () => oeeBody })
    }
    if (url.includes('/supervisor/kpis')) {
      return Promise.resolve({ ok: true, json: async () => kpisBody })
    }
    if (url.includes('/api/v1/orders')) {
      return Promise.resolve({ ok: true, json: async () => orders })
    }
    if (url.includes('/api/v1/trace/orders/')) {
      const id = url.split('/').pop()
      return Promise.resolve({ ok: true, json: async () => trace[id ?? ''] ?? [] })
    }
    return Promise.resolve({ ok: false, status: 404, json: async () => ({}) })
  }))
}

describe('Panel de Supervisor (planta en un vistazo)', () => {
  it('muestra OEE y KPIs cargados desde la API', async () => {
    stubApi()

    renderPage()

    expect(await screen.findByText('23,75')).toBeInTheDocument()
    expect(screen.getAllByText('50').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('95')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument() // merma kg
    expect(screen.getByText('111,1 %')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('sin datos muestra marcadores vacíos, no inventa valores', () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
    }))
    renderPage()
    expect(screen.getByText('Turno actual')).toBeInTheDocument()
    expect(screen.getAllByText('--').length).toBeGreaterThan(0)
    vi.unstubAllGlobals()
  })
})

describe('Trazabilidad ISO 9001 en el panel Supervisor', () => {
  it('carga la primera orden y muestra su serie de eventos', async () => {
    stubApi({ trace: { OP1: traceOP1 } })

    renderPage()

    expect(await screen.findByText('OP-DEMO-001 · active')).toBeInTheDocument()
    expect(await screen.findByText('Inicio de sesión')).toBeInTheDocument()
    expect(screen.getByText('Producción')).toBeInTheDocument()
    expect(screen.getByText('10.000 uds')).toBeInTheDocument()
    expect(screen.getByText(/COIL-DEMO-001/)).toBeInTheDocument()
    expect(screen.getByText('Fin de bobina')).toBeInTheDocument()
    expect(screen.getAllByText(/Operario Demo/).length).toBeGreaterThanOrEqual(3)
    vi.unstubAllGlobals()
  })

  it('al cambiar de orden carga la traza de la nueva orden', async () => {
    stubApi({ trace: { OP1: traceOP1, OP2: traceOP2 } })

    renderPage()

    await screen.findByText('Producción')
    fireEvent.change(screen.getByLabelText('Orden'), { target: { value: 'OP2' } })

    expect(await screen.findByText('Cierre de turno')).toBeInTheDocument()
    expect(screen.queryByText('Producción')).not.toBeInTheDocument()
    expect(screen.getByText(/fin de jornada/)).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('orden sin eventos muestra mensaje vacío, no inventa eventos', async () => {
    stubApi({ trace: { OP1: [] } })

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
  ) {
    const base = vi.fn((url: string, init?: RequestInit) => {
      if (url.includes('/api/v1/incidencias')) return fetchMock(url, init)
      if (url.includes('/supervisor/oee')) {
        return Promise.resolve({ ok: true, json: async () => oeeBody })
      }
      if (url.includes('/supervisor/kpis')) {
        return Promise.resolve({ ok: true, json: async () => kpisBody })
      }
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
})
