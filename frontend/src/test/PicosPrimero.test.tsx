import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AvisoPicos } from '../components/AvisoPicos'
import { BobinasDisponibles } from '../components/BobinasDisponibles'
import { PicosAcumulados } from '../components/PicosAcumulados'
import { OperarioPage } from '../pages/OperarioPage'

const bobina = (lote: string, extra = {}) => ({
  id: `id-${lote}`, lote, coil_id: `COIL-${lote}`, peso_kg: 1200, ancho_mm: 108, espesor_mm: 1.2,
  material_code: 'FLEJE-108', material_name: 'Fleje', estado: 'activo', ubicacion: 'ALMACEN',
  modo: 'auto', en_puesto: false, antiguedad_dias: 0, ...extra,
})

describe('Aviso de picos al elegir bobina nueva (D-019)', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('enseña los picos y cada motivo se manda con un toque', async () => {
    const onMotivo = vi.fn()
    const onUsarPico = vi.fn()
    render(
      <AvisoPicos
        picos={[{ coil_id: 'B-PICO', peso_kg: 45 }]}
        onMotivo={onMotivo}
        onUsarPico={onUsarPico}
      />,
    )
    const aviso = screen.getByRole('dialog', { name: 'Hay picos de este material' })
    expect(aviso).toHaveTextContent('B-PICO (45 kg)')

    await userEvent.setup().click(screen.getByRole('button', { name: 'No llega para la orden' }))
    expect(onMotivo).toHaveBeenCalledWith('pico_corto')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Está en mal estado' }))
    expect(onMotivo).toHaveBeenCalledWith('pico_danado')
    await userEvent.setup().click(screen.getByRole('button', { name: 'No lo encuentro' }))
    expect(onMotivo).toHaveBeenCalledWith('no_localizado')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Otro motivo' }))
    expect(onMotivo).toHaveBeenCalledWith('otro')

    await userEvent.setup().click(screen.getByRole('button', { name: 'Elegir un pico' }))
    expect(onUsarPico).toHaveBeenCalledTimes(1)
  })

  it('la lista marca el pico como «usar primero», avisa y dice cuánto lleva guardado', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          bobina('PICO', { estado: 'pico', ubicacion: 'Retales', antiguedad_dias: 12, peso_kg: 45 }),
          bobina('NUEVA'),
        ],
      }),
    )
    render(<BobinasDisponibles lineId="L1" onElegir={vi.fn()} />)

    expect(await screen.findByText('Usar primero')).toBeInTheDocument()
    expect(screen.getByText(/gástalos primero/i)).toBeInTheDocument()
    expect(screen.getByText(/hace 12 días/)).toBeInTheDocument()
  })

  it('sin picos no hay aviso ni etiqueta', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => [bobina('NUEVA'), bobina('OTRA')] }),
    )
    render(<BobinasDisponibles lineId="L1" onElegir={vi.fn()} />)

    await screen.findByText('COIL-NUEVA')
    expect(screen.queryByText('Usar primero')).not.toBeInTheDocument()
    expect(screen.queryByText(/gástalos primero/i)).not.toBeInTheDocument()
  })
})

describe('Picos acumulados en la vista del supervisor', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lista cada material con sus picos, kilos y antigüedad', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          {
            material_id: 'm1',
            material_code: 'ACERO-01',
            material_name: 'Bobina Acero',
            picos: 2,
            kg_total: 65,
            mas_antiguo_dias: 12,
            items: [
              { id: 'a', coil_id: 'B-PICO', lote: 'L1', peso_kg: 45, ubicacion: 'Retales', antiguedad_dias: 12 },
              { id: 'b', coil_id: null, lote: 'L2', peso_kg: 20, ubicacion: 'LINEA-1', antiguedad_dias: 0 },
            ],
          },
        ],
      }),
    )
    render(<PicosAcumulados />)

    const seccion = await screen.findByRole('region', { name: 'Picos acumulados' })
    expect(seccion).toHaveTextContent('ACERO-01')
    expect(seccion).toHaveTextContent('2 picos · 65 kg')
    expect(seccion).toHaveTextContent('el más antiguo, 12 días')
    expect(seccion).toHaveTextContent('B-PICO · en Retales')
    expect(seccion).toHaveTextContent('L2 · en LINEA-1')
    expect(seccion).toHaveTextContent('de hoy')
  })

  it('no enseña nada si no hay picos ni si el servidor falla', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }))
    const { unmount } = render(<PicosAcumulados />)
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(screen.queryByRole('region', { name: 'Picos acumulados' })).not.toBeInTheDocument()
    unmount()

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) }))
    render(<PicosAcumulados />)
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(screen.queryByRole('region', { name: 'Picos acumulados' })).not.toBeInTheDocument()
  })
})

