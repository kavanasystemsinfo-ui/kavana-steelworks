/** Cola de producción sin conexión (T-159, auditoría H8).
 *
 * El parte se guarda ANTES en localStorage y después se intenta enviar. Si
 * cae el wifi, la cola reintenta sola con espera creciente (5 s, 15 s, 60 s,
 * luego cada 2 min) y también al recibir el evento «online» del navegador.
 *
 * Clasificación del resultado:
 * - Éxito o duplicate: sale de la cola (el servidor lo registró una vez).
 * - Error de red, timeout (AbortController 15 s), 5xx o 429: sigue pendiente.
 * - 401: la cola se PAUSA (nada se borra); al volver a entrar el MISMO
 *   usuario (mismo user_sub del JWT) se reanuda.
 * - 400, 409 o 422: pasa a «fallido» con el mensaje del servidor y la cola
 *   SIGUE con el siguiente (lección PR #84: nunca se detiene en el primero).
 *
 * Sin dependencias nuevas: solo localStorage, todo envuelto en try/catch
 * (una tablet sin almacenamiento no puede romper el registro en línea).
 */

import { api, ApiError, type Desglose } from './api'

export const CLAVE_COLA = 'steelworks-cola-produccion'
export const TIMEOUT_ENVIO_MS = 15000

/** Esperas entre reintentos: 5 s, 15 s, 60 s y luego cada 2 min. */
const ESPERAS_MS = [5000, 15000, 60000]

export interface ElementoCola {
  /** Clave de idempotencia: se genera UNA vez al pulsar «Registrar». */
  client_request_id: string
  /** sub del JWT del operario que registró (solo él lo envía al volver). */
  user_sub: string
  order_id: string
  line_id: string
  incremental_quantity: number
  desglose: Desglose | null
  /** Hora real del parte en la tablet (ISO). */
  ocurrido_en: string
  intentos: number
  ultimo_error: string | null
  estado: 'pendiente' | 'fallido'
}

export interface ResumenCola {
  pendientesMios: number
  fallidosMios: number
  pendientesOtros: number
}

export interface ResultadoProcesado {
  /** true si un 401 pausó la cola (hay que volver a entrar). */
  pausada: boolean
  enviados: number
}

export function cargarCola(): ElementoCola[] {
  try {
    const crudo = localStorage.getItem(CLAVE_COLA)
    if (!crudo) return []
    const datos = JSON.parse(crudo)
    return Array.isArray(datos) ? datos : []
  } catch {
    return []
  }
}

function guardarCola(cola: ElementoCola[]): void {
  try {
    localStorage.setItem(CLAVE_COLA, JSON.stringify(cola))
  } catch {
    /* sin almacenamiento: el envío en línea sigue funcionando */
  }
}

function actualizar(clientRequestId: string, cambio: (e: ElementoCola) => ElementoCola): void {
  guardarCola(
    cargarCola().map((e) => (e.client_request_id === clientRequestId ? cambio(e) : e)),
  )
}

function quitar(clientRequestId: string): void {
  guardarCola(cargarCola().filter((e) => e.client_request_id !== clientRequestId))
}

export function marcarFallido(clientRequestId: string, mensaje: string): void {
  actualizar(clientRequestId, (e) => ({ ...e, estado: 'fallido', ultimo_error: mensaje }))
}

export function reintentar(clientRequestId: string): void {
  actualizar(clientRequestId, (e) => ({
    ...e,
    estado: 'pendiente',
    ultimo_error: null,
    intentos: 0,
  }))
}

export function reintentarTodos(): void {
  guardarCola(
    cargarCola().map((e) =>
      e.estado === 'fallido' ? { ...e, estado: 'pendiente', ultimo_error: null, intentos: 0 } : e,
    ),
  )
}

export function descartar(clientRequestId: string): void {
  quitar(clientRequestId)
}

export function estadoCola(userSub: string | null): ResumenCola {
  const cola = cargarCola()
  return {
    pendientesMios: cola.filter((e) => e.user_sub === userSub && e.estado === 'pendiente').length,
    fallidosMios: cola.filter((e) => e.user_sub === userSub && e.estado === 'fallido').length,
    pendientesOtros: cola.filter((e) => e.user_sub !== userSub).length,
  }
}

