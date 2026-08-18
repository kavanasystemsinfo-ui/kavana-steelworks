import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { AdminPage } from '../pages/AdminPage'

const tenantBody = {
  id: 't1',
  name: 'Demo Aceros',
  slug: 'demo',
  status: 'active',
  is_active: true,
  auth: { login_method: 'username_password', require_line_number: true },
  theme: { colors: { primary: '#e56b2e' }, branding: { companyName: 'Demo Aceros', logoUrl: '' } },
  finances: { overhead_hourly_cost: 0, operator_categories: [] },
  sequences_config: { order: { prefix: 'OP-{MM}{YY}-', padding: 3 }, lot: { prefix: 'LT-', padding: 3 } },
}

const usersBody = [
  { id: 'u1', email: 'admin@demo.local', name: 'Admin Demo', role: 'admin', is_active: true, employee_number: null, default_workstation_code: null, last_login_at: null },
  { id: 'u2', email: 'operario@demo.local', name: 'Operario Demo', role: 'operator', is_active: true, employee_number: null, default_workstation_code: 'LINEA-1', last_login_at: null },
]

const workstationsBody = [
  { id: 'w1', group_id: null, code: 'LINEA-1', name: 'Línea 1 - Corte', color: '#3498db', hourly_cost: 45, registration_method: 'quantity', maintenance_interval_hours: 0, maintenance_pre_warning_hours: 0, last_maintenance_reset: null, accumulated_hours: 0, is_active: true },
]

const rolesBody = [
  { id: 'r1', role_key: 'operator', name: 'Operario', permissions: ['stock.scan', 'stock.link'], is_system: true },
  { id: 'r2', role_key: 'admin', name: 'Admin', permissions: ['admin.users', 'admin.tenant'], is_system: true },
]

function stubApi() {
  const handler = vi.fn((url: string, init?: RequestInit) => {
    const path = url.replace('/api/v1/admin', '')
    const method = init?.method ?? 'GET'

    if (path === '/tenant' && method === 'GET') {
      return Promise.resolve({ ok: true, json: async () => tenantBody })
    }
    if (path === '/tenant' && method === 'PUT') {
      const body = JSON.parse(init?.body as string)
      return Promise.resolve({ ok: true, json: async () => ({ ...tenantBody, ...body }) })
    }
    if (path === '/users' && method === 'GET') return Promise.resolve({ ok: true, json: async () => usersBody })
    if (path === '/users' && method === 'POST') {
      const body = JSON.parse(init?.body as string)
      return Promise.resolve({ ok: true, json: async () => ({ id: 'u3', ...body }) })
    }
    if (path.startsWith('/users/') && method === 'DELETE') {
      return Promise.resolve({ ok: true, json: async () => ({ ...usersBody[1], is_active: false }) })
    }
    if (path.startsWith('/users/') && method === 'PATCH') {
      return Promise.resolve({ ok: true, json: async () => ({ ...usersBody[0], ...JSON.parse(init?.body as string) }) })
    }
    if (path === '/workstations' && method === 'GET') return Promise.resolve({ ok: true, json: async () => workstationsBody })
    if (path === '/workstations' && method === 'POST') {
      const body = JSON.parse(init?.body as string)
      return Promise.resolve({ ok: true, json: async () => ({ ...workstationsBody[0], ...body, id: 'w9' }) })
    }
    if (path === '/workstations/groups') return Promise.resolve({ ok: true, json: async () => [] })
    if (path.startsWith('/workstations/') && method === 'DELETE') {
      return Promise.resolve({ ok: true, json: async () => ({ ...workstationsBody[0], is_active: false }) })
    }
    if (path === '/roles' && method === 'GET') return Promise.resolve({ ok: true, json: async () => rolesBody })
    if (path === '/sequences' && method === 'GET') {
      return Promise.resolve({ ok: true, json: async () => tenantBody.sequences_config })
    }
    if (path === '/sequences' && method === 'PUT') {
      const body = JSON.parse(init?.body as string)
      return Promise.resolve({ ok: true, json: async () => body })
    }
    if (path === '/sequences/next/order') {
      return Promise.resolve({ ok: true, json: async () => ({ type: 'order', next: 'OP-0826-001' }) })
    }
    if (path === '/sequences/next/lot') {
      return Promise.resolve({ ok: true, json: async () => ({ type: 'lot', next: 'LT-001' }) })
    }
    return Promise.resolve({ ok: false, status: 404, json: async () => ({ detail: 'noop' }) })
  })
  vi.stubGlobal('fetch', handler)
  return handler
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminPage />
    </MemoryRouter>,
  )
}

