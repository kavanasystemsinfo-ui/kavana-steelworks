import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { InformeTurno } from '../components/InformeTurno'

const informe = {
  fecha: '2026-10-28', turno: 'A', inicio: '', fin: '',
  puestos: [], totales: {},
  por_operario: [
    {
      operario: 'Ana', orden: 'OP-1', material: 'FLEJE', piezas: 100,
      consumo_kg: 965, piezas_kg: 900, chatarra_kg: 65, chatarra_pct: 6.7,
      modelo: 'MOD-1', chatarra_prevista_kg: 40, chatarra_de_mas_kg: 25, referencia: 'peso_terminado',
    },
    {
      operario: 'Luis', orden: 'OP-2', material: 'FLEJE', piezas: 50,
      consumo_kg: 480, piezas_kg: 470, chatarra_kg: 10, chatarra_pct: 2.1,
      modelo: null, chatarra_prevista_kg: null, chatarra_de_mas_kg: null, referencia: null,
    },
  ],
}

describe('Informe de turno: chatarra prevista y de más', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('separa la chatarra prevista de la de más y marca los modelos que aprenden', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => informe }))
    render(<InformeTurno />)
    expect(await screen.findByText('40 kg')).toBeInTheDocument()
    expect(screen.getByText('25 kg')).toBeInTheDocument()
    expect(screen.getByText('aprendiendo')).toBeInTheDocument()
  })
})
