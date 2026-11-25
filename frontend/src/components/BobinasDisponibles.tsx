import { useEffect, useState } from 'react'
import { api } from '../lib/api'

type Bobina = Awaited<ReturnType<typeof api.bobinasDisponibles>>[number]

/** Cuántas bobinas se enseñan de entrada; el resto, tras «Ver más». */
const MAX_VISIBLES = 4

/** Bobinas para tocar y vincular sin saberse el código (legacy MaterialScanner):
 *  las del material de la orden y las que ya están en el puesto. Primero lo
 *  que está en la máquina, luego picos y después la más antigua (FIFO). */
export function BobinasDisponibles({
  lineId,
  onElegir,
}: {
  lineId: string
  onElegir: (bobina: Bobina) => void
}) {
  const [bobinas, setBobinas] = useState<Bobina[] | null>(null)
  const [verTodas, setVerTodas] = useState(false)

  useEffect(() => {
    let vivo = true
    api
      .bobinasDisponibles(lineId)
      .then((b) => vivo && setBobinas(Array.isArray(b) ? b : []))
      .catch(() => vivo && setBobinas([]))
    return () => {
      vivo = false
    }
  }, [lineId])

  if (bobinas === null) {
    return <p className="text-sm text-kavana-text-dim">Buscando bobinas disponibles…</p>
  }

  // Picos primero (D-019): se ven antes que la bobina nueva y se avisa de ello
  const hayPicosLibres = bobinas.some((b) => b.estado === 'pico' && !b.en_puesto)
  const hayNuevas = bobinas.some((b) => b.estado !== 'pico' && !b.en_puesto)
  // La lista ya llega ordenada (en el puesto, picos y luego la más antigua):
  // se enseñan las primeras y el resto queda tras un enlace discreto.
  const visibles = verTodas ? bobinas : bobinas.slice(0, MAX_VISIBLES)
  const ocultas = bobinas.length - visibles.length
  const indiceMasAntigua = bobinas.findIndex((b) => !b.en_puesto && b.estado !== 'pico')

  return (
    <div data-tour-step="op-disponibles" className="bg-kavana-surface border border-kavana-border border-t-4 border-t-kavana-orange rounded-xl p-4 space-y-2">
      <p className="label-industrial text-xs text-kavana-text-dim">
        Bobinas disponibles para esta orden · toca una para vincularla
      </p>
      {hayPicosLibres && hayNuevas && (
        <p className="text-sm text-kavana-warn">
          Hay picos de este material: gástalos primero. Si eliges una bobina nueva te pediremos el motivo.
        </p>
      )}
      {bobinas.length === 0 && (
        <p className="text-sm text-kavana-text-dim">
          No hay bobinas registradas de este material. Regístrala a mano con la etiqueta.
        </p>
      )}
      {visibles.map((b) => (
        <button
          key={b.id}
          type="button"
          onClick={() => onElegir(b)}
          className={`w-full flex items-center gap-3 p-3 rounded-xl text-left border min-h-[64px] transition-colors hover:border-kavana-orange ${
            b.en_puesto
              ? 'border-kavana-ok bg-kavana-dark'
              : b.estado === 'pico'
                ? 'border-kavana-warn bg-kavana-dark'
                : 'border-kavana-border bg-kavana-dark'
          }`}
        >
          <span className="flex-1 min-w-0">
            <span className="block mono-data font-bold truncate">
              {b.coil_id ?? b.lote}
              {b.en_puesto && (
                <span className="ml-2 text-[10px] uppercase tracking-wide text-kavana-ok">
                  En tu puesto
                </span>
              )}
              {b.estado === 'pico' && !b.en_puesto && (
                <span className="ml-2 text-[10px] uppercase tracking-wide text-kavana-warn">
                  Usar primero
                </span>
              )}
              {bobinas.indexOf(b) === indiceMasAntigua && (
                <span className="ml-2 text-[10px] uppercase tracking-wide text-kavana-text-dim">
                  Más antigua
                </span>
              )}
            </span>
            <span className="block text-xs text-kavana-text-dim truncate">
              {b.material_code} · lote {b.lote}
              {b.ancho_mm ? ` · ${b.ancho_mm}x${b.espesor_mm ?? '?'} mm` : ''}
              {' · '}
              {b.en_puesto
                ? 'ya en tu puesto'
                : `${b.estado === 'pico' ? 'pico / retal · ' : ''}en ${b.ubicacion ?? 'sin ubicación'}`}
              {b.antiguedad_dias != null && b.antiguedad_dias > 0
                ? ` · hace ${b.antiguedad_dias} ${b.antiguedad_dias === 1 ? 'día' : 'días'}`
                : ''}
            </span>
          </span>
          <span className="shrink-0 text-right mono-data font-bold">
            {b.peso_kg.toLocaleString('es-ES', { maximumFractionDigits: 0 })} kg
          </span>
        </button>
      ))}
      {(ocultas > 0 || (verTodas && bobinas.length > MAX_VISIBLES)) && (
        <button
          type="button"
          onClick={() => setVerTodas((v) => !v)}
          className="w-full py-1 text-center text-xs text-kavana-text-dim underline-offset-2 hover:underline hover:text-kavana-orange"
        >
          {verTodas ? 'Ver menos' : `Ver ${ocultas} más`}
        </button>
      )}
    </div>
  )
}
