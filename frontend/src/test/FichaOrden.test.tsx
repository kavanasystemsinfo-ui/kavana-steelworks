import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FichaOrden } from '../components/FichaOrden'
import type { FichaOrden as Ficha } from '../lib/api'

const ficha: Ficha = {
  numero: 'OF-SOL-01', cliente: 'Nova Solar', fecha_entrega: '2026-10-30T12:00:00+00:00',
  plazo: 'en_riesgo', modelo: 'MOD-CELDA-M10', modelo_nombre: 'Celda M10',
  material: 'GALVA-182', material_nombre: 'Galva', ancho_mm: 182, espesor_mm: 1.2,
  largo_mm: 212, ritmo: 600, total: 115, hechas: 54, faltan: 61, bobina: null, tramo_desde: null,
}

describe('Ficha de la orden del operario', () => {
  it('muestra los datos clave de la orden de un vistazo', () => {
    render(<FichaOrden ficha={ficha} numero={null} />)
    expect(screen.getByRole('heading', { name: 'OF-SOL-01' })).toBeInTheDocument()
    expect(screen.getByText('Nova Solar')).toBeInTheDocument()
    expect(screen.getByText(/En riesgo · entrega/)).toBeInTheDocument()
    expect(screen.getByText('MOD-CELDA-M10')).toBeInTheDocument()
    expect(screen.getByText('Galva · 182 × 1,2 mm')).toBeInTheDocument()
    expect(screen.getByText('212 mm')).toBeInTheDocument()
    expect(screen.getByText('600 pzs/h')).toBeInTheDocument()
    expect(screen.getByText(/faltan 61/)).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '47')
  })

  it('sin ficha muestra al menos el número de orden', () => {
    render(<FichaOrden ficha={null} numero="OP-1" />)
    expect(screen.getByRole('heading', { name: 'OP-1' })).toBeInTheDocument()
  })
})
