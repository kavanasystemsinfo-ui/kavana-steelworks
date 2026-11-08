import type { MotivoSaltoPico } from '../lib/api'

export interface PicoAviso {
  coil_id: string
  peso_kg: number
}

const MOTIVOS: { valor: MotivoSaltoPico; texto: string }[] = [
  { valor: 'pico_corto', texto: 'No llega para la orden' },
  { valor: 'pico_danado', texto: 'Está en mal estado' },
  { valor: 'no_localizado', texto: 'No lo encuentro' },
  { valor: 'otro', texto: 'Otro motivo' },
]

/** Picos primero (D-019): hay picos de este material y se ha elegido una bobina nueva.
 *  No se impide: se pide un motivo de un toque, que queda en la trazabilidad. */
export function AvisoPicos({
  picos,
  onMotivo,
  onUsarPico,
}: {
  picos: PicoAviso[]
  onMotivo: (motivo: MotivoSaltoPico) => void
  onUsarPico: () => void
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Hay picos de este material"
      className="bg-kavana-surface border-2 border-kavana-warn rounded-xl p-4 space-y-3"
    >
      <div>
        <p className="m-0 font-bold">Hay picos de este material</p>
        <p className="m-0 text-sm text-kavana-text-dim">
          Gástalos antes de abrir una bobina nueva:{' '}
          {picos
            .map((p) => `${p.coil_id} (${p.peso_kg.toLocaleString('es-ES', { maximumFractionDigits: 0 })} kg)`)
            .join(', ')}
          .
        </p>
      </div>

      <button
        type="button"
        onClick={onUsarPico}
        className="w-full min-h-[56px] rounded-xl bg-kavana-orange text-black font-bold"
      >
        Elegir un pico
      </button>

      <div>
        <p className="m-0 mb-2 text-sm text-kavana-text-dim">
          Si prefieres la bobina nueva, ¿por qué?
        </p>
        <div className="grid grid-cols-2 gap-2">
          {MOTIVOS.map((m) => (
            <button
              key={m.valor}
              type="button"
              onClick={() => onMotivo(m.valor)}
              className="min-h-[56px] rounded-xl border border-kavana-border bg-kavana-dark px-2 text-sm font-semibold hover:border-kavana-orange"
            >
              {m.texto}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
