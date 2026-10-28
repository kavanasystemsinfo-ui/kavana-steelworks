import { useEffect, useState } from 'react'
import { api } from '../lib/api'

type Bobina = Awaited<ReturnType<typeof api.bobinasDisponibles>>[number]

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

  return (
    <div className="bg-kavana-surface border border-kavana-border rounded-sm p-4 space-y-2">
      <p className="label-industrial text-xs text-kavana-text-dim">
        Bobinas disponibles para esta orden · toca una para vincularla
      </p>
      {bobinas.length === 0 && (
        <p className="text-sm text-kavana-text-dim">
          No hay bobinas registradas de este material. Regístrala a mano con la etiqueta.
        </p>
      )}
      {bobinas.map((b, i) => (
        <button
          key={b.id}
          type="button"
          onClick={() => onElegir(b)}
          className={`w-full flex items-center gap-3 p-3 rounded-sm text-left border min-h-[64px] transition-colors hover:border-kavana-orange ${
            b.en_puesto
              ? 'border-kavana-ok bg-kavana-dark'
              : b.estado === 'pico'
                ? 'border-kavana-warn bg-kavana-dark'
                : 'border-kavana-border bg-kavana-dark'
          }`}
        >
          <span className="w-8 h-8 shrink-0 rounded-full flex items-center justify-center text-xs font-black bg-kavana-surface">
            {b.en_puesto ? '📍' : b.estado === 'pico' ? '⚡' : i + 1}
          </span>
          <span className="flex-1 min-w-0">
            <span className="block mono-data font-bold truncate">{b.coil_id ?? b.lote}</span>
            <span className="block text-xs text-kavana-text-dim truncate">
              {b.material_code} · lote {b.lote}
              {b.ancho_mm ? ` · ${b.ancho_mm}x${b.espesor_mm ?? '?'} mm` : ''}
              {' · '}
              {b.en_puesto ? 'ya en tu puesto' : b.estado === 'pico' ? 'pico / retal' : (b.ubicacion ?? 'sin ubicación')}
            </span>
          </span>
          <span className="shrink-0 text-right mono-data font-bold">
            {b.peso_kg.toLocaleString('es-ES', { maximumFractionDigits: 0 })} kg
          </span>
        </button>
      ))}
    </div>
  )
}
