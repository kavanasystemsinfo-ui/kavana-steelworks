import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { VistaCostes } from '../components/VistaCostes'

/** Forma real de la respuesta del endpoint (copiada de una respuesta real). */
const panelBody = {
  periodo: 'mes',
  desde: '2026-10-01T05:00:00+00:00',
  hasta: '2026-11-01T05:00:00+00:00',
  coste_kg: { valor: 3.2, periodo_anterior: 3.5, objetivo: 2.9 },
  coste_total: 640.0,
  kg_total: 192.5,
  lineas_metros_excluidas: 2,
  ordenes_completadas: 2,
  desviacion: { pct: 10.0, euros: 40.0, ordenes_con_estimado: 2 },
  chatarra: { euros: 12.5, pct_material: 2.8 },
  reparto: [
    { clave: 'material', etiqueta: 'Material', euros: 440.0, pct: 68.75 },
    { clave: 'mano_obra', etiqueta: 'Mano de obra', euros: 200.0, pct: 31.25 },
    { clave: 'chatarra', etiqueta: 'Chatarra', euros: 0.0, pct: 0.0 },
  ],
  coste_paradas: {
    total: 45.0,
    por_tipo: [{ tipo: 'maquina', etiqueta: 'Máquina', euros: 45.0 }],
    horas: 1.5,
  },
  tendencia: [
    { semana: '2026-09-07', valor: 0.0 },
    { semana: '2026-09-14', valor: 0.0 },
    { semana: '2026-09-21', valor: 0.0 },
    { semana: '2026-09-28', valor: 0.0 },
    { semana: '2026-10-05', valor: 0.0 },
    { semana: '2026-10-12', valor: 0.0 },
    { semana: '2026-10-19', valor: 0.0 },
    { semana: '2026-10-26', valor: 3.2 },
  ],
  ordenes: [
    {
      order_id: 'ord-1',
      numero: 'OP-2',
      producto: 'MAT-OP-2',
      kg: 100.0,
      estimado: 200.0,
      real: 240.0,
      desv_euros: 40.0,
      desv_pct: 20.0,
      causa: 'Sin causa clara',
    },
  ],
}

function stubFetch(datos: unknown = panelBody) {
  const mock = vi.fn((url: string) => {
    if (String(url).includes('formato=csv')) {
      return Promise.resolve({
        ok: true,
        headers: {
          get: () => 'attachment; filename="panel-costes-mes-2026-10-01.csv"',
        },
        blob: async () => new Blob(['Panel de costes;mes']),
      })
    }
    return Promise.resolve({ ok: true, json: async () => datos })
  })
  vi.stubGlobal('fetch', mock)
  return mock
}

