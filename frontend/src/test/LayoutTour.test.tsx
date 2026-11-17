// Tour guiado en el Layout: se abre solo la primera vez que entra un visitante de la demo con cada rol
// y se repite con el botón de la barra. También se comprueba que los recorridos están bien enlazados.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { Layout } from '../components/layout/Layout'
import * as api from '../lib/api'
import { TOUR_DE_VISTA, TOUR_INICIAL, crearTours, tourDelOperario } from '../lib/tours'

vi.mock('../lib/api', () => ({
  api: { logout: vi.fn() },
  getJwtPayload: vi.fn(),
}))

function montar(ruta: string) {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/operario" element={<p>Panel operario</p>} />
          <Route path="/supervisor" element={<p>Panel supervisor</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

function comoRol(role: string, demo: boolean) {
  vi.mocked(api.getJwtPayload).mockReturnValue({ role, demo } as never)
}

describe('Tour guiado en el Layout', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })
  afterEach(() => cleanup())

  it('se abre solo la primera vez que un visitante de la demo entra con un rol, y no vuelve', async () => {
    comoRol('operator', true)
    const primera = montar('/operario')
    expect(await screen.findByRole('dialog', { name: 'Tres pasos y a producir' }, { timeout: 3000 })).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(localStorage.getItem('steelworks-tour-visto-operator')).toBe('true')
    primera.unmount()

    montar('/operario')
    await new Promise((r) => setTimeout(r, 1500))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('cada rol tiene su propio «visto»: haber visto el del operario no oculta el del supervisor', async () => {
    localStorage.setItem('steelworks-tour-visto-operator', 'true')
    comoRol('supervisor', true)
    montar('/supervisor')
    expect(await screen.findByRole('dialog', { name: 'Una pestaña por pregunta' }, { timeout: 3000 })).toBeInTheDocument()
  })

  it('no se abre solo con una cuenta propia (no es la demo)', async () => {
    comoRol('operator', false)
    montar('/operario')
    await new Promise((r) => setTimeout(r, 1500))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('el botón Tour abre el recorrido de la pestaña del supervisor en la que estás', async () => {
    localStorage.setItem('steelworks-tour-visto-supervisor', 'true')
    comoRol('supervisor', true)
    window.history.replaceState({}, '', '/supervisor?vista=planta')
    montar('/supervisor?vista=planta')
    fireEvent.click(screen.getByRole('button', { name: /Tour/ }))
    expect(await screen.findByRole('dialog', { name: '¿De dónde sale la eficiencia?' })).toBeInTheDocument()
  })

  it('en el operario, el botón Tour lee la pantalla de la URL aunque cambie sin pasar por el router', async () => {
    localStorage.setItem('steelworks-tour-visto-operator', 'true')
    comoRol('operator', true)
    window.history.replaceState({}, '', '/operario')
    montar('/operario')
    window.history.replaceState({}, '', '/operario?ws=AR-1')
    fireEvent.click(screen.getByRole('button', { name: /Tour/ }))
    expect(await screen.findByRole('dialog', { name: 'La cola de órdenes' })).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    window.history.replaceState({}, '', '/operario?ws=AR-1&order=abc')
    fireEvent.click(screen.getByRole('button', { name: /Tour/ }))
    expect(await screen.findByRole('dialog', { name: 'Siempre sabes qué toca' })).toBeInTheDocument()
  })
})

describe('Recorridos de Steelworks', () => {
  const tours = crearTours({ ir: () => {} })

  it('cada rol y cada pestaña del supervisor tienen su recorrido', () => {
    for (const clave of [...Object.values(TOUR_INICIAL), ...Object.values(TOUR_DE_VISTA)]) {
      expect(tours[clave]?.length, clave).toBeGreaterThan(0)
    }
  })

  it('el operario tiene un recorrido por pantalla, según lo que dice la URL', () => {
    expect(tourDelOperario(new URLSearchParams(''))).toBe('operario-puesto')
    expect(tourDelOperario(new URLSearchParams('ws=AR-1'))).toBe('operario-cola')
    expect(tourDelOperario(new URLSearchParams('ws=AR-1&order=abc'))).toBe('operario-bobina')
    for (const clave of ['operario-puesto', 'operario-cola', 'operario-bobina']) {
      expect(tours[clave]?.length, clave).toBeGreaterThan(0)
    }
  })

  it('los pasos «siguiente» apuntan a un recorrido que existe y los id no se repiten', () => {
    const ids = new Set<string>()
    for (const pasos of Object.values(tours)) {
      for (const paso of pasos) {
        expect(ids.has(paso.id), paso.id).toBe(false)
        ids.add(paso.id)
        if (paso.siguiente) expect(tours[paso.siguiente], paso.siguiente).toBeDefined()
      }
    }
  })
})
