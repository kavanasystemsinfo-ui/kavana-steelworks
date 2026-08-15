import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { OperarioPage } from '../pages/OperarioPage'

function renderPage() {
  return render(
    <MemoryRouter>
      <OperarioPage />
    </MemoryRouter>,
  )
}

describe('Panel de Operario (directriz no abrumar)', () => {
  it('muestra la guía de acción clara al inicio', () => {
    renderPage()
    expect(screen.getByText('Vincular bobina')).toBeInTheDocument()
    expect(screen.getByText('Paso actual')).toBeInTheDocument()
  })

  it('tiene el botón de escaneo grande y deshabilitado sin código', () => {
    renderPage()
    const boton = screen.getByRole('button', { name: /escanear bobina/i })
    expect(boton).toBeDisabled()
  })

  it('habilita el escaneo al escribir un código de bobina', async () => {
    const user = userEvent.setup()
    renderPage()
    const input = screen.getByPlaceholderText(/escanea la etiqueta/i)
    await user.type(input, 'COIL-123')
    const boton = screen.getByRole('button', { name: /escanear bobina/i })
    expect(boton).toBeEnabled()
  })

  it('muestra error si la bobina no existe', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => null,
    }))
    renderPage()
    const input = screen.getByPlaceholderText(/escanea la etiqueta/i)
    await user.type(input, 'NO-EXISTE')
    await user.click(screen.getByRole('button', { name: /escanear bobina/i }))
    expect(
      await screen.findByText(/bobina no encontrada/i),
    ).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('al escanear, muestra la ficha de la bobina con sus datos', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 'bobina-1',
        lote: 'L-DEMO',
        coil_id: 'COIL-L-DEMO',
        peso_kg: 800,
        ancho_mm: 122,
        espesor_mm: 0.5,
        material_code: 'ACERO-01',
        material_name: 'Bobina Acero',
        estado: 'activo',
        ubicacion: 'ALMACEN-1',
        modo: 'auto',
      }),
    }))
    renderPage()
    const input = screen.getByPlaceholderText(/escanea la etiqueta/i)
    await user.type(input, 'COIL-L-DEMO')
    await user.click(screen.getByRole('button', { name: /escanear bobina/i }))

    expect(await screen.findByText('COIL-L-DEMO')).toBeInTheDocument()
    expect(screen.getByText('ACERO-01')).toBeInTheDocument()
    expect(screen.getByText('800 kg')).toBeInTheDocument()
    expect(screen.getByText('122 x 0.5 mm')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /vincular a mi orden/i }),
    ).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('los datos de apoyo están colapsados (no abruman al operario)', () => {
    renderPage()
    const detalles = screen.getByText('Detalles de la orden')
    expect(detalles).toBeInTheDocument()
    expect(detalles.closest('summary')).toBeTruthy()
  })

  it('tras vincular, el fin de bobina pide radio en mm y hay botón Retirar', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 'bobina-1',
        lote: 'L-DEMO',
        coil_id: 'COIL-L-DEMO',
        peso_kg: 800,
        ancho_mm: 122,
        espesor_mm: 0.5,
        material_code: 'ACERO-01',
        material_name: 'Bobina Acero',
        estado: 'activo',
        ubicacion: 'ALMACEN-1',
        modo: 'auto',
      }),
    }))
    renderPage()
    const input = screen.getByPlaceholderText(/escanea la etiqueta/i)
    await user.type(input, 'COIL-L-DEMO')
    await user.click(screen.getByRole('button', { name: /escanear bobina/i }))
    const botonVincular = await screen.findByRole('button', { name: /vincular a mi orden/i })
    // El flujo de demo: vincular muestra el panel de producción
    await user.click(botonVincular)
    expect(
      await screen.findByPlaceholderText(/radio restante/i),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /retirar pico a inventario/i }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /registrar piezas/i }),
    ).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('registrar piezas llama a /api/v1/production/record', async () => {
    const user = userEvent.setup()
    const bobina = {
      id: 'bobina-1',
      lote: 'L-DEMO',
      coil_id: 'COIL-L-DEMO',
      peso_kg: 800,
      ancho_mm: 122,
      espesor_mm: 0.5,
      material_code: 'ACERO-01',
      material_name: 'Bobina Acero',
      estado: 'activo',
      ubicacion: 'ALMACEN-1',
      modo: 'auto',
    }
    const fetchMock = vi.fn((url: string) => {
      if (url.includes('/scan')) {
        return Promise.resolve({ ok: true, json: async () => bobina })
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({
          incremental_quantity: 5,
          consumed_amount: 4.75,
          consumption_unit: 'kg',
          calculation_method: 'density_formula',
        }),
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    renderPage()
    const input = screen.getByPlaceholderText(/escanea la etiqueta/i)
    await user.type(input, 'COIL-L-DEMO')
    await user.click(screen.getByRole('button', { name: /escanear bobina/i }))
    await user.click(
      await screen.findByRole('button', { name: /vincular a mi orden/i }),
    )

    const piezas = await screen.findByPlaceholderText(/piezas/i)
    await user.type(piezas, '5')
    await user.click(screen.getByRole('button', { name: /registrar piezas/i }))

    const llamadas = fetchMock.mock.calls.map((c) => c[0])
    expect(llamadas).toContain('/api/v1/production/record')
    expect(
      await screen.findByText(/5 piezas registradas/i),
    ).toBeInTheDocument()
    vi.unstubAllGlobals()
  })
})

const bobinaDemo = {
  id: 'bobina-1',
  lote: 'L-DEMO',
  coil_id: 'COIL-L-DEMO',
  peso_kg: 800,
  ancho_mm: 122,
  espesor_mm: 0.5,
  material_code: 'ACERO-01',
  material_name: 'Bobina Acero',
  estado: 'activo',
  ubicacion: 'ALMACEN-1',
  modo: 'auto',
}

const modeloDemo = {
  id: 'M1',
  code: 'PERFIL-DEMO-001',
  name: 'Perfil decapado 1.2x1220',
  material_code: 'ACERO-DC01',
  quality_plan: [
    { id: 'c1', name: 'Largo Total', tipo: 'numeric', tool_id: 'Cinta métrica', nominal_value: 2000, tolerance_plus: 10, tolerance_minus: 10, is_critical: true },
    { id: 'c2', name: 'Acabado superficial', tipo: 'visual', tool_id: null, nominal_value: null, tolerance_plus: null, tolerance_minus: null, is_critical: true },
    { id: 'c3', name: 'Espesor', tipo: 'numeric', tool_id: 'Micrómetro', nominal_value: 1.2, tolerance_plus: 0.1, tolerance_minus: 0.1, is_critical: true },
  ],
}

function stubAutocontrol(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal('fetch', fetchMock)
}

async function vincularBobina(user: ReturnType<typeof userEvent.setup>) {
  const input = screen.getByPlaceholderText(/escanea la etiqueta/i)
  await user.type(input, 'COIL-L-DEMO')
  await user.click(screen.getByRole('button', { name: /escanear bobina/i }))
  await user.click(
    await screen.findByRole('button', { name: /vincular a mi orden/i }),
  )
}

describe('Autocontrol de calidad (spec 04)', () => {
  it('tras vincular, muestra el formulario con los checks del plan', async () => {
    const user = userEvent.setup()
    stubAutocontrol(
      vi.fn((url: string) => {
        if (url.includes('/scan')) {
          return Promise.resolve({ ok: true, json: async () => bobinaDemo })
        }
        if (url.includes('/api/v1/orders')) {
          return Promise.resolve({
            ok: true,
            json: async () => [
              { id: 'OP1', numero: 'OP-DEMO-001', estado: 'active', cliente: null, fecha_entrega: null, workstation_id: 'LINEA-1' },
            ],
          })
        }
        if (url.includes('/api/v1/quality/models')) {
          return Promise.resolve({ ok: true, json: async () => [modeloDemo] })
        }
        return Promise.resolve({ ok: true, json: async () => ({}) })
      }),
    )
    renderPage()
    await vincularBobina(user)

    expect(await screen.findByText('Autocontrol de calidad')).toBeInTheDocument()
    expect(screen.getByLabelText(/Largo Total/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Espesor/)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Aprobar Acabado superficial' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Rechazar Acabado superficial' }),
    ).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('registra un autocontrol aprobado y muestra el resultado', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.includes('/scan')) {
        return Promise.resolve({ ok: true, json: async () => bobinaDemo })
      }
      if (url.includes('/api/v1/orders')) {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { id: 'OP1', numero: 'OP-DEMO-001', estado: 'active', cliente: null, fecha_entrega: null, workstation_id: 'LINEA-1' },
          ],
        })
      }
      if (url.includes('/api/v1/quality/models')) {
        return Promise.resolve({ ok: true, json: async () => [modeloDemo] })
      }
      if (url.includes('/api/v1/quality/checks')) {
        const body = JSON.parse(init?.body as string)
        expect(body.order_id).toBe('OP1')
        expect(body.workstation_id).toBe('LINEA-1')
        expect(body.measurements).toEqual([
          { check_name: 'Largo Total', value_entered: 1990 },
          { check_name: 'Acabado superficial', value_entered: true },
          { check_name: 'Espesor', value_entered: 1.2 },
        ])
        return Promise.resolve({
          ok: true,
          json: async () => ({
            msg: 'Inspección registrada: APPROVED',
            record: { overall_status: 'approved' },
          }),
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })
    stubAutocontrol(fetchMock)
    renderPage()
    await vincularBobina(user)

    const largo = await screen.findByLabelText(/Largo Total/)
    await user.type(largo, '1990')
    await user.click(
      screen.getByRole('button', { name: 'Aprobar Acabado superficial' }),
    )
    const espesor = screen.getByLabelText(/Espesor/)
    await user.type(espesor, '1.2')
    await user.click(screen.getByRole('button', { name: /registrar autocontrol/i }))

    expect(await screen.findByText('Aprobado')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('un autocontrol rechazado se registra igual y no bloquea', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn((url: string) => {
      if (url.includes('/scan')) {
        return Promise.resolve({ ok: true, json: async () => bobinaDemo })
      }
      if (url.includes('/api/v1/orders')) {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { id: 'OP1', numero: 'OP-DEMO-001', estado: 'active', cliente: null, fecha_entrega: null, workstation_id: 'LINEA-1' },
          ],
        })
      }
      if (url.includes('/api/v1/quality/models')) {
        return Promise.resolve({ ok: true, json: async () => [modeloDemo] })
      }
      if (url.includes('/api/v1/quality/checks')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            msg: 'Inspección registrada: REJECTED',
            record: { overall_status: 'rejected' },
          }),
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })
    stubAutocontrol(fetchMock)
    renderPage()
    await vincularBobina(user)

    const largo = await screen.findByLabelText(/Largo Total/)
    await user.type(largo, '9999')
    await user.click(
      screen.getByRole('button', { name: 'Rechazar Acabado superficial' }),
    )
    await user.click(screen.getByRole('button', { name: /registrar autocontrol/i }))

    expect(
      await screen.findByText(/Rechazado \(no bloquea la producción\)/i),
    ).toBeInTheDocument()
    vi.unstubAllGlobals()
  })
})