beforeEach(() => {
  Object.defineProperty(URL, 'createObjectURL', {
    value: vi.fn(() => 'blob:panel'),
    configurable: true,
    writable: true,
  })
  Object.defineProperty(URL, 'revokeObjectURL', {
    value: vi.fn(),
    configurable: true,
    writable: true,
  })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const tarjeta = (titulo: string) => {
  const el = screen.getByText(titulo).closest('div')
  if (!el) throw new Error(`tarjeta no encontrada: ${titulo}`)
  return el
}

describe('Vista Costes (panel de mando)', () => {
  it('muestra las cifras del backend sin recalcularlas', async () => {
    stubFetch()

    render(<VistaCostes />)

    await screen.findByText('€/kg del periodo')
    expect(tarjeta('€/kg del periodo')).toHaveTextContent('3,20')
    expect(tarjeta('€/kg del periodo')).toHaveTextContent('Periodo anterior 3,50 €/kg')
    expect(tarjeta('Coste total')).toHaveTextContent('640,00 €')
    expect(tarjeta('Coste total')).toHaveTextContent('192,5 kg valorados')
    expect(tarjeta('Coste total')).toHaveTextContent('2 órdenes completadas')
    expect(tarjeta('Coste total')).toHaveTextContent('2 líneas en metros fuera del €/kg')
  })

  it('sin objetivo configurado lo dice en vez de inventar una cifra', async () => {
    stubFetch({ ...panelBody, coste_kg: { ...panelBody.coste_kg, objetivo: null } })

    render(<VistaCostes />)

    expect(await screen.findByText('Sin objetivo de €/kg configurado')).toBeInTheDocument()
  })

  it('muestra el reparto y la chatarra con los porcentajes del backend', async () => {
    stubFetch()

    render(<VistaCostes />)

    expect(
      await screen.findByText('440,00 € · 68,75 %'),
    ).toBeInTheDocument()
    expect(screen.getByText('200,00 € · 31,25 %')).toBeInTheDocument()
    expect(screen.getByText('12,50 €')).toBeInTheDocument()
    expect(screen.getByText('2,80 % del material cargado')).toBeInTheDocument()
  })

  it('valora las paradas por tipo y las horas declaradas', async () => {
    stubFetch()

    render(<VistaCostes />)

    const paradas = (await screen.findByText('Coste de paradas')).closest('div')!
    expect(paradas).toHaveTextContent('45,00 €')
    expect(paradas).toHaveTextContent('· 1,5 h')
    expect(paradas).toHaveTextContent('Máquina')
  })

  it('sin paradas valoradas lo dice en vez de mostrar 0 €', async () => {
    stubFetch({
      ...panelBody,
      coste_paradas: { total: 0, por_tipo: [], horas: 0 },
    })

    render(<VistaCostes />)

    expect(await screen.findByText('Sin paradas valoradas en el periodo.')).toBeInTheDocument()
  })

  it('sin órdenes con estimado no compara desviaciones', async () => {
    stubFetch({
      ...panelBody,
      desviacion: { pct: null, euros: null, ordenes_con_estimado: 0 },
    })

    render(<VistaCostes />)

    expect(
      await screen.findByText('Sin órdenes con estimado: no hay desviación que comparar.'),
    ).toBeInTheDocument()
  })

  it('lista las órdenes con su causa y desviación', async () => {
    stubFetch()

    render(<VistaCostes />)

    const fila = (await screen.findByText('OP-2')).closest('tr')!
    expect(fila).toHaveTextContent('MAT-OP-2')
    expect(fila).toHaveTextContent('Sin causa clara')
    expect(fila).toHaveTextContent('+40,00 €')
    expect(fila).toHaveTextContent('+20,00 %')
  })

  it('sin órdenes completadas lo dice y no pinta tabla', async () => {
    stubFetch({ ...panelBody, ordenes: [], ordenes_completadas: 0 })

    render(<VistaCostes />)

    expect(await screen.findByText('Sin órdenes completadas en el periodo.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('pide el panel del periodo elegido', async () => {
    const fetchMock = stubFetch()
    const user = userEvent.setup()

    render(<VistaCostes />)
    await screen.findByText('€/kg del periodo')

    await user.click(screen.getByRole('button', { name: 'Trimestre' }))

    await waitFor(() => {
      const urls = fetchMock.mock.calls.map(([url]) => String(url))
      expect(urls.some((u) => u.includes('panel/costes?periodo=trimestre'))).toBe(true)
    })
  })

  it('descarga el CSV del periodo y no el JSON', async () => {
    const fetchMock = stubFetch()
    const user = userEvent.setup()

    render(<VistaCostes />)
    await screen.findByText('€/kg del periodo')

    await user.click(screen.getByRole('button', { name: 'Descargar CSV de costes' }))

    await waitFor(() => {
      const urls = fetchMock.mock.calls.map(([url]) => String(url))
      expect(urls.some((u) => u.includes('formato=csv'))).toBe(true)
    })
    expect(URL.createObjectURL).toHaveBeenCalled()
  })

  it('muestra el error real si el endpoint falla', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: 'Rol no autorizado' }) }),
    )

    render(<VistaCostes />)

    expect(await screen.findByText('Rol no autorizado')).toBeInTheDocument()
  })
})
