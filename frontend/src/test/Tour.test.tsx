import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Tour, type TourStep } from '../components/Tour'

const pasos: TourStep[] = [
  { id: 'a', title: 'Primero', content: 'Texto uno\nSegunda línea' },
  { id: 'b', title: 'Segundo', content: 'Texto dos' },
  { id: 'c', title: 'Tercero', content: 'Texto tres' },
]

function montar(extra: Partial<Parameters<typeof Tour>[0]> = {}) {
  const props = {
    steps: pasos,
    isOpen: true,
    onClose: vi.fn(),
    onComplete: vi.fn(),
    onIr: vi.fn(),
    ...extra,
  }
  render(<Tour {...props} />)
  return props
}

describe('Tour', () => {
  it('no pinta nada si está cerrado', () => {
    montar({ isOpen: false })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('enseña el primer paso con su contador y las líneas del texto', () => {
    montar()
    expect(screen.getByRole('dialog', { name: 'Primero' })).toBeInTheDocument()
    expect(screen.getByText('Paso 1 de 3')).toBeInTheDocument()
    expect(screen.getByText('Segunda línea')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Atrás/ })).not.toBeInTheDocument()
  })

  it('Siguiente y Atrás recorren los pasos; el último dice Finalizar y completa', () => {
    const props = montar()
    fireEvent.click(screen.getByRole('button', { name: /Siguiente/ }))
    expect(screen.getByText('Paso 2 de 3')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Atrás/ }))
    expect(screen.getByText('Paso 1 de 3')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Siguiente/ }))
    fireEvent.click(screen.getByRole('button', { name: /Siguiente/ }))
    expect(screen.getByText('Paso 3 de 3')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Finalizar' }))
    expect(props.onComplete).toHaveBeenCalledTimes(1)
    expect(props.onClose).toHaveBeenCalledTimes(1)
  })

  it('las flechas del teclado navegan y Esc cierra', () => {
    const props = montar()
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(screen.getByText('Paso 2 de 3')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(screen.getByText('Paso 1 de 3')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(props.onComplete).toHaveBeenCalledTimes(1)
    expect(props.onClose).toHaveBeenCalledTimes(1)
  })

  it('Omitir tour cierra y lo da por visto', () => {
    const props = montar()
    fireEvent.click(screen.getByRole('button', { name: 'Omitir tour' }))
    expect(props.onComplete).toHaveBeenCalledTimes(1)
    expect(props.onClose).toHaveBeenCalledTimes(1)
  })

  it('un paso con «siguiente» ofrece seguir con otro tour', () => {
    const props = montar({
      steps: [{ id: 'x', title: 'Fin de Resumen', content: 'Hola', siguiente: 'personal' }],
    })
    fireEvent.click(screen.getByRole('button', { name: 'Sí, llévame' }))
    expect(props.onIr).toHaveBeenCalledWith('personal')
    fireEvent.click(screen.getByRole('button', { name: 'No, omitir' }))
    expect(props.onClose).toHaveBeenCalledTimes(1)
  })

  it('ejecuta la acción del paso al llegar', () => {
    const accion = vi.fn()
    montar({ steps: [{ id: 'x', title: 'Con acción', content: 'Hola', action: accion }] })
    expect(accion).toHaveBeenCalledTimes(1)
  })

  it('sin ancla (o con un ancla que no existe) el paso sale centrado y sin recuadro', async () => {
    montar({ steps: [{ id: 'x', anchor: '.no-existe', title: 'Sin elemento', content: 'Hola' }] })
    await new Promise((r) => setTimeout(r, 200))
    expect(document.querySelector('.tour-recuadro')).toBeNull()
    expect(document.querySelector('.tour-velo')).not.toBeNull()
    expect(screen.getByRole('dialog', { name: 'Sin elemento' })).toBeInTheDocument()
  })

  it('con ancla visible resalta ese elemento', async () => {
    const el = document.createElement('div')
    el.className = 'objetivo-tour'
    el.getBoundingClientRect = () => new DOMRect(100, 100, 200, 50)
    el.scrollIntoView = vi.fn()
    document.body.append(el)
    try {
      montar({ steps: [{ id: 'x', anchor: '.objetivo-tour', title: 'Con elemento', content: 'Hola' }] })
      await waitFor(() => expect(document.querySelector('.tour-recuadro')).not.toBeNull())
      expect(document.querySelector('.tour-velo')).toBeNull()
      expect(el.scrollIntoView).toHaveBeenCalled()
    } finally {
      el.remove()
    }
  })
})
