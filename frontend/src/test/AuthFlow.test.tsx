import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { api } from '../lib/api'

function makeToken(role: string): string {
  const payload = { sub: 'u1', tenant_id: 't1', role, exp: 9999999999 }
  const b64 = btoa(JSON.stringify(payload))
  return `header.${b64}.firma`
}

function renderApp(route = '/operario') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <App />
    </MemoryRouter>,
  )
}

describe('Guard de rutas por rol (Fase 6)', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  it('sin token redirige a /login', async () => {
    renderApp('/operario')
    expect(screen.getByText(/KAVANA Steelworks/)).toBeInTheDocument()
    // Just verify we can find the login form (it's async due to redirect)
    await screen.findByText(/Acceso rápido a la demo \(sin credenciales\)/i)
  })

  it('operario entra en /operario y no ve el nav de supervisor', () => {
    sessionStorage.setItem('kavana_token', makeToken('operator'))
    renderApp('/operario')
    expect(screen.getByText(/vincular bobina/i)).toBeInTheDocument()
    expect(screen.queryByText(/supervisor/i)).not.toBeInTheDocument()
  })

  it('materias no puede ver /operario y cae a /materias-primas', () => {
    sessionStorage.setItem('kavana_token', makeToken('materials'))
    renderApp('/operario')
    expect(screen.getByText(/materias primas/i)).toBeInTheDocument()
  })

  it('supervisor ve /supervisor y no los paneles de operario', () => {
    sessionStorage.setItem('kavana_token', makeToken('supervisor'))
    renderApp('/supervisor')
    expect(screen.getByRole('navigation', { name: 'Vistas del panel' })).toBeInTheDocument()
    expect(screen.queryByText(/vincular bobina/i)).not.toBeInTheDocument()
  })

  it('supervisor NO puede entrar a /operario ni ve los otros paneles', () => {
    sessionStorage.setItem('kavana_token', makeToken('supervisor'))
    renderApp('/operario')
    expect(screen.getByRole('navigation', { name: 'Vistas del panel' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /operario/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /materias primas/i })).not.toBeInTheDocument()
  })

  it('admin NO puede entrar a /supervisor y cae a /admin', () => {
    sessionStorage.setItem('kavana_token', makeToken('admin'))
    renderApp('/supervisor')
    expect(screen.queryByRole('navigation', { name: 'Vistas del panel' })).not.toBeInTheDocument()
    expect(screen.getByText(/usuarios/i)).toBeInTheDocument()
  })

  it('admin entra al panel /admin y ve la gestión de empresa', () => {
    sessionStorage.setItem('kavana_token', makeToken('admin'))
    renderApp('/admin')
    expect(screen.getAllByText(/empresa/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/usuarios/i)).toBeInTheDocument()
    expect(screen.getByText(/secuencias/i)).toBeInTheDocument()
    expect(screen.getByText(/puestos/i)).toBeInTheDocument()
    expect(screen.getByText(/roles/i)).toBeInTheDocument()
  })

  it('supervisor NO puede entrar a /admin y cae a su home', () => {
    sessionStorage.setItem('kavana_token', makeToken('supervisor'))
    renderApp('/admin')
    expect(screen.getByRole('navigation', { name: 'Vistas del panel' })).toBeInTheDocument()
    expect(screen.queryByText(/gestión de empresa/i)).not.toBeInTheDocument()
  })

  it('login redirige al panel según rol y guarda el token', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'login').mockResolvedValue({
      access_token: makeToken('supervisor'),
      token_type: 'bearer',
    })
    renderApp('/login')
    // Click "Tengo cuenta propia" to show the credentials form
    await user.click(screen.getByRole('button', { name: /Tengo cuenta propia/i }))
    await user.type(screen.getByLabelText(/Usuario/i), 'supervisor@demo.local')
    await user.type(screen.getByLabelText(/Contraseña/i), 'kavana')
    await user.click(screen.getByRole('button', { name: /Entrar/i }))
    expect(await screen.findByRole('navigation', { name: 'Vistas del panel' })).toBeInTheDocument()
    expect(sessionStorage.getItem('kavana_token')).toBeTruthy()
  })

  it('muestra botones de acceso rápido a la demo en el login', () => {
    renderApp('/login')
    expect(screen.getByText('Acceso rápido a la demo (sin credenciales)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Operario/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Supervisor/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Materias Primas/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Admin/i })).toBeInTheDocument()
  })
})