describe('Operario: vincular una bobina nueva habiendo picos', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('el 409 abre el aviso, el motivo reenvía la vinculación y sigue el flujo normal', async () => {
    const user = userEvent.setup()
    const cuerposLink: Array<Record<string, unknown>> = []
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.includes('/scan')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: 'bobina-1', lote: 'L-DEMO', coil_id: 'COIL-L-DEMO', peso_kg: 800, ancho_mm: 122,
            espesor_mm: 0.5, material_code: 'ACERO-01', material_name: 'Bobina Acero',
            estado: 'activo', ubicacion: 'ALMACEN-1', modo: 'auto',
          }),
        })
      }
      if (url.includes('/api/v1/orders/OP1')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: 'OP1', numero: 'OP-DEMO-001', estado: 'active', cliente: null, fecha_entrega: null,
            workstation_id: 'LINEA-1',
            lines: [
              {
                id: 'line-1', linea_numero: 1, workstation_id: 'LINEA-1', estado: 'pending',
                total_quantity: 50, produced_quantity: 0, material_id: 'mat-1', active_coil_id: null,
                active_coil_code: null, real_material_qty: 0, real_material_cost: 0, real_cost: 0,
                scrap_material_qty: 0, target_material_qty: 100, target_material_unit: 'kg',
                meters_per_piece: 2.0,
              },
            ],
          }),
        })
      }
      if (url === '/api/v1/orders/available') {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { id: 'OP1', numero: 'OP-DEMO-001', estado: 'active', cliente: null, fecha_entrega: null, workstation_id: 'LINEA-1' },
          ],
        })
      }
      if (url.includes('/stock-items/link')) {
        const cuerpo = JSON.parse(String(init?.body ?? '{}'))
        cuerposLink.push(cuerpo)
        if (!cuerpo.motivo_salto_pico) {
          return Promise.resolve({
            ok: false,
            status: 409,
            json: async () => ({
              detail: {
                codigo: 'MOTIVO_PICO_REQUERIDO',
                mensaje: 'Hay picos de este material. Indica por qué eliges una bobina nueva.',
                picos: [{ coil_id: 'B-PICO', peso_kg: 45 }],
              },
            }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, coil_weight: 800, order: 'OP1' }),
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <MemoryRouter>
        <OperarioPage />
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/api/v1/orders/OP1'))).toBe(true)
    })
    await user.type(screen.getByPlaceholderText(/escanea la etiqueta/i), 'COIL-L-DEMO')
    await user.click(screen.getByRole('button', { name: /escanear bobina/i }))
    await user.click(await screen.findByRole('button', { name: /vincular a mi orden/i }))

    // 409: aparece el aviso con el pico y todavía no está vinculada
    const aviso = await screen.findByRole('dialog', { name: 'Hay picos de este material' })
    expect(aviso).toHaveTextContent('B-PICO (45 kg)')
    expect(screen.queryByRole('button', { name: /fin de bobina: medir la carne/i })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'No llega para la orden' }))

    expect(
      await screen.findByRole('button', { name: /fin de bobina: medir la carne/i }),
    ).toBeInTheDocument()
    expect(cuerposLink).toHaveLength(2)
    expect(cuerposLink[0].motivo_salto_pico).toBeUndefined()
    expect(cuerposLink[1].motivo_salto_pico).toBe('pico_corto')
    expect(screen.queryByRole('dialog', { name: 'Hay picos de este material' })).not.toBeInTheDocument()
  })
})
