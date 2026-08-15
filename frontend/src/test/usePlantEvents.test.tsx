import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePlantEvents } from '../hooks/usePlantEvents'
import { MockWebSocket } from './mockWebSocket'

function stubWebSocket() {
  MockWebSocket.instances = []
  vi.stubGlobal('WebSocket', MockWebSocket)
}

function evento(id: string, tipo = 'consumo_fifo', data: Record<string, unknown> = { kg: 30 }) {
  return { id, tipo, data, timestamp: '2026-08-15T10:00:00Z' }
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('usePlantEvents (ADR-014)', () => {
  it('empieza desconectado y conectar abre un WS con tenant y subprotocolo kavana.v1', () => {
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    expect(result.current.estado).toBe('desconectado')

    act(() => result.current.conectar('T1'))

    expect(MockWebSocket.instances).toHaveLength(1)
    const ws = MockWebSocket.instances[0]
    expect(ws.url).toContain('/api/v1/ws/events?tenant_id=T1')
    expect(ws.url).toMatch(/^ws:\/\//)
    expect(ws.protocols).toBe('kavana.v1')
    expect(result.current.estado).toBe('conectando')
  })

  it('recibe el lote events y lo expone como eventos', () => {
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    const ws = MockWebSocket.instances[0]

    act(() => ws.mensaje({ type: 'hello', tenant_id: 'T1', queued: 2 }))
    expect(result.current.estado).toBe('conectado')

    act(() =>
      ws.mensaje({
        type: 'events',
        events: [evento('e1'), evento('e2', 'stock_deficit')],
      }),
    )
    expect(result.current.eventos).toHaveLength(2)
    expect(result.current.eventos[0].tipo).toBe('consumo_fifo')
    expect(result.current.ultimoEvento?.tipo).toBe('stock_deficit')
  })

  it('hace append con un event individual y respeta maxEventos', () => {
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents({ maxEventos: 2 }))
    act(() => result.current.conectar('T1'))
    const ws = MockWebSocket.instances[0]
    act(() => ws.mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))
    act(() => ws.mensaje({ type: 'events', events: [evento('e1'), evento('e2')] }))

    act(() => ws.mensaje({ type: 'event', event: evento('e3', 'downtime') }))
    act(() => ws.mensaje({ type: 'event', event: evento('e4', 'kpi') }))

    expect(result.current.eventos).toHaveLength(2)
    expect(result.current.eventos.map((e) => e.id)).toEqual(['e3', 'e4'])
  })

  it('responde pong a cada ping del servidor', () => {
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    const ws = MockWebSocket.instances[0]
    act(() => ws.mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))

    act(() => ws.mensaje({ type: 'ping' }))

    expect(ws.sent).toContain(JSON.stringify({ type: 'pong' }))
  })

  it('expone el error enviado por el servidor', () => {
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    const ws = MockWebSocket.instances[0]
    act(() => ws.mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))

    act(() =>
      ws.mensaje({ type: 'error', code: 'unsupported', message: 'tipo no soportado' }),
    )

    expect(result.current.error).toBe('tipo no soportado')
  })

  it('reconecta con backoff exponencial tras un cierre no deseado', () => {
    vi.useFakeTimers()
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    const ws = MockWebSocket.instances[0]
    act(() => ws.mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))

    act(() => ws.cerrarServidor())
    expect(result.current.estado).toBe('reconectando')
    expect(MockWebSocket.instances).toHaveLength(1)

    // backoff base 1000 ms con jitter ±30 %: el primer reintento cae en [700, 1300]
    act(() => {
      vi.advanceTimersByTime(1400)
    })

    expect(MockWebSocket.instances).toHaveLength(2)
    const ws2 = MockWebSocket.instances[1]
    expect(ws2.url).toContain('tenant_id=T1')
    act(() => ws2.mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))
    expect(result.current.estado).toBe('conectado')
  })

  it('reconecta al instante cuando vuelve la red (evento online)', () => {
    vi.useFakeTimers()
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    const ws = MockWebSocket.instances[0]
    act(() => ws.mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))
    act(() => ws.cerrarServidor())
    expect(result.current.estado).toBe('reconectando')

    act(() => {
      window.dispatchEvent(new Event('online'))
    })

    expect(MockWebSocket.instances).toHaveLength(2)
    expect(result.current.estado).toBe('conectando')
  })

  it('desconectar cierra el socket y limpia el estado', () => {
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    const ws = MockWebSocket.instances[0]
    act(() => ws.mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))
    act(() => ws.mensaje({ type: 'event', event: evento('e1') }))

    act(() => result.current.desconectar())

    expect(ws.readyState).toBe(MockWebSocket.CLOSED)
    expect(result.current.estado).toBe('desconectado')
    expect(result.current.error).toBeNull()
  })

  it('conectar dos veces cierra el socket anterior (idempotente ante StrictMode)', () => {
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    const primero = MockWebSocket.instances[0]

    act(() => result.current.conectar('T1'))

    expect(MockWebSocket.instances).toHaveLength(2)
    expect(primero.readyState).toBe(MockWebSocket.CLOSED)
  })
})
