// T-162: cerrar sin medir. Menos de 20 kg va a merma; desde 20 kg el operario elige.
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { Layout } from '../components/layout/Layout'
import { OperarioPage } from '../pages/OperarioPage'

const b64 = (s: string) => btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
const token = `x.${b64(JSON.stringify({ sub: 'u1', tenant_id: 'T1', role: 'operator', exp: 9999999999 }))}.sig`
const json = (body: unknown, status = 200) =>
  Promise.resolve({ ok: status < 400, status, json: async () => body })

function preparar(kg: number) {
  const pendiente = { stock_item_id: 'SI1', coil_code: 'COIL-1', order_id: 'OP1', line_id: 'L1', puesto: 'P-K300', kg_restantes: kg }
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    if (u.includes('/mediciones-pendientes')) return json([pendiente])
    if (u.includes('/auth/close-shift')) {
      return json({ success: true, status: 'completed', total_hours: 8, turno: 'B', logout_time: 'x', merma_sin_medir_kg: kg })
    }
    if (u.includes('/auth/logout')) {
      const elige = JSON.parse(String(init?.body ?? '{}')).mermar_sin_medir
      if (elige) return Promise.resolve({ ok: true, status: 204, json: async () => ({}) })
      return json({ detail: { codigo: 'medicion_pendiente', mensaje: 'Quedan kg sin medir en COIL-1 (120.0 kg). Mide la bobina o manda esos kg a merma.', kg_total: kg, bobinas: [pendiente] } }, 409)
    }
    if (u.includes('/admin/workstations') || u.includes('/orders/available') || u.includes('/quality/models')) return json([])
    if (u.includes('/api/v1/events/')) return json({ events: [] })
    return json(null)
  })
  vi.stubGlobal('fetch', fetchMock)
  sessionStorage.setItem('kavana_token', token)
  localStorage.clear()
  localStorage.setItem('steelworks-tour-visto-operator', 'true')
  return fetchMock
}

const cuerpo = (f: { mock: { calls: unknown[][] } }, trozo: string) => {
  const c = f.mock.calls.find(([u]) => String(u).includes(trozo)) as [string, RequestInit] | undefined
  return c ? JSON.parse(String(c[1].body)) : null
}
const panel = () =>
  render(
    <MemoryRouter>
      <OperarioPage />
    </MemoryRouter>,
  )

describe('T-162: cerrar la jornada sin medir', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    localStorage.clear()
    sessionStorage.clear()
  })

  it('con menos de 20 kg avisa de la merma y deja cerrar sin medir', async () => {
    const user = userEvent.setup()
    const f = preparar(12.5)
    panel()
    await user.click(await screen.findByRole('button', { name: /cerrar jornada/i }))
    expect(await screen.findByText(/tiene 12,5 kg sin medir: se anotarán como merma/)).toBeInTheDocument()
    expect(screen.queryByPlaceholderText(/carne \(mm\)/i)).not.toBeInTheDocument()
    const cerrar = screen.getByRole('button', { name: /sí, cerrar/i })
    await waitFor(() => expect(cerrar).toBeEnabled())
    await user.click(cerrar)
    await waitFor(() => expect(cuerpo(f, '/auth/close-shift')).toEqual({ mermar_sin_medir: false }))
  })

  it('desde 20 kg ofrece medir o mandar a merma, con confirmación', async () => {
    const user = userEvent.setup()
    const f = preparar(120)
    panel()
    await user.click(await screen.findByRole('button', { name: /cerrar jornada/i }))
    expect(await screen.findByPlaceholderText(/carne \(mm\)/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sí, cerrar/i })).toBeDisabled()
    await user.click(await screen.findByRole('button', { name: 'No medir: mandar 120 kg a merma y cerrar' }))
    expect(cuerpo(f, '/auth/close-shift')).toBeNull()
    expect(screen.getByText(/Se anotarán 120 kg como merma/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Sí, mandar a merma' }))
    await waitFor(() => expect(cuerpo(f, '/auth/close-shift')).toEqual({ mermar_sin_medir: true }))
  })

  it('«Salir» con 20 kg o más deja elegir mandarlos a merma', async () => {
    const user = userEvent.setup()
    const f = preparar(120)
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
    await user.click(await screen.findByRole('button', { name: 'Mandar 120 kg a merma y salir' }))
    expect(screen.getByText(/Se anotarán 120 kg como merma/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Sí, mandar a merma y salir' }))
    expect(await screen.findByText('Pantalla de login')).toBeInTheDocument()
    const ultimo = f.mock.calls.filter(([u]) => String(u).includes('/auth/logout')).at(-1) as unknown as [string, RequestInit]
    expect(JSON.parse(String(ultimo[1].body))).toEqual({ mermar_sin_medir: true })
  })
})
