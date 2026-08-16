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

  it('sin token redirige a /login', () => {
    renderApp('/operario')
    expect(screen.getByText(/KAVANA Steelworks/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /entrar/i })).toBeInTheDocument()
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
    expect(screen.getByText(/oee/i)).toBeInTheDocument()
    expect(screen.queryByText(/vincular bobina/i)).not.toBeInTheDocument()
  })

  it('admin ve el nav completo (hereda supervisor)', () => {
    sessionStorage.setItem('kavana_token', makeToken('admin'))
    renderApp('/supervisor')
    expect(screen.getByText(/oee/i)).toBeInTheDocument()
    expect(screen.getByText(/operario/i)).toBeInTheDocument()
    expect(screen.getByText(/materias primas/i)).toBeInTheDocument()
  })

  it('login redirige al panel según rol y guarda el token', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'login').mockResolvedValue({
      access_token: makeToken('supervisor'),
      token_type: 'bearer',
    })
    renderApp('/login')
    await user.type(screen.getByLabelText(/usuario/i), 'supervisor@demo.local')
    await user.type(screen.getByLabelText(/contraseña/i), 'kavana')
    await user.click(screen.getByRole('button', { name: /entrar/i }))
    expect(await screen.findByText(/oee/i)).toBeInTheDocument()
    expect(sessionStorage.getItem('kavana_token')).toBeTruthy()
  })

  it('muestra credenciales demo en el login para entrar fácil', () => {
    renderApp('/login')
    expect(screen.getByText(/operario@demo.local/)).toBeInTheDocument()
    expect(screen.getByText(/supervisor@demo.local/)).toBeInTheDocument()
    expect(screen.getByText(/materias@demo.local/)).toBeInTheDocument()
  })
})
