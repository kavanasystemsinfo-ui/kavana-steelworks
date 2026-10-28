import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MotivosParada, PantallaParada } from '../components/ParadaMaquina'

const parada = {
  id: 'p1', puesto: 'LINEA-1', motivo: 'averia', motivo_texto: 'avería', nota: null,
  inicio: new Date(Date.now() - 75_000).toISOString(), fin: null,
}

describe('Paradas con un toque', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('un toque en el motivo abre la parada del puesto', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => parada })
    vi.stubGlobal('fetch', fetchMock)
    const onParada = vi.fn()
    render(<MotivosParada puesto="LINEA-1" orderId="O1" lineId="L1" onParada={onParada} onError={vi.fn()} />)

    for (const m of ['Avería', 'Ajustes', 'Cambio de modelo', 'Limpieza', 'Mantenimiento', 'Otros']) {
      expect(screen.getByRole('button', { name: m })).toBeInTheDocument()
    }
    await userEvent.setup().click(screen.getByRole('button', { name: 'Avería' }))
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({
      puesto: 'LINEA-1', motivo: 'averia', order_id: 'O1', line_id: 'L1',
    })
    expect(onParada).toHaveBeenCalledWith(parada)
  })

  it('la pantalla de parada cuenta el tiempo y vuelve a producir con la nota', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...parada, fin: 'x' }) })
    vi.stubGlobal('fetch', fetchMock)
    const onFin = vi.fn()
    render(<PantallaParada parada={parada} orden="OP-1" onCambio={vi.fn()} onFin={onFin} onError={vi.fn()} />)
    const user = userEvent.setup()

    expect(screen.getByRole('heading', { name: 'Avería' })).toBeInTheDocument()
    expect(screen.getByText(/^01:1\d$/)).toBeInTheDocument()
    await user.type(screen.getByPlaceholderText(/cuchilla/i), 'motor caliente')
    await user.click(screen.getByRole('button', { name: /volver a producir/i }))
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/production/paradas/p1/fin')
    expect(JSON.parse(String(init.body))).toEqual({ nota: 'motor caliente' })
    expect(onFin).toHaveBeenCalled()
  })
})
