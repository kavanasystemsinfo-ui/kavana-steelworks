/** Tests TDD de la cola de producción sin conexión (T-159, auditoría H8).
 *
 * Contrato:
 * - Al registrar: se guarda primero en la cola y después se intenta enviar.
 * - Éxito o duplicate: sale de la cola.
 * - Error de red / timeout / 5xx / 429: sigue pendiente (reintenta el mismo id).
 * - 401: la cola se PAUSA (no se borra).
 * - 400 / 409 / 422: pasa a «fallido» con el mensaje del servidor y la cola SIGUE.
 * - Solo se envían los elementos del user_sub conectado.
 * - «Reintentar» devuelve el elemento a pendiente.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from '../lib/api'
import {
  cargarCola,
  encolarYEnviar,
  estadoCola,
  marcarFallido,
  procesarCola,
  reintentar,
  reintentarTodos,
  descartar,
  CLAVE_COLA,
  type ElementoCola,
} from '../lib/colaProduccion'

function elemento(parcial: Partial<ElementoCola> = {}): ElementoCola {
  return {
    client_request_id: crypto.randomUUID(),
    user_sub: 'user-1',
    order_id: 'orden-1',
    line_id: 'linea-1',
    incremental_quantity: 5,
    desglose: null,
    ocurrido_en: new Date().toISOString(),
    intentos: 0,
    ultimo_error: null,
    estado: 'pendiente',
    ...parcial,
  }
}

describe('colaProduccion', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('éxito: el elemento sale de la cola', async () => {
    const enviar = vi.fn().mockResolvedValue({ success: true })
    const el = elemento()
    await encolarYEnviar(el, enviar)
    expect(enviar).toHaveBeenCalledTimes(1)
    expect(cargarCola()).toEqual([])
  })

  it('duplicate del servidor: también sale de la cola', async () => {
    const enviar = vi.fn().mockResolvedValue({ success: true, duplicate: true })
    await encolarYEnviar(elemento(), enviar)
    expect(cargarCola()).toEqual([])
  })

  it('fallo de red: sigue pendiente y el reintento usa el MISMO client_request_id', async () => {
    const enviar = vi.fn().mockRejectedValue(new TypeError('fetch failed'))
    const el = elemento()
    await encolarYEnviar(el, enviar)
    expect(cargarCola()).toHaveLength(1)
    expect(cargarCola()[0].estado).toBe('pendiente')

    // La red vuelve: procesarCola reintenta con el mismo id
    enviar.mockResolvedValue({ success: true })
    await procesarCola('user-1', enviar)
    expect(enviar).toHaveBeenCalledTimes(2)
    expect(enviar.mock.calls[1][0].client_request_id).toBe(el.client_request_id)
    expect(cargarCola()).toEqual([])
  })

  it('timeout (AbortError): sigue pendiente', async () => {
    const enviar = vi.fn().mockRejectedValue(new DOMException('Aborted', 'AbortError'))
    await encolarYEnviar(elemento(), enviar)
    expect(cargarCola()[0]?.estado).toBe('pendiente')
  })

  it('500 y 429: sigue pendiente', async () => {
    const enviar = vi.fn().mockRejectedValue(new ApiError('Error 500', 500))
    await encolarYEnviar(elemento(), enviar)
    enviar.mockRejectedValue(new ApiError('Error 429', 429))
    await encolarYEnviar(elemento(), enviar)
    const cola = cargarCola()
    expect(cola).toHaveLength(2)
    expect(cola.every((e) => e.estado === 'pendiente')).toBe(true)
  })

  it('400: pasa a fallido con el mensaje del servidor y la cola SIGUE con el siguiente', async () => {
    const malo = elemento({ incremental_quantity: 999 })
    const bueno = elemento()
    localStorage.setItem(CLAVE_COLA, JSON.stringify([malo, bueno]))
    const enviar = vi
      .fn()
      .mockRejectedValueOnce(new ApiError('No hay bobina vinculada a esta línea.', 400))
      .mockResolvedValueOnce({ success: true })

    await procesarCola('user-1', enviar)
    const cola = cargarCola()
    expect(cola).toHaveLength(1)
    expect(cola[0].client_request_id).toBe(malo.client_request_id)
    expect(cola[0].estado).toBe('fallido')
    expect(cola[0].ultimo_error).toBe('No hay bobina vinculada a esta línea.')
    expect(enviar).toHaveBeenCalledTimes(2) // no se detuvo en el fallido
  })

  it('409 y 422 también van a fallidos', async () => {
    localStorage.setItem(CLAVE_COLA, JSON.stringify([elemento(), elemento()]))
    const enviar = vi
      .fn()
      .mockRejectedValueOnce(new ApiError('Conflicto', 409))
      .mockRejectedValueOnce(new ApiError('Validación', 422))
    await procesarCola('user-1', enviar)
    expect(cargarCola().every((e) => e.estado === 'fallido')).toBe(true)
  })

  it('401: la cola se PAUSA sin borrar nada y no intenta los siguientes', async () => {
    localStorage.setItem(CLAVE_COLA, JSON.stringify([elemento(), elemento()]))
    const enviar = vi.fn().mockRejectedValue(new ApiError('Token requerido', 401))
    const res = await procesarCola('user-1', enviar)
    expect(res.pausada).toBe(true)
    expect(enviar).toHaveBeenCalledTimes(1) // no sigue con el segundo
    expect(cargarCola()).toHaveLength(2) // nada se borró
    expect(cargarCola().every((e) => e.estado === 'pendiente')).toBe(true)
  })

  it('solo se envían los elementos del user_sub conectado', async () => {
    const mio = elemento({ user_sub: 'user-1' })
    const deOtro = elemento({ user_sub: 'user-2' })
    localStorage.setItem(CLAVE_COLA, JSON.stringify([mio, deOtro]))
    const enviar = vi.fn().mockResolvedValue({ success: true })
    await procesarCola('user-1', enviar)
    expect(enviar).toHaveBeenCalledTimes(1)
    expect(enviar.mock.calls[0][0].client_request_id).toBe(mio.client_request_id)
    const cola = cargarCola()
    expect(cola).toHaveLength(1)
    expect(cola[0].user_sub).toBe('user-2')
  })

  it('reintentar devuelve un fallido a pendiente; descartar lo borra', async () => {
    const el = elemento({ estado: 'fallido', ultimo_error: 'x' })
    localStorage.setItem(CLAVE_COLA, JSON.stringify([el]))
    reintentar(el.client_request_id)
    expect(cargarCola()[0].estado).toBe('pendiente')
    expect(cargarCola()[0].ultimo_error).toBeNull()
    descartar(el.client_request_id)
    expect(cargarCola()).toEqual([])
  })

  it('reintentarTodos devuelve todos los fallidos a pendiente', async () => {
    localStorage.setItem(
      CLAVE_COLA,
      JSON.stringify([elemento({ estado: 'fallido' }), elemento({ estado: 'fallido' })]),
    )
    reintentarTodos()
    expect(cargarCola().every((e) => e.estado === 'pendiente')).toBe(true)
  })

  it('estadoCola resume pendientes y fallidos por usuario', () => {
    localStorage.setItem(
      CLAVE_COLA,
      JSON.stringify([
        elemento({ user_sub: 'u1' }),
        elemento({ user_sub: 'u1', estado: 'fallido' }),
        elemento({ user_sub: 'u2' }),
      ]),
    )
    const res = estadoCola('u1')
    expect(res.pendientesMios).toBe(1)
    expect(res.fallidosMios).toBe(1)
    expect(res.pendientesOtros).toBe(1)
  })

  it('localStorage roto no rompe la app: cola vacía y sin throw', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denegado')
    })
    expect(cargarCola()).toEqual([])
    vi.restoreAllMocks()
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('lleno')
    })
    const el = elemento()
    // encolarYEnviar sigue intentando el envío aunque no se pueda guardar
    const enviar = vi.fn().mockResolvedValue({ success: true })
    return expect(encolarYEnviar(el, enviar)).resolves.toMatchObject({ tipo: 'aceptado' })
  })

  it('marcarFallido registra el motivo', () => {
    const el = elemento()
    localStorage.setItem(CLAVE_COLA, JSON.stringify([el]))
    marcarFallido(el.client_request_id, 'motivo x')
    expect(cargarCola()[0].estado).toBe('fallido')
    expect(cargarCola()[0].ultimo_error).toBe('motivo x')
  })

  it('debug: que devuelve recordProduction con fetch mockeado', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.includes('/production/record')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            incremental_quantity: 5,
            consumed_amount: 4.75,
            consumption_unit: 'kg',
            calculation_method: 'density_formula',
          }),
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })
    vi.stubGlobal('fetch', fetchMock)
    const res = await api.recordProduction({
      order_id: 'o-1',
      line_id: 'l-1',
      incremental_quantity: 5,
    })
    // eslint-disable-next-line no-console
    console.log('RESULTADO API:', JSON.stringify(res))
    expect(res.incremental_quantity).toBe(5)
    vi.unstubAllGlobals()
  })
})
