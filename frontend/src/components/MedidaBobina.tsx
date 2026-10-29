import { useEffect, useState } from 'react'
import { api, type PrevisionMedida } from '../lib/api'

// Si falta un dato (por ejemplo, un servidor aún sin actualizar) se enseña un guion,
// nunca se rompe la pantalla del operario.
const kg = (n?: number | null) =>
  typeof n === 'number' ? n.toLocaleString('es-ES', { maximumFractionDigits: 1 }) : '—'

/** Medir la carne de una bobina y ver el resultado antes de confirmar.
 *
 *  Maquetación del CoilCalculator del legacy (Jorge, 29-10): la ficha con la
 *  que se calcula, la medida, los kg en grande y Sistema / Real / Merma en
 *  tres columnas. Sin lo que no debe tocar el operario: la densidad y el
 *  mandril son de solo lectura, no hay modo kg→mm y no se enseñan euros.
 *  La cuenta la hace siempre el servidor, con la misma fórmula que al confirmar.
 */
export function MedidaBobina({
  stockItemId,
  textoConfirmar,
  onConfirmar,
  onCancelar,
}: {
  stockItemId?: string | null
  textoConfirmar: string
  onConfirmar: (radioMm: number) => void | Promise<void>
  onCancelar?: () => void
}) {
  const [radio, setRadio] = useState('')
  const [prevision, setPrevision] = useState<PrevisionMedida | null>(null)
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

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

  const confirmar = async () => {
    setEnviando(true)
    try {
      await onConfirmar(Number(radio))
    } finally {
      setEnviando(false)
    }
  }

  const mermaReal = prevision !== null && prevision.merma_kg > 0 && !prevision.merma_dentro_del_margen

  return (
    <div className="space-y-4 text-left">
      {prevision && prevision.ancho_mm != null && (
        <dl className="grid grid-cols-3 gap-2 rounded-xl border border-kavana-border p-3 text-xs">
          <div>
            <dt className="text-kavana-text-dim">Bobina</dt>
            <dd className="mono-data">{prevision.coil_code ?? prevision.material_code ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-kavana-text-dim">Ancho</dt>
            <dd className="mono-data">{kg(prevision.ancho_mm)} mm</dd>
          </div>
          <div>
            <dt className="text-kavana-text-dim">Mandril</dt>
            <dd className="mono-data">{kg(prevision.mandril_mm)} mm</dd>
          </div>
        </dl>
      )}

      <label className="block space-y-1">
        <span className="text-sm font-semibold">Carne medida</span>
        <div className="relative">
          <input
            type="number"
            inputMode="decimal"
            step="0.5"
            min="0"
            value={radio}
            onChange={(e) => setRadio(e.target.value)}
            placeholder="Carne (mm)"
            className="mono-data w-full bg-kavana-dark border-2 border-kavana-orange rounded-xl px-4 pr-14 min-h-[60px] text-2xl text-center outline-none"
          />
          <span className="absolute right-4 top-1/2 -translate-y-1/2 text-sm text-kavana-text-dim">mm</span>
        </div>
        <span className="block text-xs text-kavana-text-dim text-center">
          Mide con el metro el espesor de la pared: del mandril al borde exterior.
        </span>
      </label>

      {error && <p className="text-sm text-kavana-danger">{error}</p>}

      <div className="rounded-xl border border-kavana-ok/40 p-4 text-center" aria-live="polite">
        <p className="text-sm text-kavana-text-dim">Quedan en la bobina</p>
        <p className="mono-data text-4xl font-bold text-kavana-ok">
          {prevision ? `${kg(prevision.peso_restante_kg)} kg` : '—'}
        </p>
      </div>

      {prevision && (
        <div className={`rounded-xl border p-3 ${mermaReal ? 'border-kavana-warn' : 'border-kavana-border'}`}>
          <div className="grid grid-cols-3 text-center">
            <div>
              <p className="text-xs text-kavana-text-dim">Sistema</p>
              <p className="mono-data font-bold">{kg(prevision.sistema_kg)} kg</p>
            </div>
            <div>
              <p className="text-xs text-kavana-text-dim">Real</p>
              <p className="mono-data font-bold text-kavana-ok">{kg(prevision.peso_restante_kg)} kg</p>
            </div>
            <div>
              <p className="text-xs text-kavana-text-dim">Merma</p>
              <p className={`mono-data font-bold ${mermaReal ? 'text-kavana-warn' : ''}`}>
                {kg(prevision.merma_kg)} kg
              </p>
            </div>
          </div>
          <p className="mt-2 text-center text-xs text-kavana-text-dim">
            {prevision.merma_kg === 0
              ? 'Sin merma: queda lo que el sistema esperaba o más.'
              : mermaReal
                ? `Merma del ${kg(prevision.merma_pct)} %. Se apuntará como chatarra al confirmar.`
                : `Puede ser solo error del metro: cada mm de carne son unos ${kg(prevision.kg_por_mm)} kg.`}
          </p>
        </div>
      )}

      <div className="flex gap-2">
        {onCancelar && (
          <button
            type="button"
            onClick={onCancelar}
            className="min-h-[56px] flex-1 rounded-xl border border-kavana-border font-bold"
          >
            Cancelar
          </button>
        )}
        <button
          type="button"
          onClick={confirmar}
          disabled={!prevision || enviando}
          className="min-h-[56px] flex-[2] rounded-xl bg-kavana-orange text-black font-bold disabled:opacity-40"
        >
          {textoConfirmar}
        </button>
      </div>
    </div>
  )
}
