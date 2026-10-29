import { useEffect, useState } from 'react'
import { api, type PrevisionMedida as Prevision } from '../lib/api'

/** Vista previa de la medición (legacy CoilCalculator, Jorge 29-10).
 *
 *  Mientras el operario teclea los milímetros de carne, pide al servidor los
 *  kilos que quedan y la merma que se apuntaría, sin guardar nada. La cuenta
 *  la hace siempre el servidor, con la misma fórmula que al confirmar.
 */
export function PrevisionMedida({ stockItemId, radio }: { stockItemId?: string | null; radio: string }) {
  const [prevision, setPrevision] = useState<Prevision | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setPrevision(null)
    setError('')
    const mm = Number(radio)
    if (!stockItemId || radio === '' || !Number.isFinite(mm) || mm < 0) return
    let vigente = true
    const espera = setTimeout(() => {
      api
        .preverMedida(stockItemId, mm)
        .then((p) => vigente && setPrevision(p))
        .catch((e) => vigente && setError(e instanceof Error ? e.message : 'No se pudo calcular'))
    }, 300)
    return () => {
      vigente = false
      clearTimeout(espera)
    }
  }, [stockItemId, radio])

  if (error) return <p className="text-xs text-kavana-warn">{error}</p>
  if (!prevision) return null
  const kg = (n: number) => n.toLocaleString('es-ES', { maximumFractionDigits: 2 })
  return (
    <p className="text-sm text-kavana-text-dim" aria-live="polite">
      Quedan ≈ <span className="mono-data text-kavana-text">{kg(prevision.peso_restante_kg)} kg</span>
      {' · '}merma <span className="mono-data text-kavana-text">{kg(prevision.merma_kg)} kg</span>
      {' '}(el sistema cree que quedan {kg(prevision.sistema_kg)} kg)
    </p>
  )
}
