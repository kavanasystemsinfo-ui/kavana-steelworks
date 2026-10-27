import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PanelLayout } from '../panel/PanelLayout'
import { BarraProgreso, EstadoBanner, KpiCard, Pastilla } from '../panel/ui'
import { vistaDeUrl } from '../panel/vistas'

describe('componentes del panel de mando', () => {
  it('KpiCard pinta la cifra, su unidad, el estado y el contexto', () => {
    render(
      <KpiCard
        label="Piezas buenas"
        valor="1.180"
        unidad="de 2.000"
        estado={{ texto: 'En ritmo', tono: 'ok' }}
        contexto="Plan a esta hora: 1.175"
      />,
    )
    const tarjeta = screen.getByText('Piezas buenas').closest('article')!
    expect(tarjeta).toHaveTextContent('1.180')
    expect(tarjeta).toHaveTextContent('de 2.000')
    expect(tarjeta).toHaveTextContent('En ritmo')
    expect(tarjeta).toHaveTextContent('Plan a esta hora: 1.175')
  })

  it('la pastilla siempre lleva texto y el color de su tono', () => {
    render(<Pastilla tono="mal">Parado</Pastilla>)
    expect(screen.getByText('Parado').className).toContain('text-p-mal')
  })

  it('la barra de progreso se recorta entre 0 y 100', () => {
    render(<BarraProgreso pct={140} etiqueta="Avance" />)
    expect(screen.getByRole('progressbar', { name: 'Avance' })).toHaveAttribute('aria-valuenow', '100')
  })

  it('el banner de estado muestra la frase y el detalle', () => {
    render(<EstadoBanner tono="aviso" titular="En ritmo, pero con 2 puestos parados" detalle="PUNZ-1" />)
    const banner = screen.getByRole('region', { name: 'Estado' })
    expect(banner).toHaveTextContent('En ritmo, pero con 2 puestos parados')
    expect(banner.className).toContain('bg-p-aviso-bg')
  })
})

describe('PanelLayout', () => {
  it('marca la pestaña activa y avisa al cambiar de vista', async () => {
    const onVista = vi.fn()
    const user = userEvent.setup()
    render(
      <PanelLayout vista="turno" onVista={onVista} onModoTv={() => {}}>
        <p>contenido</p>
      </PanelLayout>,
    )

    expect(screen.getByRole('link', { name: 'Turno' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'Costes' })).not.toHaveAttribute('aria-current')
    expect(screen.getByRole('link', { name: 'Costes' })).toHaveAttribute('href', '?vista=costes')

    await user.click(screen.getByRole('link', { name: 'Costes' }))
    expect(onVista).toHaveBeenCalledWith('costes')
  })

  it('una vista desconocida en la URL abre Turno', () => {
    expect(vistaDeUrl('costes')).toBe('costes')
    expect(vistaDeUrl('cualquiera')).toBe('turno')
    expect(vistaDeUrl(null)).toBe('turno')
  })
})
