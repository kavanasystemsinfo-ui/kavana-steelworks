// T-161: fallos de la cola sin conexión hallados al probar en producción el 21-11.
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { Layout } from '../components/layout/Layout'
import { OperarioPage } from '../pages/OperarioPage'

const CLAVE = 'steelworks-cola-produccion'
const b64 = (s: string) => btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
const token = `x.${b64(JSON.stringify({ sub: 'u1', tenant_id: 'T1', role: 'operator', exp: 9999999999 }))}.sig`

const parte = (intentos = 0) => ({
  client_request_id: crypto.randomUUID(),
  user_sub: 'u1',
  order_id: 'OP1',
  line_id: 'L1',
  incremental_quantity: 3,
  desglose: null,
  ocurrido_en: new Date().toISOString(),
  intentos,
  ultimo_error: null,
  estado: 'pendiente',
})

const json = (body: unknown, status = 200) =>
  Promise.resolve({ ok: status < 400, status, json: async () => body })

function preparar(nPartes: number, registro: { status: number; detail?: string }, intentos = 0) {
  const fetchMock = vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/admin/workstations')) {
      return json([{ id: 'w1', code: 'P-K300', name: 'Perfiladora', color: '#333', group_id: null, is_active: true }])
    }
    if (u.includes('/orders/available')) {
      return json([{ id: 'OP1', numero: 'OP-1', estado: 'active', cliente: 'C', fecha_entrega: null, workstation_id: 'P-K300' }])
    }
    if (u.includes('/orders/OP1')) {
      return json({ id: 'OP1', numero: 'OP-1', estado: 'active', lines: [{ id: 'L1', linea_numero: 1, workstation_id: 'P-K300' }] })
    }
    if (u.includes('/production/record')) {
      return registro.status === 200
        ? json({ success: true, incremental_quantity: 3, consumed_amount: 30, consumption_unit: 'kg' })
        : json({ detail: registro.detail ?? 'Error' }, registro.status)
    }
    if (u.includes('/mediciones-pendientes') || u.includes('/quality/models') || u.includes('/disponibles')) return json([])
    if (u.includes('/api/v1/events/')) return json({ events: [] })
    return json(null)
  })
  vi.stubGlobal('fetch', fetchMock)
  sessionStorage.clear()
  sessionStorage.setItem('kavana_token', token)
  localStorage.clear()
  localStorage.setItem('steelworks-tour-visto-operator', 'true')
  localStorage.setItem(CLAVE, JSON.stringify(Array.from({ length: nPartes }, () => parte(intentos))))
  return fetchMock
}

const llamadas = (f: { mock: { calls: unknown[][] } }, trozo: string) =>
  f.mock.calls.filter(([u]) => String(u).includes(trozo)).length
const cola = () => JSON.parse(localStorage.getItem(CLAVE) || '[]')
const panel = () =>
  render(
    <MemoryRouter>
      <OperarioPage />
    </MemoryRouter>,
  )

describe('T-161: cola sin conexión', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true })
    localStorage.clear()
    sessionStorage.clear()
  })

  it('si vuelve el wifi con la API caída, sigue reintentando solo hasta enviar', async () => {
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true })
    const registro = { status: 503 }
    const f = preparar(1, registro, 5)
    panel()
    await screen.findByText(/1 parte sin enviar/)
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true })
    window.dispatchEvent(new Event('online'))
    await waitFor(() => expect(llamadas(f, '/production/record')).toBeGreaterThan(0))
    registro.status = 200
    await waitFor(() => expect(cola()).toEqual([]), { timeout: 7000 })
  }, 10000)

  it('al montar con pendientes y red, los envía sin esperar al temporizador', async () => {
    preparar(1, { status: 200 }, 5)
    panel()
    await waitFor(() => expect(cola()).toEqual([]), { timeout: 2000 })
  })

  it('una sesión caducada al reenviar avisa, no borra y deja de reintentar', async () => {
    const f = preparar(2, { status: 401, detail: 'Token inválido o expirado' })
    panel()
    expect(await screen.findByText(/Tu sesión ha caducado: vuelve a entrar para enviar 2 partes/)).toBeInTheDocument()
    expect(cola()).toHaveLength(2)
    const antes = llamadas(f, '/production/record')
    await new Promise((r) => setTimeout(r, 5600))
    expect(llamadas(f, '/production/record')).toBe(antes)
  }, 10000)

  it('tras un envío automático refresca la ficha de la orden', async () => {
    const user = userEvent.setup()
    const registro = { status: 503 }
    const f = preparar(1, registro, 5)
    panel()
    await waitFor(() => expect(llamadas(f, '/production/ficha')).toBeGreaterThan(0))
    const antes = llamadas(f, '/production/ficha')
    registro.status = 200
    await user.click(await screen.findByRole('button', { name: 'Enviar ahora' }))
    await waitFor(() => expect(cola()).toEqual([]))
    await waitFor(() => expect(llamadas(f, '/production/ficha')).toBeGreaterThan(antes))
  })

  it('«Salir» con partes pendientes avisa y deja cancelar o salir', async () => {
    const user = userEvent.setup()
    const f = preparar(2, { status: 503 })
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true })
    render(
      <MemoryRouter initialEntries={['/operario']}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/operario" element={<p>Panel</p>} />
          </Route>
          <Route path="/login" element={<p>Pantalla de login</p>} />
        </Routes>
      </MemoryRouter>,
    )
    await user.click(screen.getByRole('button', { name: 'Salir' }))
    expect(await screen.findByText(/Quedan 2 partes sin enviar en esta tablet/)).toBeInTheDocument()
    expect(llamadas(f, '/auth/logout')).toBe(0)
    await user.click(screen.getByRole('button', { name: 'Seguir aquí' }))
    expect(screen.queryByText(/Quedan 2 partes/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Salir' }))
    await user.click(await screen.findByRole('button', { name: 'Salir igualmente' }))
    expect(await screen.findByText('Pantalla de login')).toBeInTheDocument()
    expect(cola()).toHaveLength(2)
  })
})
