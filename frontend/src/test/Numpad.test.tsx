import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { Numpad } from '../components/Numpad'

/** Fase Usabilidad: numpad táctil para tablet en la fábrica.
 *  Botones de 64px, se opera con guantes (KAVANA_DESIGN 4.1).
 */

function Harness({
  initial = '',
  step = 1,
  allowDecimals = false,
  min = 0,
}: {
  initial?: string
  step?: number
  allowDecimals?: boolean
  min?: number
}) {
  const [value, setValue] = useState(initial)
  return (
    <div>
      <output data-testid="valor">{value}</output>
      <Numpad value={value} onChange={setValue} step={step} allowDecimals={allowDecimals} min={min} />
    </div>
  )
}

const valor = () => screen.getByTestId('valor').textContent

describe('Numpad táctil', () => {
  it('los dígitos se acumulan de izquierda a derecha', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: '7' }))
    await user.click(screen.getByRole('button', { name: '5' }))
    expect(valor()).toBe('75')
  })

  it('arrancando de 0 el primer dígito reemplaza el cero', async () => {
    const user = userEvent.setup()
    render(<Harness initial="0" />)
    await user.click(screen.getByRole('button', { name: '3' }))
    expect(valor()).toBe('3')
  })

  it('borrar quita el último dígito y deja vacío al final', async () => {
    const user = userEvent.setup()
    render(<Harness initial="12" />)
    const borrar = screen.getByRole('button', { name: /borrar/i })
    await user.click(borrar)
    expect(valor()).toBe('1')
    await user.click(borrar)
    expect(valor()).toBe('')
  })

  it('limpiar vacía el valor', async () => {
    const user = userEvent.setup()
    render(<Harness initial="99" />)
    await user.click(screen.getByRole('button', { name: /limpiar/i }))
    expect(valor()).toBe('')
  })

  it('sin decimales la tecla punto está deshabilitada', () => {
    render(<Harness allowDecimals={false} />)
    expect(screen.getByRole('button', { name: '.' })).toBeDisabled()
  })

  it('con decimales la tecla punto inserta un punto una sola vez', async () => {
    const user = userEvent.setup()
    render(<Harness allowDecimals />)
    await user.click(screen.getByRole('button', { name: '1' }))
    await user.click(screen.getByRole('button', { name: '.' }))
    await user.click(screen.getByRole('button', { name: '5' }))
    await user.click(screen.getByRole('button', { name: '.' }))
    expect(valor()).toBe('1.5')
  })

  it('aumentar suma el paso y reducir lo resta respetando el mínimo', async () => {
    const user = userEvent.setup()
    render(<Harness initial="10" step={0.5} allowDecimals min={0} />)
    await user.click(screen.getByRole('button', { name: /aumentar/i }))
    expect(valor()).toBe('10.5')
    await user.click(screen.getByRole('button', { name: /reducir/i }))
    expect(valor()).toBe('10')
    await user.click(screen.getByRole('button', { name: /reducir/i }))
    expect(valor()).toBe('9.5')
  })

  it('reducir nunca baja del mínimo', async () => {
    const user = userEvent.setup()
    render(<Harness initial="1" step={5} min={0} />)
    await user.click(screen.getByRole('button', { name: /reducir/i }))
    expect(valor()).toBe('0')
  })

  it('las teclas táctiles tienen área mínima de 64px', () => {
    render(<Harness />)
    const digitos = screen.getAllByRole('button', { name: /^\d$/ })
    expect(digitos.length).toBeGreaterThanOrEqual(10)
    for (const b of digitos) {
      expect(b.className).toContain('min-h-[64px]')
    }
  })
})
