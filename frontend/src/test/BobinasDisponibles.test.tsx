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

  it('una bobina de otro puesto dice dónde está, también si es un pico', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          bobina('PICO', { estado: 'pico', ubicacion: 'P-K300' }),
          bobina('ALM', { ubicacion: 'ALMACEN' }),
        ],
      }),
    )
    render(<BobinasDisponibles lineId="L1" onElegir={vi.fn()} />)
    expect(await screen.findByText(/pico \/ retal · en P-K300/i)).toBeInTheDocument()
    expect(screen.getByText(/· en ALMACEN/i)).toBeInTheDocument()
  })

  it('enseña solo las 4 primeras y el resto queda tras «Ver más»', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ['A', 'B', 'C', 'D', 'E', 'F'].map((l) => bobina(l)),
      }),
    )
    const user = userEvent.setup()
    render(<BobinasDisponibles lineId="L1" onElegir={vi.fn()} />)

    expect(await screen.findByText('COIL-A')).toBeInTheDocument()
    expect(screen.getByText('COIL-D')).toBeInTheDocument()
    expect(screen.queryByText('COIL-E')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Ver 2 más' }))
    expect(screen.getByText('COIL-F')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Ver menos' }))
    expect(screen.queryByText('COIL-E')).not.toBeInTheDocument()
  })

  it('con 4 o menos no hay botón y las etiquetas sustituyen a los iconos', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          bobina('PUESTO', { en_puesto: true }),
          bobina('PICO', { estado: 'pico' }),
          bobina('VIEJA'),
          bobina('NUEVA'),
        ],
      }),
    )
    render(<BobinasDisponibles lineId="L1" onElegir={vi.fn()} />)
    expect(await screen.findByText('En tu puesto')).toBeInTheDocument()
    expect(screen.getByText('Usar primero')).toBeInTheDocument()
    expect(screen.getAllByText('Más antigua')).toHaveLength(1)
    expect(screen.queryByRole('button', { name: /ver .* más/i })).not.toBeInTheDocument()
  })

  it('sin bobinas invita a registrarla a mano', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }))
    render(<BobinasDisponibles lineId="L1" onElegir={vi.fn()} />)
    expect(await screen.findByText(/regístrala a mano/i)).toBeInTheDocument()
  })
})
