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
