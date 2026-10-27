import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { PuestoEstado } from '../lib/api'
import { haceCuanto } from '../lib/tiempo'

/** Etiqueta y color de cada estado (el rojo del andon es la incidencia). */
const ESTADOS: Record<PuestoEstado['estado'], { label: string; clase: string }> = {
  incidencia: { label: 'Incidencia', clase: 'border-kavana-danger text-kavana-danger' },
  en_curso: { label: 'En curso', clase: 'border-kavana-ok text-kavana-ok' },
  parado: { label: 'Parado', clase: 'border-kavana-warn text-kavana-warn' },
  pendiente: { label: 'Pendiente', clase: 'border-kavana-steel text-kavana-text-dim' },
  libre: { label: 'Libre', clase: 'border-kavana-border text-kavana-text-dim' },
}

/** Monitor de puestos en planta: una tarjeta por puesto, polling cada 10 s.
 *  `andon` agranda todo para una TV de planta (mismo dato, sin pantalla nueva).
 */
export function PuestosMonitor({ andon = false }: { andon?: boolean }) {
  const [puestos, setPuestos] = useState<PuestoEstado[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const cargar = () => {
      api.getPuestos()
        .then((data) => {
          setPuestos(Array.isArray(data) ? data : [])
          setError('')
        })
        .catch(() => setError('No se pudo cargar el estado de los puestos'))
    }
    cargar()
    const timer = setInterval(cargar, 10000)
    return () => clearInterval(timer)
  }, [])

  if (error) return <p className="text-kavana-danger text-sm">{error}</p>
  if (puestos === null) return <p className="text-kavana-text-dim text-sm">Cargando puestos...</p>
  if (puestos.length === 0) {
    return (
      <p className="text-kavana-text-dim text-sm">
        No hay puestos configurados. Créalos en Admin → Puestos.
      </p>
    )
  }

  return (
    <div
      className={`grid gap-3 ${
        andon ? 'grid-cols-1 md:grid-cols-2 xl:grid-cols-3' : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'
      }`}
    >
      {puestos.map((p) => {
        const est = ESTADOS[p.estado]
        const progreso =
          p.orden && p.orden.objetivo > 0
            ? Math.min(100, Math.round((p.orden.piezas / p.orden.objetivo) * 100))
            : 0
        return (
          <div
            key={p.code}
            data-testid={`puesto-${p.code}`}
            className={`bg-kavana-surface border-2 rounded-sm ${andon ? 'p-6' : 'p-4'} space-y-2 ${est.clase.split(' ')[0]}`}
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className={`font-bold text-kavana-text ${andon ? 'text-2xl' : 'text-base'}`}>
                  {p.name}
                </p>
                <p className="text-xs text-kavana-text-dim">{p.code}</p>
              </div>
              <span
                className={`label-industrial border rounded-sm px-2 py-0.5 ${andon ? 'text-base' : 'text-[10px]'} ${est.clase}`}
              >
                {est.label}
              </span>
            </div>

            {p.orden ? (
              <div className={andon ? 'text-lg space-y-1' : 'text-sm space-y-1'}>
                <p>
                  <span className="font-semibold">{p.orden.numero}</span>
                  {p.orden.cliente && (
                    <span className="text-kavana-text-dim"> · {p.orden.cliente}</span>
                  )}
                </p>
                <p className="text-kavana-text-dim">
                  Bobina: <span className="mono-data text-kavana-text">{p.orden.bobina ?? 'sin vincular'}</span>
                </p>
                <div>
                  <div className="flex justify-between text-xs text-kavana-text-dim">
                    <span>Piezas</span>
                    <span className="mono-data">
                      {p.orden.piezas.toLocaleString('es-ES')}/{p.orden.objetivo.toLocaleString('es-ES')}
                    </span>
                  </div>
                  <div className="h-2 bg-kavana-panel rounded-sm overflow-hidden">
                    <div className="h-full bg-kavana-orange" style={{ width: `${progreso}%` }} />
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-sm text-kavana-text-dim">Sin orden asignada</p>
            )}

            {p.incidencias_abiertas.length > 0 && (
              <p className={`text-kavana-danger ${andon ? 'text-lg' : 'text-sm'}`}>
                ⚠ {p.incidencias_abiertas[0].descripcion}
                {p.incidencias_abiertas.length > 1 && ` (+${p.incidencias_abiertas.length - 1})`}
              </p>
            )}

            <p className="text-xs text-kavana-text-dim">
              {p.ultima_actividad
                ? `Última actividad ${haceCuanto(p.ultima_actividad.timestamp)}${
                    p.ultima_actividad.operario ? ` · ${p.ultima_actividad.operario}` : ''
                  }`
                : 'Sin actividad registrada'}
            </p>
          </div>
        )
      })}
    </div>
  )
}
