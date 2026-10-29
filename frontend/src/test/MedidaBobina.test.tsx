import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MedidaBobina } from '../components/MedidaBobina'

const prevision = (extra = {}) => ({
  radio_mm: 125, peso_restante_kg: 512.54, sistema_kg: 521.49, merma_kg: 8.95, merma_pct: 1.7,
  kg_por_mm: 4.9, margen_error_kg: 14.7, merma_dentro_del_margen: true,
  coil_code: 'SIM-FLEJE-D265', material_code: 'FLEJE-D265-18', ancho_mm: 265, mandril_mm: 508,
  densidad_kg_dm3: 7.7807, ...extra,
})

function stub(datos: object) {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => datos })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('Medir la carne de una bobina (maquetación del legacy)', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('enseña la ficha, los kg en grande y Sistema / Real / Merma antes de confirmar', async () => {
    const fetchMock = stub(prevision())
    const onConfirmar = vi.fn()
    const user = userEvent.setup()
    render(<MedidaBobina stockItemId="B1" textoConfirmar="Cerrar bobina" onConfirmar={onConfirmar} />)

    expect(screen.getByRole('button', { name: 'Cerrar bobina' })).toBeDisabled()
    await user.type(screen.getByPlaceholderText(/carne \(mm\)/i), '125')

    expect(await screen.findByText('265 mm')).toBeInTheDocument()
    expect(screen.getAllByText('512,5 kg')).toHaveLength(2)
    expect(screen.getByText('521,5 kg')).toBeInTheDocument()
    expect(screen.getByText(/puede ser solo error del metro/i)).toBeInTheDocument()
    expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain('/stock-items/B1/prevision-medida?radio_mm=125')

    const boton = screen.getByRole('button', { name: 'Cerrar bobina' })
    await waitFor(() => expect(boton).toBeEnabled())
    await user.click(boton)
    expect(onConfirmar).toHaveBeenCalledWith(125)
  })

  it('una merma mayor que el error del metro se avisa como merma real, sin euros', async () => {
    stub(prevision({ merma_kg: 48, merma_pct: 9.2, merma_dentro_del_margen: false }))
    render(<MedidaBobina stockItemId="B1" textoConfirmar="Medir" onConfirmar={vi.fn()} />)
    await userEvent.setup().type(screen.getByPlaceholderText(/carne \(mm\)/i), '100')

    expect(await screen.findByText(/merma del 9,2 %/i)).toBeInTheDocument()
    expect(screen.queryByText(/€/)).not.toBeInTheDocument()
  })

  it('sin bobina no pregunta nada', async () => {
    const fetchMock = stub(prevision())
    render(<MedidaBobina stockItemId={null} textoConfirmar="Medir" onConfirmar={vi.fn()} />)
    await userEvent.setup().type(screen.getByPlaceholderText(/carne \(mm\)/i), '100')
    await new Promise((r) => setTimeout(r, 400))
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