function esperaReintento(intentos: number): number {
  return intentos < ESPERAS_MS.length ? ESPERAS_MS[intentos] : 120000
}

type EnviarFn = (el: ElementoCola) => Promise<unknown>

/** Envío por defecto: la API real con timeout de 15 s (AbortController). */
export const enviarPorApi: EnviarFn = (el) =>
  api.recordProduction(
    {
      order_id: el.order_id,
      line_id: el.line_id,
      incremental_quantity: el.incremental_quantity,
      desglose: el.desglose,
      client_request_id: el.client_request_id,
      ocurrido_en: el.ocurrido_en,
    },
    { timeoutMs: TIMEOUT_ENVIO_MS },
  )

function esFalloRedOTimeout(err: unknown): boolean {
  if (err instanceof DOMException && err.name === 'AbortError') return true
  if (err instanceof TypeError) return true // fetch failed / NetworkError
  return false
}

function esReintentable(err: unknown): boolean {
  if (esFalloRedOTimeout(err)) return true
  if (err instanceof ApiError && (err.status === 429 || err.status >= 500)) return true
  return false
}

/**
 * Guarda el parte en la cola y lo intenta enviar ya. Devuelve si el servidor
 * lo aceptó (salió de la cola con su respuesta) o sigue pendiente (sin red
 * o error reintentable).
 */
export type ResultadoEnvio =
  | { tipo: 'aceptado'; respuesta: unknown }
  | { tipo: 'pendiente' }

export async function encolarYEnviar(
  el: ElementoCola,
  enviar: EnviarFn = enviarPorApi,
): Promise<ResultadoEnvio> {
  const cola = cargarCola()
  if (!cola.some((e) => e.client_request_id === el.client_request_id)) {
    guardarCola([...cola, el])
  }
  return enviarYRegistrar(el, enviar)
}

/** Intenta enviar un elemento ya en la cola. */
async function enviarYRegistrar(el: ElementoCola, enviar: EnviarFn): Promise<ResultadoEnvio> {
  try {
    const respuesta = await enviar(el)
    quitar(el.client_request_id)
    return { tipo: 'aceptado', respuesta }
  } catch (err) {
    if (esReintentable(err)) {
      actualizar(el.client_request_id, (e) => ({ ...e, intentos: e.intentos + 1 }))
    } else if (err instanceof ApiError && err.status === 401) {
      // Pausa: queda pendiente; se reanuda al volver a entrar el mismo usuario
    } else {
      marcarFallido(
        el.client_request_id,
        err instanceof Error ? err.message : 'Error al registrar',
      )
    }
    return { tipo: 'pendiente' }
  }
}

/**
 * Intenta vaciar la cola del usuario conectado. Los elementos de otro
 * operario se quedan guardados. Un 401 pausa el proceso sin borrar nada.
 */
export async function procesarCola(
  userSub: string,
  enviar: EnviarFn = enviarPorApi,
): Promise<ResultadoProcesado> {
  let enviados = 0
  for (const el of cargarCola()) {
    if (el.user_sub !== userSub || el.estado !== 'pendiente') continue
    try {
      await enviar(el)
      quitar(el.client_request_id)
      enviados++
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        return { pausada: true, enviados }
      }
      if (esReintentable(err)) {
        actualizar(el.client_request_id, (e) => ({ ...e, intentos: e.intentos + 1 }))
      } else {
        marcarFallido(
          el.client_request_id,
          err instanceof Error ? err.message : 'Error al registrar',
        )
      }
      // La cola SIGUE con el siguiente (nunca se detiene en un fallido)
    }
  }
  return { pausada: false, enviados }
}

/** Milisegundos de espera recomendada antes del próximo reintento automático. */
export function esperaSiguienteReintento(): number {
  const pendientes = cargarCola().filter((e) => e.estado === 'pendiente')
  const maxIntentos = pendientes.reduce((m, e) => Math.max(m, e.intentos), 0)
  return esperaReintento(maxIntentos)
}
