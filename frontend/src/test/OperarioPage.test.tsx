import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { OperarioPage } from '../pages/OperarioPage'
import { MockWebSocket } from './mockWebSocket'

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
    let fetchMock: ReturnType<typeof vi.fn>
    vi.stubGlobal('fetch', fetchMock = vi.fn((url: string) => {
      if (url.includes('/scan')) {
        return Promise.resolve({
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
        })
      }
      if (url.includes('/api/v1/orders/OP1')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: 'OP1',
            numero: 'OP-DEMO-001',
            estado: 'active',
            cliente: null,
            fecha_entrega: null,
            workstation_id: 'LINEA-1',
            lines: [
              {
                id: 'line-1',
                linea_numero: 1,
                workstation_id: 'LINEA-1',
                estado: 'pending',
                total_quantity: 50,
                produced_quantity: 0,
                material_id: 'mat-1',
                active_coil_id: null,
                active_coil_code: null,
                real_material_qty: 0,
                real_material_cost: 0,
                real_cost: 0,
                scrap_material_qty: 0,
                target_material_qty: 100,
                target_material_unit: 'kg',
                meters_per_piece: 2.0,
              },
            ],
          }),
        })
      }
      if (url === '/api/v1/orders/available') {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { id: 'OP1', numero: 'OP-DEMO-001', estado: 'active', cliente: null, fecha_entrega: null, workstation_id: 'LINEA-1' },
          ],
        })
      }
      if (url.includes('/stock-items/link')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, coil_weight: 800, order: 'OP1' }),
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    }))
    renderPage()
    // Wait for initial data fetch: list orders and get order
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([u]) => u.includes('/api/v1/orders/OP1'))).toBe(true)
    })
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
    const fetchMock = vi.fn((url: string, _init?: RequestInit) => {
        if (url.includes('/scan')) {
          return Promise.resolve({ ok: true, json: async () => bobina })
        }
        if (url.includes('/api/v1/orders/OP1')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              id: 'OP1',
              numero: 'OP-DEMO-001',
              estado: 'active',
              cliente: null,
              fecha_entrega: null,
              workstation_id: 'LINEA-1',
              lines: [
                {
                  id: 'line-1',
                  linea_numero: 1,
                  workstation_id: 'LINEA-1',
                  estado: 'pending',
                  total_quantity: 50,
                  produced_quantity: 0,
                  material_id: 'mat-1',
                  active_coil_id: null,
                  active_coil_code: null,
                  real_material_qty: 0,
                  real_material_cost: 0,
                  real_cost: 0,
                  scrap_material_qty: 0,
                  target_material_qty: 100,
                  target_material_unit: 'kg',
                  meters_per_piece: 2.0,
                },
              ],
            }),
          })
        }
        if (url === '/api/v1/orders/available') {
          return Promise.resolve({
            ok: true,
            json: async () => [
              { id: 'OP1', numero: 'OP-DEMO-001', estado: 'active', cliente: null, fecha_entrega: null, workstation_id: 'LINEA-1' },
            ],
          })
        }
        if (url.includes('/stock-items/link')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ success: true, coil_weight: 800, order: 'OP1' }),
          })
        }
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

  it('el numpad táctil rellena piezas y registra producción', async () => {
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
    const fetchMock = vi.fn((url: string, _init?: RequestInit) => {
      if (url.includes('/scan')) {
        return Promise.resolve({ ok: true, json: async () => bobina })
      }
      if (url.includes('/api/v1/orders/OP1')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: 'OP1',
            numero: 'OP-DEMO-001',
            estado: 'active',
            cliente: null,
            fecha_entrega: null,
            workstation_id: 'LINEA-1',
            lines: [
              {
                id: 'line-1',
                linea_numero: 1,
                workstation_id: 'LINEA-1',
                estado: 'pending',
                total_quantity: 50,
                produced_quantity: 0,
                material_id: 'mat-1',
                active_coil_id: null,
                active_coil_code: null,
                real_material_qty: 0,
                real_material_cost: 0,
                real_cost: 0,
                scrap_material_qty: 0,
                target_material_qty: 100,
                target_material_unit: 'kg',
                meters_per_piece: 2.0,
              },
            ],
          }),
        })
      }
      if (url === '/api/v1/orders/available') {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { id: 'OP1', numero: 'OP-DEMO-001', estado: 'active', cliente: null, fecha_entrega: null, workstation_id: 'LINEA-1' },
          ],
        })
      }
      if (url.includes('/stock-items/link')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, coil_weight: 800, order: 'OP1' }),
        })
      }
      if (url.includes('/production/record')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            incremental_quantity: 75,
            consumed_amount: 71.25,
            consumption_unit: 'kg',
            calculation_method: 'density_formula',
          }),
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
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
    await user.click(screen.getByRole('button', { name: '7' }))
    await user.click(screen.getByRole('button', { name: '5' }))
    expect(piezas).toHaveValue(75)

    await user.click(screen.getByRole('button', { name: /registrar piezas/i }))
    const recordCall = fetchMock.mock.calls.find(([u]) =>
      String(u).includes('/production/record'),
    )
    expect(recordCall).toBeTruthy()
    const body = JSON.parse(String(recordCall?.[1]?.body))
    expect(body.incremental_quantity).toBe(75)
    expect(
      await screen.findByText(/75 piezas registradas/i),
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
        // Check exact URLs to avoid partial matches - order matters!
        if (url.includes('/api/v1/orders/OP1')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              id: 'OP1',
              numero: 'OP-DEMO-001',
              estado: 'active',
              cliente: null,
              fecha_entrega: null,
              workstation_id: 'LINEA-1',
              lines: [
                {
                  id: 'line-1',
                  linea_numero: 1,
                  workstation_id: 'LINEA-1',
                  estado: 'pending',
                  total_quantity: 50,
                  produced_quantity: 0,
                  material_id: 'mat-1',
                  active_coil_id: null,
                  active_coil_code: null,
                  real_material_qty: 0,
                  real_material_cost: 0,
                  real_cost: 0,
                  scrap_material_qty: 0,
                  target_material_qty: 100,
                  target_material_unit: 'kg',
                  meters_per_piece: 2.0,
                },
              ],
            }),
          })
        }
        if (url === '/api/v1/orders/available') {
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
        if (url.includes('/stock-items/link')) {
          return Promise.resolve({ ok: true, json: async () => ({ success: true, coil_weight: 800, order: 'OP1' }) })
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
      // Order matters: check specific URL first
      if (url.includes('/api/v1/orders/OP1')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: 'OP1',
            numero: 'OP-DEMO-001',
            estado: 'active',
            cliente: null,
            fecha_entrega: null,
            workstation_id: 'LINEA-1',
            lines: [
              {
                id: 'line-1',
                linea_numero: 1,
                workstation_id: 'LINEA-1',
                estado: 'pending',
                total_quantity: 50,
                produced_quantity: 0,
                material_id: 'mat-1',
                active_coil_id: null,
                active_coil_code: null,
                real_material_qty: 0,
                real_material_cost: 0,
                real_cost: 0,
                scrap_material_qty: 0,
                target_material_qty: 100,
                target_material_unit: 'kg',
                meters_per_piece: 2.0,
              },
            ],
          }),
        })
      }
      if (url === '/api/v1/orders/available') {
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
      if (url.includes('/stock-items/link')) {
        return Promise.resolve({ ok: true, json: async () => ({ success: true, coil_weight: 800, order: 'OP1' }) })
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
    // Wait for initial data fetch: list orders and get order
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([u]) => u.includes('/api/v1/orders/OP1'))).toBe(true)
    })
    await vincularBobina(user)

    const largo = await screen.findByLabelText(/Largo Total/)
    await user.type(largo, '1990')
    await user.click(
      screen.getByRole('button', { name: 'Aprobar Acabado superficial' }),
    )
    const espesor = screen.getByLabelText(/Espesor/)
    await user.type(espesor, '1.2')
    await user.click(screen.getByRole('button', { name: /registrar autocontrol/i }))

    expect(await screen.findByText(/Aprobado/i)).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('un autocontrol rechazado se registra igual y no bloquea', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn((url: string) => {
      if (url.includes('/scan')) {
        return Promise.resolve({ ok: true, json: async () => bobinaDemo })
      }
      // Order matters: check specific URL first
      if (url.includes('/api/v1/orders/OP1')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: 'OP1',
            numero: 'OP-DEMO-001',
            estado: 'active',
            cliente: null,
            fecha_entrega: null,
            workstation_id: 'LINEA-1',
            lines: [
              {
                id: 'line-1',
                linea_numero: 1,
                workstation_id: 'LINEA-1',
                estado: 'pending',
                total_quantity: 50,
                produced_quantity: 0,
                material_id: 'mat-1',
                active_coil_id: null,
                active_coil_code: null,
                real_material_qty: 0,
                real_material_cost: 0,
                real_cost: 0,
                scrap_material_qty: 0,
                target_material_qty: 100,
                target_material_unit: 'kg',
                meters_per_piece: 2.0,
              },
            ],
          }),
        })
      }
      if (url === '/api/v1/orders/available') {
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
      if (url.includes('/api/v1/orders/OP1')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: 'OP1',
            numero: 'OP-DEMO-001',
            estado: 'active',
            cliente: null,
            fecha_entrega: null,
            workstation_id: 'LINEA-1',
            lines: [
              {
                id: 'line-1',
                linea_numero: 1,
                workstation_id: 'LINEA-1',
                estado: 'pending',
                total_quantity: 50,
                produced_quantity: 0,
                material_id: 'mat-1',
                active_coil_id: null,
                active_coil_code: null,
                real_material_qty: 0,
                real_material_cost: 0,
                real_cost: 0,
                scrap_material_qty: 0,
                target_material_qty: 100,
                target_material_unit: 'kg',
                meters_per_piece: 2.0,
              },
            ],
          }),
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
              sessionId: 'SES-DEMO',
              status: 'pending',
              expiresAt: '2026-08-15T23:00:00Z',
              hasPhoto: false,
              incidenciaId: null,
            }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({
            sessionId: 'SES-DEMO',
            status: 'pending',
            expiresAt: '2026-08-15T23:00:00Z',
            hasPhoto: false,
            incidenciaId: null,
            photoDataUrl: null,
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

describe('Alertas de almacén por WebSocket (ADR-014)', () => {
  const tokenDemo = (() => {
    const b64 = (s: string) =>
      btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
    const payload = JSON.stringify({
      sub: 'u1',
      tenant_id: 'T1',
      role: 'operator',
      exp: 9999999999,
    })
    return `x.${b64(payload)}.sig`
  })()
  const eventoWs = {
    id: 'e1',
    tipo: 'consumo_fifo',
    data: { kg: 30 },
    timestamp: '2026-08-15T10:00:00Z',
  }
  const eventoRest = {
    id: 'e2',
    tipo: 'stock_deficit',
    data: { kg: 12 },
    timestamp: '2026-08-15T10:05:00Z',
  }

  function stubFetch() {
    return vi.fn((url: string) => {
      if (url.includes('/api/v1/quality/models')) {
        return Promise.resolve({ ok: true, json: async () => [modeloDemo] })
      }
      if (url.includes('/api/v1/orders')) {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { id: 'OP1', numero: 'OP-DEMO-001', estado: 'active', cliente: null, fecha_entrega: null, workstation_id: 'LINEA-1' },
          ],
        })
      }
      if (url.includes('/api/v1/events/')) {
        return Promise.resolve({ ok: true, json: async () => ({ events: [eventoRest] }) })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })
  }

  beforeEach(() => {
    sessionStorage.clear()
    sessionStorage.setItem('kavana_token', tokenDemo)
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    sessionStorage.clear()
  })

  it('muestra los eventos recibidos por WebSocket y el badge En vivo, sin polling', async () => {
    const fetchMock = stubFetch()
    vi.stubGlobal('fetch', fetchMock)
    renderPage()
    const ws = MockWebSocket.instances.at(-1)!
    expect(ws.url).toContain('/api/v1/ws/events?tenant_id=T1')

    act(() => ws.mensaje({ type: 'hello', tenant_id: 'T1', queued: 1 }))
    act(() => ws.mensaje({ type: 'events', events: [eventoWs] }))

    expect(screen.getByText('En vivo')).toBeInTheDocument()
    expect(screen.getByText('consumo_fifo')).toBeInTheDocument()
    // El polling de 5 s desaparece: el fallback REST no llega a arrancar
    const llamadas = fetchMock.mock.calls.map((c) => String(c[0]))
    expect(llamadas.filter((u) => u.includes('/api/v1/events/'))).toHaveLength(0)
  })

  it('muestra Reconectando... cuando se cae la conexión', async () => {
    const fetchMock = stubFetch()
    vi.stubGlobal('fetch', fetchMock)
    renderPage()
    const ws = MockWebSocket.instances.at(-1)!
    act(() => ws.mensaje({ type: 'hello', tenant_id: 'T1', queued: 0 }))
    expect(screen.getByText('En vivo')).toBeInTheDocument()

    act(() => ws.cerrarServidor())

    expect(screen.getByText('Reconectando...')).toBeInTheDocument()
  })

  it('cae al polling REST si el WebSocket nunca conecta (fallback honesto)', async () => {
    const fetchMock = stubFetch()
    vi.stubGlobal('fetch', fetchMock)
    renderPage()
    const ws = MockWebSocket.instances.at(-1)!

    // El handshake falla (p.ej. Vercel no reenvía upgrades): el servidor
    // nunca envía hello y el socket se cierra.
    act(() => ws.cerrarServidor())

    expect(screen.getByText('Reconectando...')).toBeInTheDocument()
    expect(await screen.findByText('stock_deficit')).toBeInTheDocument()
    const llamadas = fetchMock.mock.calls.map((c) => String(c[0]))
    expect(llamadas.filter((u) => u.includes('/api/v1/events/')).length).toBeGreaterThanOrEqual(1)
  })
})

