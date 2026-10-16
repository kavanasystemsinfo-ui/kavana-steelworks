import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MateriasPrimasPage } from '../pages/MateriasPrimasPage'

/** Fase 0 UX: recepción de bobinas.
 *  - El formulario auto-rellena ancho/espesor desde el material elegido.
 *  - No pide Nº calor (heat) ni Grado de acero (decisión Jorge: esos datos
 *    vienen de la etiqueta del proveedor solo cuando existen en la API).
 */

const materiales = [
  {
    id: 'm1',
    code: 'FLEJE-G175-12',
    name: 'Fleje galva DX51D 175x1,2',
    cost_per_unit: 1.1,
    unit: 'kg',
    stock_current: 5000,
    dimension_ancho_mm: 175,
    dimension_espesor_mm: 1.2,
  },
  {
    id: 'm2',
    code: 'D310-15',
    name: 'Fleje decapado DC01 310x1,5',
    cost_per_unit: 0.95,
    unit: 'kg',
    stock_current: 3200,
    dimension_ancho_mm: 310,
    dimension_espesor_mm: 1.5,
  },
]

function makeToken(): string {
  const payload = { sub: 'u1', tenant_id: 't1', role: 'materials', exp: 9999999999 }
  return `x.${btoa(JSON.stringify(payload))}.x`
}

let ultimoPost: Record<string, unknown> | null = null

function instalarFetch() {
  ultimoPost = null
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        ultimoPost = JSON.parse(String(init.body)) as Record<string, unknown>
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: 'b1',
            lote: ultimoPost?.lote,
            coil_id: `COIL-${ultimoPost?.lote}`,
            estado: 'activo',
            peso: ultimoPost?.peso,
            ubicacion: null,
            costo_method: 'standard',
          }),
        }
      }
      return { ok: true, status: 200, json: async () => materiales }
    }),
  )
}

beforeEach(() => {
  sessionStorage.setItem('kavana_token', makeToken())
  instalarFetch()
})

afterEach(() => {
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

describe('Formulario de recepción (Fase 0 UX)', () => {
  it('auto-rellena ancho y espesor del material seleccionado por defecto', async () => {
    render(<MateriasPrimasPage />)
    await waitFor(() =>
      expect(screen.getByLabelText(/ancho \(mm\)/i)).toHaveValue(175),
    )
    expect(screen.getByLabelText(/espesor \(mm\)/i)).toHaveValue(1.2)
  })

  it('al cambiar de material se actualizan ancho y espesor', async () => {
    const user = userEvent.setup()
    render(<MateriasPrimasPage />)
    await waitFor(() =>
      expect(screen.getByLabelText(/ancho \(mm\)/i)).toHaveValue(175),
    )

    await user.selectOptions(screen.getByLabelText(/^material/i), 'm2')

    expect(screen.getByLabelText(/ancho \(mm\)/i)).toHaveValue(310)
    expect(screen.getByLabelText(/espesor \(mm\)/i)).toHaveValue(1.5)
  })

  it('no muestra Nº calor (heat) ni Grado de acero', async () => {
    render(<MateriasPrimasPage />)
    await waitFor(() =>
      expect(screen.getByLabelText(/ancho \(mm\)/i)).toHaveValue(175),
    )
    expect(screen.queryByText(/nº calor/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/grado de acero/i)).not.toBeInTheDocument()
  })

  it('envía ancho/espesor rellenados y omite heat y grado', async () => {
    const user = userEvent.setup()
    render(<MateriasPrimasPage />)
    await waitFor(() =>
      expect(screen.getByLabelText(/ancho \(mm\)/i)).toHaveValue(175),
    )

    await user.type(screen.getByLabelText(/lote/i), 'L-UX-01')
    await user.type(screen.getByLabelText(/peso \(kg\)/i), '900')
    await user.click(screen.getByRole('button', { name: /registrar bobina/i }))

    await waitFor(() => expect(ultimoPost).not.toBeNull())
    expect(ultimoPost).toMatchObject({
      lote: 'L-UX-01',
      peso: 900,
      width_mm: 175,
      thickness_mm: 1.2,
    })
    expect(ultimoPost).not.toHaveProperty('heat_number')
    expect(ultimoPost).not.toHaveProperty('grado_acero')
  })

  it('permite sobrescribir las medidas si la etiqueta trae otras', async () => {
    const user = userEvent.setup()
    render(<MateriasPrimasPage />)
    await waitFor(() =>
      expect(screen.getByLabelText(/ancho \(mm\)/i)).toHaveValue(175),
    )

    const ancho = screen.getByLabelText(/ancho \(mm\)/i)
    await user.clear(ancho)
    await user.type(ancho, '185')
    await user.type(screen.getByLabelText(/lote/i), 'L-UX-02')
    await user.type(screen.getByLabelText(/peso \(kg\)/i), '500')
    await user.click(screen.getByRole('button', { name: /registrar bobina/i }))

    await waitFor(() => expect(ultimoPost).not.toBeNull())
    expect(ultimoPost).toMatchObject({ width_mm: 185 })
  })
})
