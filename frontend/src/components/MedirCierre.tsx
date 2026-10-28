import { useEffect, useState } from 'react'
import { api, type MedicionPendiente } from '../lib/api'

/** Medición obligatoria del cierre de turno (Jorge, 28-10).
 *
 *  Por cada bobina montada con la que el operario ha producido sin medirla,
 *  pide los milímetros de radio. El sistema apunta la chatarra (lo que creía
 *  que quedaba menos lo medido) y deja la bobina en la máquina para el
 *  relevo. Mientras quede alguna, no se puede cerrar la jornada ni la sesión.
 */
export function MedirCierre({ onPendientes }: { onPendientes: (n: number) => void }) {
  const [pendientes, setPendientes] = useState<MedicionPendiente[] | null>(null)
  const [radios, setRadios] = useState<Record<string, string>>({})
  const [hechas, setHechas] = useState<string[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .getMedicionesPendientes()
      .then((p) => {
        setPendientes(p)
        onPendientes(p.length)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error de conexión'))
  }, [onPendientes])

  const medir = async (p: MedicionPendiente) => {
    setError('')
    try {
      const res = await api.medirBobina({
        stock_item_id: p.stock_item_id,
        order_id: p.order_id,
        line_id: p.line_id,
        radio_mm: Number(radios[p.stock_item_id]),
      })
      const quedan = (pendientes ?? []).filter((x) => x.stock_item_id !== p.stock_item_id)
      setPendientes(quedan)
      onPendientes(quedan.length)
      setHechas((h) => [
        ...h,
        `${p.coil_code ?? 'Bobina'}: quedan ${res.peso_restante_kg.toLocaleString('es-ES')} kg montados · chatarra ${res.chatarra_kg.toLocaleString('es-ES')} kg`,
      ])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al medir')
    }
  }

  if (pendientes === null && !error) {
    return <p className="text-sm text-kavana-text-dim">Comprobando bobinas montadas…</p>
  }

  return (
    <div className="space-y-2">
      {(pendientes ?? []).map((p) => (
        <div key={p.stock_item_id} className="bg-kavana-dark border border-kavana-warn rounded-sm p-3 space-y-2">
          <p className="text-sm">
            Mide el radio de la bobina <span className="mono-data">{p.coil_code}</span>
            {p.puesto ? ` en ${p.puesto}` : ''}. Seguirá montada para el relevo.
          </p>
          <div className="flex gap-2">
            <input
              type="number"
              inputMode="decimal"
              min="0"
              aria-label={`Radio de ${p.coil_code ?? 'la bobina'} en mm`}
              placeholder="Radio (mm)"
              value={radios[p.stock_item_id] ?? ''}
              onChange={(e) => setRadios((r) => ({ ...r, [p.stock_item_id]: e.target.value }))}
              className="mono-data flex-1 bg-kavana-dark border border-kavana-border rounded-sm px-3 min-h-[52px] text-lg focus:border-kavana-orange outline-none"
            />
            <button
              type="button"
              onClick={() => medir(p)}
              disabled={radios[p.stock_item_id] === undefined || radios[p.stock_item_id] === ''}
              className="min-h-[52px] px-4 bg-kavana-orange text-black font-bold uppercase tracking-widest rounded-sm disabled:opacity-40"
            >
              Medir
            </button>
          </div>
        </div>
      ))}
      {hechas.map((h) => (
        <p key={h} className="text-sm text-kavana-ok">
          ✓ {h}
        </p>
      ))}
      {error && <p className="text-sm text-kavana-danger">{error}</p>}
    </div>
  )
}
