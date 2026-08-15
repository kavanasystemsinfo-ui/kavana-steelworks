import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { OperarioPage } from '../pages/OperarioPage'
import { MockWebSocket } from './mockWebSocket'

// QA del fallback REST de OperarioPage (ADR-014): cuando el WebSocket nunca
// conecta, el panel cae al polling REST; cuando el WS por fin conecta, el
// polling REST debe DETENERSE (de lo contrario se duplican fuentes y
// requests vacíos cada 5 s, justo lo que el ADR quería eliminar).

const tokenDemo = (() => {
  const b64 = (s: string) =>
    btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  const payload = JSON.stringify({
    sub: 'u1',
    tenant_id: 'T1',
    role: 'operator',
    exp: 9999999999,
  })
  return `x.${b64(payload)}.sig`
})()

const eventoRest = {
  id: 'e2',
  tipo: 'stock_deficit',
  data: { kg: 12 },
  timestamp: '2026-08-15T10:05:00Z',
}

const eventoWs = {
  id: 'e1',
  tipo: 'consumo_fifo',
  data: { kg: 30 },
  timestamp: '2026-08-15T10:00:00Z',
}

const modeloDemo = {
  id: 'M1',
  code: 'PERFIL-DEMO-001',
  name: 'Perfil decapado 1.2x1220',
  material_code: 'ACERO-DC01',
  quality_plan: [],
}

function stubFetch() {
  return vi.fn((url: string) => {
    if (url.includes('/api/v1/quality/models')) {
      return Promise.resolve({ ok: true, json: async () => [modeloDemo] })
    }
    if (url.includes('/api/v1/orders')) {
      return Promise.resolve({
        ok: true,
        json: async () => [
          {
            id: 'OP1',
            numero: 'OP-DEMO-001',
            estado: 'active',
            cliente: null,
            fecha_entrega: null,
            workstation_id: 'LINEA-1',
          },
        ],
      })
    }
    if (url.includes('/api/v1/events/')) {
      return Promise.resolve({ ok: true, json: async () => ({ events: [eventoRest] }) })
    }
    return Promise.resolve({ ok: true, json: async () => ({}) })
  })
}

describe('QA fallback REST de OperarioPage (ADR-014)', () => {
  beforeEach(() => {
    sessionStorage.clear()
    sessionStorage.setItem('kavana_token', tokenDemo)
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
    sessionStorage.clear()
  })

  it('qa: el polling REST arranca si el WS falla y se detiene cuando el WS conecta', async () => {
    vi.useFakeTimers()
    const fetchMock = stubFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(
      <MemoryRouter>
        <OperarioPage />
      </MemoryRouter>,
    )
    const restCalls = () =>
      fetchMock.mock.calls
        .map((c) => String(c[0]))
        .filter((u) => u.includes('/api/v1/events/'))

    // el handshake del WS falla (Vercel sin reenvío de upgrades): la página
    // cae al fallback REST
    await act(async () => {
      MockWebSocket.instances.at(-1)!.cerrarServidor()
    })
    await act(async () => {}) // flush de microtasks de las promesas de fetch
    expect(screen.getByText('Reconectando...')).toBeInTheDocument()
    expect(screen.getByText('stock_deficit')).toBeInTheDocument()
    expect(restCalls().length).toBeGreaterThanOrEqual(1)

    // el backoff reconecta (jitter real: 700-1300 ms) y esta vez responde
    act(() => vi.advanceTimersByTime(2000))
    const wsNuevo = MockWebSocket.instances.at(-1)!
    act(() => {
      wsNuevo.mensaje({ type: 'hello', tenant_id: 'T1', queued: 1 })
      wsNuevo.mensaje({ type: 'events', events: [eventoWs] })
    })
    expect(screen.getByText('En vivo')).toBeInTheDocument()
    expect(screen.getByText('consumo_fifo')).toBeInTheDocument()

    // el polling REST queda cancelado: pasan 15 s sin llamadas nuevas
    const antes = restCalls().length
    act(() => vi.advanceTimersByTime(15000))
    expect(restCalls().length).toBe(antes)
  })
})
