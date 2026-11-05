import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { TablaPuestos } from '../components/TablaPuestos'
import type { DetallePuesto } from '../lib/api'

const f = (oee: number) => ({ oee, disponibilidad: 90, rendimiento: 90, calidad: 99 })
const base = { kg_material: 0, chatarra_kg: 0, chatarra_pct: null, paradas_min: 0, paradas_n: 0 }
const puestos: DetallePuesto[] = [
  { ...base, puesto: 'PERF-1', piezas: 320, plan: 500, eficiencia: f(64), paradas_min: 60, paradas_n: 1, chatarra_kg: 2, chatarra_pct: 2 },
  { ...base, puesto: 'PUNZ-1', piezas: 900, plan: 950, eficiencia: f(91) },
  { ...base, puesto: 'SOL-1', piezas: 0, plan: null, eficiencia: null, paradas_min: 130, paradas_n: 2 },
]

const orden = () =>
  within(screen.getAllByRole('rowgroup')[1])
    .getAllByRole('row')
    .map((r) => within(r).getAllByRole('cell')[0].textContent)

describe('Tabla comparativa de puestos', () => {
  it('empieza por el de menor eficiencia y deja sin dato al final', () => {
    render(<TablaPuestos puestos={puestos} objetivoOee={85} />)
    expect(orden()).toEqual(['PERF-1', 'PUNZ-1', 'SOL-1'])
    expect(screen.getByText('2 h 10 min (2)')).toBeInTheDocument()
    expect(screen.getByText('2 kg · 2 %')).toBeInTheDocument()
  })

  it('ordena por columna en los dos sentidos', async () => {
    render(<TablaPuestos puestos={puestos} objetivoOee={85} />)
    await userEvent.click(screen.getByRole('button', { name: 'Piezas' }))
    expect(orden()).toEqual(['PUNZ-1', 'PERF-1', 'SOL-1'])
    await userEvent.click(screen.getByRole('button', { name: /Piezas/ }))
    expect(orden()).toEqual(['SOL-1', 'PERF-1', 'PUNZ-1'])
    expect(screen.getByRole('columnheader', { name: /Piezas/ })).toHaveAttribute(
      'aria-sort',
      'ascending',
    )
  })

  it('un puesto lleva a su ficha', async () => {
    const onPuesto = vi.fn()
    render(<TablaPuestos puestos={puestos} objetivoOee={85} onPuesto={onPuesto} />)
    await userEvent.click(screen.getByRole('button', { name: 'Ver la ficha de SOL-1' }))
    expect(onPuesto).toHaveBeenCalledWith('SOL-1')
  })
})