describe('Fase 1: ciclo de vida (desvincular, cierre de jornada, rutas de bobina)', () => {
  function stubFase1(pendientes: unknown[] = []) {
    const fetchMock = vi.fn((url: string, _init?: RequestInit) => {
      const u = String(url)
      if (u.includes('/scan')) {
        return Promise.resolve({
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
        })
      }
      if (u === '/api/v1/orders/available') {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { id: 'OP1', numero: 'OP-DEMO-001', estado: 'active', cliente: null, fecha_entrega: null, workstation_id: 'LINEA-1' },
          ],
        })
      }
      if (u.includes('/api/v1/orders/OP1')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: 'OP1',
            numero: 'OP-DEMO-001',
            estado: 'active',
            cliente: null,
            fecha_entrega: null,
            workstation_id: 'LINEA-1',
            lines: [
              {
                id: 'line-1',
                linea_numero: 1,
                workstation_id: 'LINEA-1',
                estado: 'pending',
                total_quantity: 50,
                produced_quantity: 0,
                material_id: 'mat-1',
                active_coil_id: null,
                active_coil_code: null,
                real_material_qty: 0,
                real_material_cost: 0,
                real_cost: 0,
                scrap_material_qty: 0,
                target_material_qty: 100,
                target_material_unit: 'kg',
                meters_per_piece: 2.0,
              },
            ],
          }),
        })
      }
      if (u.includes('/stock-items/link')) {
        return Promise.resolve({ ok: true, json: async () => ({ success: true, coil_weight: 800, order: 'OP1' }) })
      }
      if (u.includes('/stock-items/unlink')) {
        return Promise.resolve({ ok: true, json: async () => ({ success: true, refunded_qty: 800, refunded_cost: 1600 }) })
      }
      if (u.includes('/stock-items/fin-bobina')) {
        return Promise.resolve({ ok: true, json: async () => ({ msg: 'ok', peso_restante_kg: 10, merma_kg: 5, merma_cost: 10 }) })
      }
      if (u.includes('/stock-items/retirar')) {
        return Promise.resolve({ ok: true, json: async () => ({ msg: 'ok' }) })
      }
      if (u.includes('/auth/close-shift')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, status: 'completed', total_hours: 3.5, turno: 'B', logout_time: '2026-10-16T20:00:00+00:00' }),
        })
      }
      if (u.includes('/stock-items/mediciones-pendientes')) {
        return Promise.resolve({ ok: true, json: async () => pendientes })
      }
      if (u.includes('/stock-items/medir')) {
        return Promise.resolve({ ok: true, json: async () => ({ msg: 'ok', chatarra_kg: 12.5, chatarra_coste: 10, peso_restante_kg: 410 }) })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })
    vi.stubGlobal('fetch', fetchMock)
    return fetchMock
  }

  async function abrirPanelVinculado(fetchMock: ReturnType<typeof vi.fn>) {
    renderPage()
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/api/v1/orders/OP1'))).toBe(true)
    })
    await vincularBobina(userEvent.setup())
  }

  it('desvincular llama a POST /stock-items/unlink y vuelve al escaneo', async () => {
    const user = userEvent.setup()
    const fetchMock = stubFase1()
    await abrirPanelVinculado(fetchMock)

    await user.click(await screen.findByRole('button', { name: /desvincular bobina/i }))

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/stock-items/unlink'))).toBe(true)
    })
    const llamada = fetchMock.mock.calls.find(([u]) => String(u).includes('/stock-items/unlink'))
    expect(llamada?.[1]?.method).toBe('POST')
    expect(await screen.findByPlaceholderText(/escanea la etiqueta/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /registrar piezas/i })).not.toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('con una bobina sin medir no deja cerrar la jornada hasta medir el radio', async () => {
    const user = userEvent.setup()
    const fetchMock = stubFase1([
      { stock_item_id: 'SI1', coil_code: 'COIL-108', order_id: 'OP1', line_id: 'L1', puesto: 'LINEA-1' },
    ])
    renderPage()
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())

    await user.click(screen.getByRole('button', { name: /cerrar jornada/i }))
    const cerrar = screen.getByRole('button', { name: /sí, cerrar/i })
    await user.type(await screen.findByLabelText(/radio de COIL-108/i), '210')
    expect(cerrar).toBeDisabled()

    await user.click(screen.getByRole('button', { name: /^medir$/i }))
    const medida = fetchMock.mock.calls.find(([u]) => String(u).includes('/stock-items/medir'))
    expect(JSON.parse(String(medida?.[1]?.body))).toMatchObject({ stock_item_id: 'SI1', radio_mm: 210 })
    expect(await screen.findByText(/quedan 410 kg montados/i)).toBeInTheDocument()
    await waitFor(() => expect(cerrar).toBeEnabled())
    vi.unstubAllGlobals()
  })

  it('cerrar jornada pide confirmación, llama a /auth/close-shift y muestra horas y turno', async () => {
    const user = userEvent.setup()
    const fetchMock = stubFase1()
    renderPage()
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())

    await user.click(screen.getByRole('button', { name: /cerrar jornada/i }))
    expect(screen.getByText(/se registrará la hora de salida/i)).toBeInTheDocument()

    const cerrar = screen.getByRole('button', { name: /sí, cerrar/i })
    await waitFor(() => expect(cerrar).toBeEnabled())
    await user.click(cerrar)
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/auth/close-shift'))).toBe(true)
    })
    const tarjeta = (await screen.findByText('Jornada cerrada')).closest('div')
    expect(tarjeta).toHaveTextContent('Turno B')
    expect(tarjeta).toHaveTextContent('3,5')
    vi.unstubAllGlobals()
  })

  it('fin de bobina apunta a /stock-items/fin-bobina (prefijo real del router)', async () => {
    const user = userEvent.setup()
    const fetchMock = stubFase1()
    await abrirPanelVinculado(fetchMock)

    const radio = await screen.findByPlaceholderText(/radio restante/i)
    await user.type(radio, '10')
    await user.click(screen.getByRole('button', { name: /cerrar bobina/i }))

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/stock-items/fin-bobina'))).toBe(true)
    })
    vi.unstubAllGlobals()
  })

  it('retirar pico apunta a /stock-items/retirar (prefijo real del router)', async () => {
    const user = userEvent.setup()
    const fetchMock = stubFase1()
    await abrirPanelVinculado(fetchMock)

    await user.click(screen.getByRole('button', { name: /retirar pico a inventario/i }))

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/stock-items/retirar'))).toBe(true)
    })
    vi.unstubAllGlobals()
  })
})