describe('Panel de Administración (spec 07)', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
    sessionStorage.clear()
  })

  it('muestra las pestañas de gestión', () => {
    stubApi()
    renderPage()
    expect(screen.getAllByText(/empresa/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/usuarios/i)).toBeInTheDocument()
    expect(screen.getByText(/secuencias/i)).toBeInTheDocument()
    expect(screen.getByText(/puestos/i)).toBeInTheDocument()
    expect(screen.getByText(/roles/i)).toBeInTheDocument()
  })

  it('carga y muestra los datos de la empresa', async () => {
    stubApi()
    renderPage()
    expect(await screen.findAllByDisplayValue('Demo Aceros')).toHaveLength(2)
    expect(screen.getByDisplayValue('demo')).toBeInTheDocument()
  })

  it('guarda los cambios de la empresa con PUT', async () => {
    const fetchMock = stubApi()
    const user = userEvent.setup()
    renderPage()

    await screen.findAllByDisplayValue('Demo Aceros')
    const nameInputs = screen.getAllByDisplayValue('Demo Aceros')
    fireEvent.change(nameInputs[0], { target: { value: 'Nueva Empresa S.A.' } })
    await user.click(screen.getByRole('button', { name: /guardar/i }))

    await waitFor(() => {
      const putCall = fetchMock.mock.calls.find(
        ([url, init]) => url.endsWith('/tenant') && init?.method === 'PUT',
      )
      expect(putCall).toBeTruthy()
      const body = JSON.parse(String(putCall?.[1]?.body ?? '{}'))
      expect(body.name).toBe('Nueva Empresa S.A.')
    })
  })

  it('lista los usuarios y elimina uno (soft delete vía DELETE)', async () => {
    const fetchMock = stubApi()
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByText(/usuarios/i))
    expect(await screen.findByText('admin@demo.local')).toBeInTheDocument()
    expect(screen.getByText('operario@demo.local')).toBeInTheDocument()

    const eliminarButtons = screen.getAllByRole('button', { name: /eliminar/i })
    await user.click(eliminarButtons[0])

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) => url.includes('/users/') && init?.method === 'DELETE',
        ),
      ).toBe(true)
    })
  })

  it('crea un usuario nuevo vía POST', async () => {
    const fetchMock = stubApi()
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByText(/usuarios/i))
    await user.type(screen.getByLabelText(/email/i), 'nuevo@demo.local')
    await user.type(screen.getByLabelText(/nombre/i), 'Nuevo Usuario')
    await user.type(screen.getByLabelText(/password inicial/i), 'clave123')
    await user.click(screen.getByRole('button', { name: /crear usuario/i }))

    await waitFor(() => {
      const postCall = fetchMock.mock.calls.find(
        ([url, init]) => url.endsWith('/users') && init?.method === 'POST',
      )
      expect(postCall).toBeTruthy()
      const body = JSON.parse(String(postCall?.[1]?.body ?? '{}'))
      expect(body.email).toBe('nuevo@demo.local')
      expect(body.password).toBe('clave123')
    })
  })

  it('muestra las secuencias y su siguiente número', async () => {
    stubApi()
    renderPage()

    await userEvent.setup().click(screen.getByText(/secuencias/i))
    expect(await screen.findByDisplayValue('OP-0826-001')).toBeInTheDocument()
    expect(screen.getByDisplayValue('LT-001')).toBeInTheDocument()
  })

  it('lista los puestos de trabajo', async () => {
    stubApi()
    renderPage()

    await userEvent.setup().click(screen.getByText(/puestos/i))
    expect(await screen.findByText('LINEA-1')).toBeInTheDocument()
    expect(screen.getByText('Línea 1 - Corte')).toBeInTheDocument()
  })

  it('lista roles y marca los del sistema', async () => {
    stubApi()
    renderPage()

    await userEvent.setup().click(screen.getByText(/roles/i))
    expect(await screen.findByText('operator')).toBeInTheDocument()
    expect(screen.getAllByText('admin').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('sistema').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('stock.scan')).toBeInTheDocument()
  })
})