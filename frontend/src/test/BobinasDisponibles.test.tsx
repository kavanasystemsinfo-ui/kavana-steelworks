import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BobinasDisponibles } from '../components/BobinasDisponibles'

const bobina = (lote: string, extra = {}) => ({
  id: `id-${lote}`, lote, coil_id: `COIL-${lote}`, peso_kg: 1200, ancho_mm: 108, espesor_mm: 1.2,
  material_code: 'FLEJE-108', material_name: 'Fleje', estado: 'activo', ubicacion: 'ALMACEN',
  modo: 'auto', en_puesto: false, ...extra,
})

describe('Bobinas disponibles (sin saberse el código)', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lista las bobinas de la línea y al tocar una la elige', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [bobina('EN-PUESTO', { en_puesto: true }), bobina('VIEJA')],
    })
    vi.stubGlobal('fetch', fetchMock)
    const onElegir = vi.fn()
    render(<BobinasDisponibles lineId="L1" onElegir={onElegir} />)

    expect(String(fetchMock.mock.calls[0][0])).toContain('/stock-items/disponibles?line_id=L1')
    expect(await screen.findByText(/ya en tu puesto/i)).toBeInTheDocument()
    await userEvent.setup().click(screen.getByText('COIL-VIEJA'))
    expect(onElegir).toHaveBeenCalledWith(expect.objectContaining({ lote: 'VIEJA' }))
  })

  it('sin bobinas invita a registrarla a mano', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }))
    render(<BobinasDisponibles lineId="L1" onElegir={vi.fn()} />)
    expect(await screen.findByText(/regístrala a mano/i)).toBeInTheDocument()
  })
})
