import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/inter/700.css'
import '@fontsource/inter/800.css'
import { turnoActual } from '../lib/tiempo'
import { VISTAS, type Vista } from './vistas'

const HORARIO_TURNO = { A: '06:00–14:00', B: '14:00–22:00', C: '22:00–06:00' } as const

/** Hora de planta HH:MM (mismo desfase que turnoActual). */
function horaPlanta(ahora: Date): string {
  const planta = new Date(ahora.getTime() - 5 * 3600 * 1000)
  return planta.toISOString().slice(11, 16)
}

/** Marco del panel de mando: pestañas por pregunta (Turno, Planta, Costes),
 *  turno y hora siempre a la vista y acceso al modo TV. Fondo claro y fuente
 *  Inter solo aquí: el resto de la aplicación conserva su estilo.
 */
export function PanelLayout({
  vista,
  onVista,
  onModoTv,
  children,
}: {
  vista: Vista
  onVista: (v: Vista) => void
  onModoTv: () => void
  children: ReactNode
}) {
  const [ahora, setAhora] = useState(() => new Date())

  useEffect(() => {
    const timer = setInterval(() => setAhora(new Date()), 30000)
    return () => clearInterval(timer)
  }, [])

  const { turno } = turnoActual(ahora)

  return (
    <div className="tema-panel -m-4 min-h-[calc(100vh-3.5rem)] bg-p-fondo text-p-texto font-panel tabular-nums">
      <div className="bg-p-tarjeta border-b border-p-borde">
        <div className="max-w-[1360px] mx-auto px-4 sm:px-6 py-2 flex flex-wrap items-center gap-x-6 gap-y-2">
          <nav aria-label="Vistas del panel" className="flex flex-wrap gap-1">
            {VISTAS.map((v) => (
              <a
                key={v.valor}
                href={`?vista=${v.valor}`}
                aria-current={vista === v.valor ? 'page' : undefined}
                onClick={(e) => {
                  e.preventDefault()
                  onVista(v.valor)
                }}
                className={`inline-flex items-center min-h-[44px] px-4 rounded-lg text-sm no-underline ${
                  vista === v.valor
                    ? 'bg-p-texto text-white font-semibold'
                    : 'text-p-texto2 font-medium hover:bg-p-linea hover:text-p-texto'
                }`}
              >
                {v.texto}
              </a>
            ))}
          </nav>
          <div className="flex-1" />
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
            <span className="text-p-texto2">
              Turno {turno} · {HORARIO_TURNO[turno]}
            </span>
            <span className="text-lg font-bold" aria-label="Hora de planta">
              {horaPlanta(ahora)}
            </span>
            <button
              type="button"
              onClick={onModoTv}
              className="inline-flex items-center gap-2 min-h-[44px] px-3.5 rounded-lg border border-p-borde bg-p-tarjeta text-p-texto font-medium cursor-pointer hover:border-p-texto2"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <rect x="2" y="4" width="20" height="13" rx="2" />
                <path d="M8 21h8M12 17v4" />
              </svg>
              Modo TV
            </button>
          </div>
        </div>
      </div>
      <div className="max-w-[1360px] mx-auto px-4 sm:px-6 pt-7 pb-12 flex flex-col gap-6">
        {children}
      </div>
    </div>
  )
}
