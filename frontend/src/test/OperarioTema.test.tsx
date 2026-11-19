import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { OperarioPage } from '../pages/OperarioPage'

function renderPage() {
  return render(
    <MemoryRouter>
      <OperarioPage />
    </MemoryRouter>,
  )
}

const panel = () => document.querySelector('.tema-operario') as HTMLElement

describe('Tema claro/oscuro del panel de operario', () => {
  beforeEach(() => localStorage.clear())

  it('arranca en claro y alterna a oscuro y de vuelta, recordando la elección', async () => {
    const user = userEvent.setup()
    renderPage()
    expect(panel()).not.toHaveClass('tema-oscuro')

    await user.click(screen.getByRole('button', { name: /tema oscuro/i }))
    expect(panel()).toHaveClass('tema-oscuro')
    expect(localStorage.getItem('steelworks-operario-tema')).toBe('oscuro')

    await user.click(screen.getByRole('button', { name: /tema claro/i }))
    expect(panel()).not.toHaveClass('tema-oscuro')
    expect(localStorage.getItem('steelworks-operario-tema')).toBe('claro')
  })

  it('recuerda el oscuro al volver a entrar', () => {
    localStorage.setItem('steelworks-operario-tema', 'oscuro')
    renderPage()
    expect(panel()).toHaveClass('tema-oscuro')
  })
})