describe('Reportar incidencia (spec 04 §3.3)', () => {
  function stubReporte(
    onBody: (body: Record<string, unknown>) => void,
  ) {
    return vi.fn((url: string, init?: RequestInit) => {
      if (url.includes('/scan')) {
        return Promise.resolve({ ok: true, json: async () => bobinaDemo })
      }
      if (url.includes('/api/v1/orders')) {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { id: 'OP1', numero: 'OP-DEMO-001', estado: 'active', cliente: null, fecha_entrega: null, workstation_id: 'LINEA-1' },
          ],
        })
      }
      if (url.includes('/api/v1/quality/models')) {
        return Promise.resolve({ ok: true, json: async () => [modeloDemo] })
      }
      if (url.includes('/upload-session')) {
        if (init?.method === 'POST') {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              session_id: 'SES-DEMO',
              status: 'pending',
              expires_at: '2026-08-15T23:00:00Z',
              has_photo: false,
              incidencia_id: null,
            }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({
            session_id: 'SES-DEMO',
            status: 'pending',
            expires_at: '2026-08-15T23:00:00Z',
            has_photo: false,
            incidencia_id: null,
            photo_data_url: null,
          }),
        })
      }
      if (url.includes('/api/v1/incidencias')) {
        onBody(JSON.parse(init?.body as string))
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, msg: 'Incidencia registrada' }),
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })
  }

  it('formulario clásico: auto-importa operario, puesto, modelo y fecha', async () => {
    const user = userEvent.setup()
    const captura: { body: Record<string, unknown> | null } = { body: null }
    vi.stubGlobal('fetch', stubReporte((b) => { captura.body = b }))
    renderPage()

    await user.click(
      await screen.findByRole('button', { name: /reportar incidencia/i }),
    )

    // Datos auto-importados visibles en el formulario
    expect(await screen.findByText('Operario Demo')).toBeInTheDocument()
    expect(screen.getByText('LINEA-1')).toBeInTheDocument()
    expect(
      screen.getByText(`Perfil decapado 1.2x1220 · PERFIL-DEMO-001`),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /adjuntar foto/i }),
    ).toBeInTheDocument()
    // Sin foto: el QR NO se genera al abrir (la sesión no se crea sola)
    expect(screen.queryByTitle('QR de subida de foto')).not.toBeInTheDocument()

    const obs = await screen.findByPlaceholderText(/detalla la incidencia/i)
    await user.type(obs, 'Atasco en la cizalla')
    await user.selectOptions(screen.getByLabelText(/tipo de incidencia/i), 'maquina')
    await user.click(screen.getByRole('button', { name: /enviar incidencia/i }))

    expect(await screen.findByText('Incidencia registrada')).toBeInTheDocument()
    expect(captura.body).toMatchObject({ linea_id: 'LINEA-1', descripcion: 'Atasco en la cizalla', tipo: 'maquina' })
    expect(captura.body?.photo_session_id).toBeNull()
    vi.unstubAllGlobals()
  })

  it('con foto: la sesión QR se crea solo al pulsar Adjuntar foto y se envía', async () => {
    const user = userEvent.setup()
    const fetchMock = stubReporte((b) => {
      expect(b.photo_session_id).toBe('SES-DEMO')
    })
    vi.stubGlobal('fetch', fetchMock)
    renderPage()

    await user.click(
      await screen.findByRole('button', { name: /reportar incidencia/i }),
    )

    const obs = await screen.findByPlaceholderText(/detalla la incidencia/i)
    await user.type(obs, 'Atasco en la cizalla')
    await user.selectOptions(screen.getByLabelText(/tipo de incidencia/i), 'maquina')

    // El QR solo aparece cuando el operario decide adjuntar foto
    await user.click(screen.getByRole('button', { name: /adjuntar foto \(opcional\)/i }))
    expect(await screen.findByText('Escanea con tu móvil')).toBeInTheDocument()
    expect(await screen.findByTitle('QR de subida de foto')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /enviar incidencia/i }))

    expect(await screen.findByText('Incidencia registrada')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('Quitar foto vuelve al formulario y la incidencia se envía sin foto', async () => {
    const user = userEvent.setup()
    const captura: { body: Record<string, unknown> | null } = { body: null }
    const fetchMock = stubReporte((b) => { captura.body = b })
    // Subida móvil simulada: el polling encuentra la foto
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/upload-session')) {
        if (init?.method === 'POST') {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              session_id: 'SES-DEMO',
              status: 'pending',
              expires_at: '2026-08-15T23:00:00Z',
              has_photo: false,
              incidencia_id: null,
            }),
          })
        }
        // GET: el polling ya encuentra la foto subida desde el móvil
        return Promise.resolve({
          ok: true,
          json: async () => ({
            session_id: 'SES-DEMO',
            status: 'uploaded',
            expires_at: '2026-08-15T23:00:00Z',
            has_photo: true,
            incidencia_id: null,
            photo_data_url: 'data:image/png;base64,AAAA',
          }),
        })
      }
      if (url.includes('/api/v1/incidencias')) {
        captura.body = JSON.parse(init?.body as string)
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, msg: 'Incidencia registrada' }),
        })
      }
      return stubReporte(() => {})(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)
    renderPage()

    await user.click(
      await screen.findByRole('button', { name: /reportar incidencia/i }),
    )
    const obs = await screen.findByPlaceholderText(/detalla la incidencia/i)
    await user.type(obs, 'Atasco en la cizalla')

    await user.click(screen.getByRole('button', { name: /adjuntar foto \(opcional\)/i }))
    // El polling tarda 2s en encontrar la foto (el stub devuelve uploaded)
    expect(
      await screen.findByText('Foto recibida', {}, { timeout: 3000 }),
    ).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /quitar foto/i }))

    expect(
      screen.getByRole('button', { name: /adjuntar foto \(opcional\)/i }),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /enviar incidencia/i }))

    expect(await screen.findByText('Incidencia registrada')).toBeInTheDocument()
    expect(captura.body?.photo_session_id).toBeNull()
    vi.unstubAllGlobals()
  })
})