describe('Fase 2 pulido: puesto -> cola de ordenes -> panel', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.history.replaceState({}, '', '/')
  })

  const puestos = [
    { id: 'w1', code: 'LINEA-1', name: 'Linea Uno', color: '#333', group_id: null, is_active: true },
    { id: 'w2', code: 'LINEA-9', name: 'Linea Nueve', color: '#333', group_id: null, is_active: true },
  ]
  const ordenes = [
    { id: 'OPA', numero: 'OP-F2-001', estado: 'active', cliente: 'Cliente A', fecha_entrega: null, workstation_id: 'LINEA-1' },
    { id: 'OPB', numero: 'OP-F2-002', estado: 'draft', cliente: 'Cliente B', fecha_entrega: null, workstation_id: 'LINEA-1' },
  ]

  function stubFlujo(opts?: { conPuestoUnico?: boolean }) {
    const llamadas: string[] = []
    const puestosUsar = opts?.conPuestoUnico ? [puestos[0]] : puestos
    const ordenesUsar = opts?.conPuestoUnico ? [ordenes[0]] : ordenes
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        const u = String(url)
        llamadas.push(u)
        if (u.includes('/admin/workstations')) {
          return Promise.resolve({ ok: true, json: async () => puestosUsar })
        }
        if (u.includes('/orders/available')) {
          return Promise.resolve({ ok: true, json: async () => ordenesUsar })
        }
        if (u.includes('/orders/OPA')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              id: 'OPA',
              numero: 'OP-F2-001',
              estado: 'active',
              lines: [{ id: 'L1', workstation_id: 'LINEA-1' }],
            }),
          })
        }
        if (u.includes('/orders/OPB')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              id: 'OPB',
              numero: 'OP-F2-002',
              estado: 'draft',
              lines: [{ id: 'L2', workstation_id: 'LINEA-1' }],
            }),
          })
        }
        if (u.includes('/quality/models')) {
          return Promise.resolve({ ok: true, json: async () => [] })
        }
        return Promise.resolve({ ok: true, json: async () => null })
      }),
    )
    return llamadas
  }

  it('con dos puestos muestra la pantalla de seleccion de puesto', async () => {
    stubFlujo()
    renderPage()
    expect(
      await screen.findByText('Selecciona tu puesto de trabajo'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /LINEA-1/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /LINEA-9/ })).toBeInTheDocument()
    expect(screen.queryByText('Vincular bobina')).not.toBeInTheDocument()
  })

  it('elegir puesto lleva a la cola y elegir orden al panel con la URL', async () => {
    const user = userEvent.setup()
    stubFlujo()
    renderPage()
    await screen.findByText('Selecciona tu puesto de trabajo')
    await user.click(screen.getByRole('button', { name: /LINEA-1/ }))

    expect(await screen.findByText(/Cola de órdenes · LINEA-1/)).toBeInTheDocument()
    expect(screen.getByText('#OP-F2-001')).toBeInTheDocument()
    expect(screen.getByText('#OP-F2-002')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /OP-F2-001/ }))
    expect(await screen.findByText('Vincular bobina')).toBeInTheDocument()
    expect(window.location.search).toContain('ws=LINEA-1')
    expect(window.location.search).toContain('order=OPA')
    expect(screen.getByText(/LINEA-1 · OP-F2-001/)).toBeInTheDocument()
  })

  it('availableOrders se llama con el puesto seleccionado', async () => {
    const user = userEvent.setup()
    const llamadas = stubFlujo()
    renderPage()
    await screen.findByText('Selecciona tu puesto de trabajo')
    await user.click(screen.getByRole('button', { name: /LINEA-1/ }))
    await waitFor(() => {
      expect(
        llamadas.some((u) => u.includes('/orders/available?workstation=LINEA-1')),
      ).toBe(true)
    })
  })

  it('con un solo puesto se salta la seleccion y con una orden va al panel', async () => {
    stubFlujo({ conPuestoUnico: true })
    renderPage()
    expect(await screen.findByText('Vincular bobina')).toBeInTheDocument()
    expect(screen.queryByText('Selecciona tu puesto de trabajo')).not.toBeInTheDocument()
    expect(screen.queryByText(/Cola de órdenes/)).not.toBeInTheDocument()
    expect(window.location.search).not.toContain('ws=')
  })

  it('el boton cambiar orden devuelve a la cola desde el panel', async () => {
    const user = userEvent.setup()
    stubFlujo({ conPuestoUnico: true })
    renderPage()
    await screen.findByText('Vincular bobina')
    await user.click(screen.getByRole('button', { name: /cambiar orden/i }))

    expect(await screen.findByText(/Cola de órdenes · LINEA-1/)).toBeInTheDocument()
    expect(screen.getByText('#OP-F2-001')).toBeInTheDocument()
    expect(screen.queryByText('Vincular bobina')).not.toBeInTheDocument()
  })

  it('el boton cambiar puesto vuelve a la seleccion de puesto', async () => {
    const user = userEvent.setup()
    stubFlujo({ conPuestoUnico: true })
    renderPage()
    await screen.findByText('Vincular bobina')
    await user.click(screen.getByRole('button', { name: /cambiar puesto/i }))

    expect(
      await screen.findByText('Selecciona tu puesto de trabajo'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /LINEA-1/ })).toBeInTheDocument()
  })
})
