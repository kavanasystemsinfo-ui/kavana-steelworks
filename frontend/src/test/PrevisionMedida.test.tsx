import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PrevisionMedida } from '../components/PrevisionMedida'

describe('Vista previa de la medición (mm de carne → kg)', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('pide al servidor los kg y la merma y los enseña antes de confirmar', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ radio_mm: 150, peso_restante_kg: 512.4, sistema_kg: 600, merma_kg: 87.6 }),
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<PrevisionMedida stockItemId="B1" radio="150" />)

    expect(await screen.findByText(/512,4 kg/)).toBeInTheDocument()
    expect(screen.getByText(/87,6 kg/)).toBeInTheDocument()
    expect(String(fetchMock.mock.calls[0][0])).toContain('/stock-items/B1/prevision-medida?radio_mm=150')
  })

  it('sin milímetros o sin bobina no pregunta nada', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<PrevisionMedida stockItemId="B1" radio="" />)
    render(<PrevisionMedida stockItemId={null} radio="150" />)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
