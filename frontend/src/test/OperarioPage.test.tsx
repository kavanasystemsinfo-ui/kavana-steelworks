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
})
