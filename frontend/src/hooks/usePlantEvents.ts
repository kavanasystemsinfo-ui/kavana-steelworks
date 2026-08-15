import { useCallback, useEffect, useRef, useState } from 'react'
import type { EventData } from '../lib/api'

export type ConexionEstado = 'desconectado' | 'conectando' | 'conectado' | 'reconectando'

export interface UsePlantEvents {
  conectar(tenantId: string): void
  desconectar(): void
  eventos: EventData[] // últimos maxEventos (default 50), el más reciente al final
  ultimoEvento: EventData | null
  estado: ConexionEstado
  error: string | null
}

export interface UsePlantEventsOptions {
  maxEventos?: number // default 50
  autoReconnect?: boolean // default true
  backoffBaseMs?: number // default 1000
  heartbeatMs?: number // default 30000
}

interface WsMessage {
  type?: string
  events?: EventData[]
  event?: EventData
  message?: string
}

const SUBPROTOCOLO = 'kavana.v1'
const RECONEXION_MAX_MS = 30000
const WS_OPEN = 1

/** Base del WS: VITE_WS_URL si existe (p.ej. directo a Fly, porque Vercel
 *  puede no reenviar upgrades), si no el mismo origen (rewrite /api/*). */
function wsBaseUrl(): string {
  const env = import.meta.env.VITE_WS_URL
  if (env) return String(env).replace(/\/+$/, '')
  const protocolo = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocolo}://${window.location.host}`
}

/** Suscripción a eventos de planta por WebSocket (ADR-014).
 *  Reconexión automática con backoff exponencial + jitter (tope 30 s) y
 *  respuesta pong al ping del servidor. La entrega es at-most-once por
 *  conexión; la cola FIFO del broker es la memoria de reconexión. */
export function usePlantEvents(options: UsePlantEventsOptions = {}): UsePlantEvents {
  const [eventos, setEventos] = useState<EventData[]>([])
  const [estado, setEstado] = useState<ConexionEstado>('desconectado')
  const [error, setError] = useState<string | null>(null)

  // Opciones en un ref: los callbacks del socket y los timers nunca ven
  // closures viejos aunque el componente se re-renderice.
  const optsRef = useRef({
    maxEventos: 50,
    autoReconnect: true,
    backoffBaseMs: 1000,
    heartbeatMs: 30000,
  })
  optsRef.current = {
    maxEventos: options.maxEventos ?? 50,
    autoReconnect: options.autoReconnect ?? true,
    backoffBaseMs: options.backoffBaseMs ?? 1000,
    heartbeatMs: options.heartbeatMs ?? 30000,
  }

  const wsRef = useRef<WebSocket | null>(null)
  const tenantRef = useRef<string | null>(null)
  const cerradoPorUsuarioRef = useRef(false)
  const intentosRef = useRef(0)
  const timerReconexionRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const watchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const limpiarTimers = () => {
    if (timerReconexionRef.current) {
      clearTimeout(timerReconexionRef.current)
      timerReconexionRef.current = null
    }
    if (watchdogRef.current) {
      clearTimeout(watchdogRef.current)
      watchdogRef.current = null
    }
  }

  const conectarRef = useRef<(tenantId: string) => void>(() => {})

  const reconectar = useCallback(() => {
    const t = tenantRef.current
    if (t && !cerradoPorUsuarioRef.current) conectarRef.current(t)
  }, [])

  const programarReconexion = useCallback(() => {
    const base = optsRef.current.backoffBaseMs
    const intento = intentosRef.current
    intentosRef.current += 1
    const exp = Math.min(base * 2 ** intento, RECONEXION_MAX_MS)
    const conJitter = exp * (0.7 + Math.random() * 0.6)
    if (timerReconexionRef.current) clearTimeout(timerReconexionRef.current)
    timerReconexionRef.current = setTimeout(reconectar, conJitter)
  }, [reconectar])

  const armarWatchdog = useCallback((ws: WebSocket) => {
    if (watchdogRef.current) clearTimeout(watchdogRef.current)
    // Si no llega NINGÚN mensaje en 2 ciclos de heartbeat, el proxy pudo
    // matar el socket sin avisar (half-open); lo cerramos y reconectamos.
    watchdogRef.current = setTimeout(() => {
      if (wsRef.current === ws && ws.readyState === WS_OPEN) ws.close()
    }, optsRef.current.heartbeatMs * 2)
  }, [])

  const conectar = useCallback(
    (tenantId: string) => {
      cerradoPorUsuarioRef.current = false
      tenantRef.current = tenantId
      // Cierra el socket anterior sin disparar su onclose (idempotente ante
      // el doble montaje de StrictMode y ante llamadas repetidas).
      const previo = wsRef.current
      wsRef.current = null
      if (previo) {
        previo.onmessage = null
        previo.onclose = null
        previo.onerror = null
        previo.close()
      }
      limpiarTimers()
      setError(null)
      setEstado('conectando')
      const url = `${wsBaseUrl()}/api/v1/ws/events?tenant_id=${encodeURIComponent(tenantId)}`
      const ws = new WebSocket(url, SUBPROTOCOLO)
      wsRef.current = ws

      ws.onmessage = (ev) => {
        armarWatchdog(ws)
        let msg: WsMessage
        try {
          msg = JSON.parse(String(ev.data)) as WsMessage
        } catch {
          return
        }
        if (msg.type === 'hello') {
          intentosRef.current = 0
          setEstado('conectado')
        } else if (msg.type === 'events' && Array.isArray(msg.events)) {
          setEventos(msg.events.slice(-optsRef.current.maxEventos))
        } else if (msg.type === 'event' && msg.event) {
          const nuevo = msg.event
          setEventos((prev) => [...prev, nuevo].slice(-optsRef.current.maxEventos))
        } else if (msg.type === 'ping') {
          ws.send(JSON.stringify({ type: 'pong' }))
        } else if (msg.type === 'error') {
          setError(msg.message ?? 'Error del servidor de eventos')
        }
      }

      ws.onclose = () => {
        if (wsRef.current === ws) wsRef.current = null
        if (cerradoPorUsuarioRef.current) {
          setEstado('desconectado')
          return
        }
        if (optsRef.current.autoReconnect) {
          setEstado('reconectando')
          programarReconexion()
        } else {
          setEstado('desconectado')
        }
      }
    },
    [armarWatchdog, programarReconexion],
  )

  conectarRef.current = conectar

  const desconectar = useCallback(() => {
    cerradoPorUsuarioRef.current = true
    tenantRef.current = null
    limpiarTimers()
    const ws = wsRef.current
    wsRef.current = null
    if (ws) {
      ws.onmessage = null
      ws.onclose = null
      ws.onerror = null
      ws.close()
    }
    setEstado('desconectado')
    setError(null)
  }, [])

  useEffect(() => {
    // Reconexión inmediata al volver la red (ADR-014), sin esperar el backoff
    const alVolverLaRed = () => {
      if (cerradoPorUsuarioRef.current) return
      if (!optsRef.current.autoReconnect) return
      const t = tenantRef.current
      if (!t) return
      if (timerReconexionRef.current) {
        clearTimeout(timerReconexionRef.current)
        timerReconexionRef.current = null
      }
      conectarRef.current(t)
    }
    window.addEventListener('online', alVolverLaRed)
    return () => {
      window.removeEventListener('online', alVolverLaRed)
      desconectar()
    }
  }, [desconectar])

  const ultimoEvento = eventos.length > 0 ? eventos[eventos.length - 1] : null

  return { conectar, desconectar, eventos, ultimoEvento, estado, error }
}
