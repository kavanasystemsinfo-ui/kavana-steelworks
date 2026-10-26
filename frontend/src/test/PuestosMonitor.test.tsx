import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { PuestosMonitor } from '../components/PuestosMonitor'
import { haceCuanto } from '../lib/tiempo'
import { SupervisorPage } from '../pages/SupervisorPage'

const puestosBody = [
  {
    code: 'PERF-1',
    name: 'Perfiladora 1',
    color: null,
    estado: 'en_curso',
    orden: {
      id: 'OP1',
      numero: 'OP-DEMO-001',
      cliente: 'Cliente demo',
      linea_id: 'L1',
      piezas: 7,
      objetivo: 20,
      bobina: 'COIL-123',
    },
    ultima_actividad: { accion: 'produce', timestamp: new Date().toISOString(), operario: 'Ana' },
    incidencias_abiertas: [],
  },
  {
    code: 'PERF-2',
    name: 'Perfiladora 2',
    color: null,
    estado: 'incidencia',
    orden: null,
    ultima_actividad: null,
    incidencias_abiertas: [{ id: 'i1', tipo: 'maquina', descripcion: 'Atasco en la cizalla' }],
  },
]

function stubPuestos(body: unknown = puestosBody) {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (url.includes('/supervisor/puestos')) {
      return Promise.resolve({ ok: true, json: async () => body })
    }
    return Promise.resolve({ ok: false, status: 404, json: async () => ({}) })
  }))
}

afterEach(() => vi.unstubAllGlobals())

describe('Monitor de puestos', () => {
  it('pinta cada puesto con su estado, orden, bobina y progreso', async () => {
    stubPuestos()
    render(<PuestosMonitor />)

    expect(await screen.findByText('Perfiladora 1')).toBeInTheDocument()
    expect(screen.getByText('En curso')).toBeInTheDocument()
    expect(screen.getByText('OP-DEMO-001')).toBeInTheDocument()
    expect(screen.getByText('COIL-123')).toBeInTheDocument()
    expect(screen.getByText('7/20')).toBeInTheDocument()
    expect(screen.getByText(/Última actividad ahora · Ana/)).toBeInTheDocument()
  })

  it('la incidencia abierta se ve en rojo con su descripción', async () => {
    stubPuestos()
    render(<PuestosMonitor />)

    expect(await screen.findByText('Incidencia')).toBeInTheDocument()
    expect(screen.getByText(/Atasco en la cizalla/)).toBeInTheDocument()
    expect(screen.getByText('Sin orden asignada')).toBeInTheDocument()
    expect(screen.getByText('Sin actividad registrada')).toBeInTheDocument()
  })

  it('sin puestos indica dónde crearlos', async () => {
    stubPuestos([])
    render(<PuestosMonitor />)

    expect(await screen.findByText(/No hay puestos configurados/)).toBeInTheDocument()
  })

  it('haceCuanto formatea minutos y horas', () => {
    const ahora = new Date('2026-10-26T12:00:00Z')
    expect(haceCuanto('2026-10-26T11:55:00Z', ahora)).toBe('hace 5 min')
    expect(haceCuanto('2026-10-26T09:00:00Z', ahora)).toBe('hace 3 h')
  })

  it('el modo Andon abre el monitor a pantalla completa y Esc lo cierra', async () => {
    stubPuestos()
    render(
      <MemoryRouter>
        <SupervisorPage />
      </MemoryRouter>,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Acción rápida' }))
    const andonBtns = screen.getAllByRole('button', { name: 'Modo Andon' })
    await userEvent.click(andonBtns[andonBtns.length - 1])

    expect(screen.getByRole('dialog', { name: 'Andon de planta' })).toBeInTheDocument()
    expect(await screen.findByText('Perfiladora 1')).toBeInTheDocument()

    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'Andon de planta' })).not.toBeInTheDocument()
  })
})
