import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { FichaPuesto } from '../components/FichaPuesto'

const ficha = {
  puesto: { code: 'PERF-1', name: 'Perfiladora 1', color: null, ritmo_nominal: 100 },
  periodo: 'hoy',
  desde: '2026-10-27T23:00:00+00:00',
  hasta: '2026-10-28T11:00:00+00:00',
  ahora: {
    estado: 'en_curso',
    orden: { numero: 'OP-7', cliente: 'ACME', piezas: 120, objetivo: 400, bobina: 'B-2' },
    ultima_actividad: { accion: 'produce', timestamp: '2026-10-28T10:30:00+00:00', operario: 'Ana' },
    incidencias_abiertas: [],
  },
  piezas: 320,
  plan: 500,
  eficiencia: { oee: 62.5, disponibilidad: 80, rendimiento: 80, calidad: 98 },
  paradas: {
    minutos: 60,
    numero: 1,
    por_causa: [{ causa: 'avería', minutos: 60, pct: 100 }],
  },
  material: { kg_consumidos: 98, chatarra_kg: 2, chatarra_pct: 2 },
  sesiones: [
    {
      operario: 'Ana',
      orden: 'OP-7',
      linea: 1,
      inicio: '2026-10-28T09:00:00+00:00',
      fin: '2026-10-28T10:30:00+00:00',
      minutos: 90,
      piezas: 80,
      chatarra_kg: 3,
      kg_material: 20,
      bobinas: ['B-1', 'B-2'],
      eventos: [
        { hora: '2026-10-28T09:00:00+00:00', accion: 'produce', texto: 'Produce', cantidad: 40, bobina: 'B-1', kg_material: 10, nota: null },
        { hora: '2026-10-28T10:30:00+00:00', accion: 'scrap', texto: 'Chatarra', cantidad: 3, bobina: null, kg_material: null, nota: null },
      ],
    },
    {
      operario: 'Luis',
      orden: 'OP-7',
      linea: 1,
      inicio: '2026-10-28T07:00:00+00:00',
      fin: '2026-10-28T07:30:00+00:00',
      minutos: 30,
      piezas: 240,
      chatarra_kg: 0,
      kg_material: 78,
      bobinas: [],
      eventos: [],
    },
  ],
}

afterEach(() => vi.unstubAllGlobals())

describe('Ficha de puesto', () => {
  it('muestra estado, cifras y sesiones sin euros', async () => {
    const mock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => ficha }))
    vi.stubGlobal('fetch', mock)

    const { container } = render(<FichaPuesto codigo="PERF-1" onVolver={() => {}} />)

    expect(await screen.findByText('PERF-1 · En marcha')).toBeInTheDocument()
    expect(String(mock.mock.calls[0][0])).toContain('/supervisor/puestos/PERF-1/ficha?periodo=hoy')
    expect(screen.getByText('320')).toBeInTheDocument()
    expect(screen.getByText('de 500')).toBeInTheDocument()
    expect(screen.getByText('63 %')).toBeInTheDocument()
    expect(screen.getByText('2 sesiones')).toBeInTheDocument()
    expect(screen.getByText('B-1, B-2')).toBeInTheDocument()
    expect(container.textContent).not.toContain('€')
  })

  it('despliega los registros de una sesión con hora, cantidad y bobina', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: async () => ficha })))
    render(<FichaPuesto codigo="PERF-1" onVolver={() => {}} />)
    await screen.findByText('2 sesiones')

    expect(screen.queryByRole('table')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: /Ana/ }))

    const tabla = screen.getByRole('table', { name: /sesión de Ana/ })
    expect(within(tabla).getByText('40 piezas')).toBeInTheDocument()
    expect(within(tabla).getByText('3 kg')).toBeInTheDocument()
    expect(within(tabla).getByText('B-1')).toBeInTheDocument()
  })

  it('pide otra vez la ficha al cambiar de periodo y avisa del error', async () => {
    const mock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ficha })
      .mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({ detail: 'Caído' }) })
    vi.stubGlobal('fetch', mock)
    render(<FichaPuesto codigo="PERF-1" onVolver={() => {}} />)
    await screen.findByText('2 sesiones')

    await userEvent.click(screen.getByRole('button', { name: 'Esta semana' }))

    await waitFor(() => expect(screen.getByText(/No se pudo cargar la ficha: Caído/)).toBeInTheDocument())
    expect(String(mock.mock.calls[1][0])).toContain('periodo=semana')
  })

  it('sin sesiones lo dice', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: async () => ({ ...ficha, sesiones: [], ahora: null, eficiencia: null, plan: null, piezas: 0 }),
        }),
      ),
    )
    render(<FichaPuesto codigo="PERF-1" onVolver={() => {}} />)
    expect(await screen.findByText(/Nadie ha registrado trabajo/)).toBeInTheDocument()
    expect(screen.getByText('PERF-1 · Sin orden')).toBeInTheDocument()
  })
})
