import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { SupervisorPage } from '../pages/SupervisorPage'

function renderPage() {
  return render(
    <MemoryRouter>
      <SupervisorPage />
    </MemoryRouter>,
  )
}

describe('Panel de Supervisor (planta en un vistazo)', () => {
  it('muestra OEE y KPIs cargados desde la API', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/oee')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            availability: 50,
            performance: 50,
            quality: 95,
            oee: 23.75,
            raw: {
              total_pieces: 10,
              total_objetivo: 20,
              total_tiempo_min: 240,
              scrap_kg: 5,
              material_kg: 100,
            },
          }),
        })
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({
          orders_total: 1,
          orders_active: 1,
          orders_completed: 0,
          estimated_cost: 1000,
          real_cost: 900,
          cost_variance: -100,
          cost_efficiency: 111.1,
          material_variance: 0,
          material_efficiency: 0,
          scrap_rate: 5,
        }),
      })
    }))

    renderPage()

    expect(await screen.findByText('23,75')).toBeInTheDocument()
    expect(screen.getAllByText('50').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('95')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument() // merma kg
    expect(screen.getByText('111,1 %')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('sin datos muestra marcadores vacíos, no inventa valores', () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
    }))
    renderPage()
    expect(screen.getByText('Turno actual')).toBeInTheDocument()
    expect(screen.getAllByText('--').length).toBeGreaterThan(0)
    vi.unstubAllGlobals()
  })
})
