// Mock de WebSocket para los tests de vitest (jsdom no implementa WebSocket
// nativo). Los helpers mensaje/cerrarServidor simulan el lado servidor del
// protocolo de ADR-014.
export class MockWebSocket {
  static instances: MockWebSocket[] = []
  static OPEN = 1
  static CLOSED = 3

  url: string
  protocols: string | string[] | undefined
  sent: string[] = []
  readyState = 0 // CONNECTING
  onopen: ((ev: Event) => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null

  constructor(url: string, protocols?: string | string[]) {
    this.url = url
    this.protocols = protocols
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.({ type: 'close' } as CloseEvent)
  }

  // Simula la llegada de un mensaje JSON del servidor
  mensaje(obj: unknown) {
    this.onmessage?.({ data: JSON.stringify(obj) })
  }

  // Simula un cierre iniciado por el servidor (caída de red, cierre 1001, ...)
  cerrarServidor() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.({ type: 'close' } as CloseEvent)
  }
}
