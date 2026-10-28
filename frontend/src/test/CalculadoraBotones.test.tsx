import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CalculadoraBotones } from '../components/CalculadoraBotones'

const palet = {
  id: 'c1', puesto: 'LINEA-1', nombre: 'Palet M10', piezas_paquete: 5, paquetes_fila: 2,
  filas_palet: 4, piezas_fila: 10, piezas_palet: 40,
}

describe('Calculadoras del puesto', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('+1 palet, +1 fila y +1 paquete suman las piezas de la calculadora', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [palet] }))
    const onSumar = vi.fn()
    render(<CalculadoraBotones puesto="LINEA-1" onSumar={onSumar} />)
    const user = userEvent.setup()

    expect(await screen.findByText('40 piezas')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /\+1 palet/i }))
    await user.click(screen.getByRole('button', { name: /\+1 fila/i }))
    await user.click(screen.getByRole('button', { name: /\+1 paquete/i }))
    expect(onSumar.mock.calls).toEqual([
      ['palets', 40, 'Palet M10'],
      ['filas', 10, 'Palet M10'],
      ['paquetes', 5, 'Palet M10'],
    ])
  })

  it('crea una calculadora nueva con el total del palet a la vista', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) =>
      Promise.resolve({
        ok: true,
        json: async () => (init?.method === 'POST' ? { ...palet, id: 'c2', nombre: 'Caja' } : []),
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    render(<CalculadoraBotones puesto="LINEA-1" onSumar={vi.fn()} />)
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: /nueva calculadora/i }))
    await user.type(screen.getByPlaceholderText(/palet estándar/i), 'Caja')
    await user.click(screen.getByRole('button', { name: /más filas por palet/i }))
    expect(screen.getByText(/5 × 2 × 5/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /guardar y usar/i }))

    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
      puesto: 'LINEA-1', nombre: 'Caja', piezas_paquete: 5, paquetes_fila: 2, filas_palet: 5,
    })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
