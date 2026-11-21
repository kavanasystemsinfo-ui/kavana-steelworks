import { useEffect, useState } from 'react'
import { api, type MedicionPendiente } from '../lib/api'
import { MedidaBobina } from './MedidaBobina'

const UMBRAL_MERMA_DIRECTA_KG = 20
const kgDe = (p: MedicionPendiente) => p.kg_restantes ?? 0
// Sin el dato de kg se pide medir: nunca se manda a merma a ciegas
const hayQueElegir = (p: MedicionPendiente) =>
  p.kg_restantes === undefined || p.kg_restantes >= UMBRAL_MERMA_DIRECTA_KG
const textoKg = (kg: number) => kg.toLocaleString('es-ES', { maximumFractionDigits: 1 })

/** Medición del cierre de turno (Jorge, 28-10 y 21-11).
 *
 *  Por cada bobina montada con la que el operario ha producido sin medirla,
 *  pide los milímetros de radio. El sistema apunta la chatarra (lo que creía
 *  que quedaba menos lo medido) y deja la bobina en la máquina para el
 *  relevo. Con menos de 20 kg no pregunta: van a merma al cerrar. Desde 20 kg
 *  el operario elige entre medir o mandarlos a merma.
 *
 *  onPendientes recibe cuántas bobinas exigen elegir y los kg que irían a merma.
 */
export function MedirCierre({ onPendientes }: { onPendientes: (n: number, kg: number) => void }) {
  const [pendientes, setPendientes] = useState<MedicionPendiente[] | null>(null)
  const [hechas, setHechas] = useState<string[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .getMedicionesPendientes()
      .then((p) => {
        setPendientes(p)
        onPendientes(p.filter(hayQueElegir).length, p.reduce((t, x) => t + kgDe(x), 0))
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error de conexión'))
  }, [onPendientes])

  const medir = async (p: MedicionPendiente, radioMm: number) => {
    setError('')
    try {
      const res = await api.medirBobina({
        stock_item_id: p.stock_item_id,
        order_id: p.order_id,
        line_id: p.line_id,
        radio_mm: radioMm,
      })
      const quedan = (pendientes ?? []).filter((x) => x.stock_item_id !== p.stock_item_id)
      setPendientes(quedan)
      onPendientes(quedan.filter(hayQueElegir).length, quedan.reduce((t, x) => t + kgDe(x), 0))
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
      {(pendientes ?? []).filter((p) => !hayQueElegir(p)).map((p) => (
        <p key={p.stock_item_id} className="text-sm text-kavana-warn">
          {`La bobina ${p.coil_code ?? ''} tiene ${textoKg(kgDe(p))} kg sin medir: se anotarán como merma al cerrar.`}
        </p>
      ))}
      {(pendientes ?? []).filter(hayQueElegir).map((p) => (
        <div key={p.stock_item_id} className="bg-kavana-dark border border-kavana-warn rounded-xl p-3 space-y-2">
          <p className="text-sm">
            Mide la bobina <span className="mono-data">{p.coil_code}</span>
            {p.puesto ? ` en ${p.puesto}` : ''}
            {p.kg_restantes !== undefined ? ` (quedan ${textoKg(p.kg_restantes)} kg)` : ''}. Seguirá
            montada para el relevo.
          </p>
          <MedidaBobina
            stockItemId={p.stock_item_id}
            textoConfirmar="Medir y dejar montada"
            onConfirmar={(mm) => medir(p, mm)}
          />
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
