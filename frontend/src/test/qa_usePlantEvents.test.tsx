import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePlantEvents } from '../hooks/usePlantEvents'
import { MockWebSocket } from './mockWebSocket'

// Tests QA independientes del hook usePlantEvents (ADR-014): cubren casos
// que la suite original no cubre: tope del backoff con jitter máximo,
// ausencia de doble conexión, watchdog de half-open, autoReconnect=false,
// cierres 1001/4403, hello que reinicia el backoff, JSON inválido del
// servidor, y el estado colgado si el servidor nunca envía hello.

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
  vi.restoreAllMocks()
})

describe('QA usePlantEvents (ADR-014)', () => {
  it('qa: backoff exponencial 1,2,4,8,16 s y tope 30 s; con jitter máximo el tope real es 39 s', () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(1) // jitter máximo: factor 1.3
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    act(() => MockWebSocket.instances[0].mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))

    // con random=1 los retrasos son: 1300, 2600, 5200, 10400, 20800, 39000
    // (margen de 5 ms por el epsilon de coma flotante)
    const esperados = [1300, 2600, 5200, 10400, 20800, 39000]
    for (const espera of esperados) {
      const antes = MockWebSocket.instances.length
      act(() => MockWebSocket.instances.at(-1)!.cerrarServidor())
      expect(result.current.estado).toBe('reconectando')
      act(() => vi.advanceTimersByTime(espera - 5))
      expect(MockWebSocket.instances).toHaveLength(antes) // aún no reconecta
      act(() => vi.advanceTimersByTime(6))
      expect(MockWebSocket.instances).toHaveLength(antes + 1) // exactamente uno
    }
    // Nota QA: el tope documentado de 30 s se aplica ANTES del jitter, así
    // que el retraso máximo real es 30000 * 1.3 = 39000 ms.
  })

  it('qa: cada ciclo de reconexión abre exactamente un socket (sin dobles)', () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0) // jitter mínimo: factor 0.7
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    act(() => MockWebSocket.instances[0].mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))

    for (const espera of [700, 1400, 2800]) {
      const antes = MockWebSocket.instances.length
      act(() => MockWebSocket.instances.at(-1)!.cerrarServidor())
      act(() => vi.advanceTimersByTime(espera + 5))
      expect(MockWebSocket.instances).toHaveLength(antes + 1)
    }
  })

  it('qa: conectar() durante la espera de reconexión cancela el timer pendiente', () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0)
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    act(() => MockWebSocket.instances[0].mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))
    act(() => MockWebSocket.instances[0].cerrarServidor())
    expect(result.current.estado).toBe('reconectando')

    act(() => result.current.conectar('T1'))
    act(() => vi.advanceTimersByTime(10000))
    expect(MockWebSocket.instances).toHaveLength(2) // el timer viejo se canceló
  })

  it('qa: watchdog cierra el socket si no llega ningún mensaje en 2 ciclos de heartbeat', () => {
    vi.useFakeTimers()
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents()) // heartbeatMs 30000 -> 60000
    act(() => result.current.conectar('T1'))
    const ws = MockWebSocket.instances[0]
    ws.readyState = MockWebSocket.OPEN
    act(() => ws.mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 })) // arma el watchdog

    act(() => vi.advanceTimersByTime(59999))
    expect(ws.readyState).toBe(MockWebSocket.OPEN)
    act(() => vi.advanceTimersByTime(1))
    expect(ws.readyState).toBe(MockWebSocket.CLOSED)
    expect(result.current.estado).toBe('reconectando')
  })

  it('qa: el watchdog se rearma con cada mensaje (ping periódico no dispara cierre)', () => {
    vi.useFakeTimers()
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    const ws = MockWebSocket.instances[0]
    ws.readyState = MockWebSocket.OPEN
    act(() => ws.mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 })) // watchdog t=60000

    act(() => vi.advanceTimersByTime(30000))
    act(() => ws.mensaje({ type: 'ping' })) // rearma para t=90000
    expect(ws.readyState).toBe(MockWebSocket.OPEN)

    act(() => vi.advanceTimersByTime(59999)) // t=89999: aún vivo
    expect(ws.readyState).toBe(MockWebSocket.OPEN)
    act(() => vi.advanceTimersByTime(1)) // t=90000: cierra
    expect(ws.readyState).toBe(MockWebSocket.CLOSED)
  })

  it('qa: sin hello el watchdog nunca se arma y el estado queda colgado en conectando', () => {
    vi.useFakeTimers()
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    const ws = MockWebSocket.instances[0]
    ws.readyState = MockWebSocket.OPEN
    // el servidor acepta el handshake pero nunca envía ningún mensaje
    act(() => vi.advanceTimersByTime(120000))
    expect(ws.readyState).toBe(MockWebSocket.OPEN) // nada lo cerró
    expect(result.current.estado).toBe('conectando') // colgado sin recuperación
  })

  it('qa: autoReconnect=false no reconecta tras un cierre', () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0.7)
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents({ autoReconnect: false }))
    act(() => result.current.conectar('T1'))
    act(() => MockWebSocket.instances[0].mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))
    act(() => MockWebSocket.instances[0].cerrarServidor())
    expect(result.current.estado).toBe('desconectado')
    act(() => vi.advanceTimersByTime(10000))
    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('qa: cierre 1001 del servidor dispara reconexión', () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0)
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    const ws = MockWebSocket.instances[0]
    act(() => ws.mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))
    act(() => ws.onclose?.({ type: 'close', code: 1001 } as CloseEvent))
    expect(result.current.estado).toBe('reconectando')
    act(() => vi.advanceTimersByTime(705))
    expect(MockWebSocket.instances).toHaveLength(2)
  })

  it('qa: cierre 4403 (auth terminal) también reintenta indefinidamente', () => {
    // El ADR pide reintento indefinido, pero 4403/4404 son condiciones
    // terminales: el hook no las distingue y seguirá martilleando el servidor.
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0)
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    const ws = MockWebSocket.instances[0]
    act(() => ws.onclose?.({ type: 'close', code: 4403 } as CloseEvent))
    expect(result.current.estado).toBe('reconectando')
    act(() => vi.advanceTimersByTime(705))
    expect(MockWebSocket.instances).toHaveLength(2)
  })

  it('qa: hello reinicia el backoff exponencial', () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0)
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    act(() => MockWebSocket.instances[0].mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))
    act(() => MockWebSocket.instances[0].cerrarServidor())
    act(() => vi.advanceTimersByTime(705))
    const ws2 = MockWebSocket.instances[1]
    act(() => ws2.mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 })) // resetea a 0
    act(() => ws2.cerrarServidor())
    act(() => vi.advanceTimersByTime(698))
    expect(MockWebSocket.instances).toHaveLength(2) // aún no: espera 700 otra vez
    act(() => vi.advanceTimersByTime(7))
    expect(MockWebSocket.instances).toHaveLength(3) // no 1400 ms
  })

  it('qa: desconectar() cancela la reconexión pendiente', () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0)
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    act(() => MockWebSocket.instances[0].mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))
    act(() => MockWebSocket.instances[0].cerrarServidor())
    act(() => result.current.desconectar())
    act(() => vi.advanceTimersByTime(10000))
    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('qa: error del servidor sin campo message usa el texto por defecto', () => {
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    const ws = MockWebSocket.instances[0]
    act(() => ws.mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))
    act(() => ws.mensaje({ type: 'error', code: 'unsupported' }))
    expect(result.current.error).toBe('Error del servidor de eventos')
  })

  it('qa: JSON inválido del servidor se ignora sin reventar ni cerrar', () => {
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    const ws = MockWebSocket.instances[0]
    act(() => ws.mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))
    act(() => ws.mensaje({ type: 'events', events: [evento('e1')] }))
    act(() => ws.onmessage?.({ data: 'esto no es json' }))
    expect(result.current.eventos).toHaveLength(1)
    expect(result.current.estado).toBe('conectado')
    expect(result.current.error).toBeNull()
  })

  it('qa: cambiar de tenant no limpia los eventos previos hasta el nuevo lote', () => {
    stubWebSocket()
    const { result } = renderHook(() => usePlantEvents())
    act(() => result.current.conectar('T1'))
    const ws1 = MockWebSocket.instances[0]
    act(() => ws1.mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))
    act(() => ws1.mensaje({ type: 'event', event: evento('e1') }))
    act(() => result.current.conectar('T2'))
    expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.CLOSED)
    expect(MockWebSocket.instances[1].url).toContain('tenant_id=T2')
    // los eventos de T1 siguen visibles hasta que llegue el lote de T2
    expect(result.current.eventos).toHaveLength(1)
  })
})
