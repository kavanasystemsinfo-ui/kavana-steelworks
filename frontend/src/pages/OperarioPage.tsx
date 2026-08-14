import { useState } from 'react'

/** Panel de Operario (tablet): una acción principal a la vez.
 *  Directriz Jorge: no abrumar, guía de acción visible, sin perder
 *  funcionalidad. El escaneo/vinculación de bobina es el paso central.
 */
export function OperarioPage() {
  const [coilId, setCoilId] = useState('')
  const [vinculada, setVinculada] = useState(false)

  const handleScan = async (e: React.FormEvent) => {
    e.preventDefault()
    setVinculada(true)
  }

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      {/* Guía de acción: el siguiente paso siempre identificable */}
      <div className="step-guide">
        <p className="label-industrial text-xs text-kavana-text-dim">
          Paso actual
        </p>
        <p className="text-lg font-bold">
          {vinculada ? 'Producir piezas' : 'Vincular bobina'}
        </p>
      </div>

      {/* Acción principal: escaneo de bobina (botón grande táctil) */}
      {!vinculada ? (
        <form
          onSubmit={handleScan}
          className="bg-kavana-surface border border-kavana-border rounded-sm p-6 space-y-4"
        >
          <label className="block">
            <span className="label-industrial text-xs text-kavana-text-dim">
              Código de bobina
            </span>
            <input
              value={coilId}
              onChange={(e) => setCoilId(e.target.value)}
              placeholder="Escanea la etiqueta o escribe el ID"
              className="mono-data mt-1 w-full bg-kavana-dark border border-kavana-border rounded-sm px-3 py-3 min-h-[52px] text-lg focus:border-kavana-orange outline-none"
              autoFocus
            />
          </label>
          <button
            type="submit"
            disabled={!coilId.trim()}
            className="w-full min-h-[64px] bg-kavana-orange text-black font-bold uppercase tracking-widest rounded-sm disabled:opacity-40 hover:opacity-90 transition-opacity"
          >
            🔗 Vincular bobina
          </button>
        </form>
      ) : (
        <div className="bg-kavana-surface border border-kavana-border rounded-sm p-6 text-center space-y-4">
          <p className="mono-data text-2xl text-kavana-ok">COIL-{coilId}</p>
          <p className="text-kavana-text-dim">
            Bobina vinculada a la orden. Registra producción para consumir kg.
          </p>
          <button
            onClick={() => {
              setVinculada(false)
              setCoilId('')
            }}
            className="w-full min-h-[64px] bg-kavana-orange text-black font-bold uppercase tracking-widest rounded-sm hover:opacity-90 transition-opacity"
          >
            ➕ Registrar producción
          </button>
        </div>
      )}

      {/* Datos de apoyo colapsados: solo si el operario los necesita */}
      <details className="bg-kavana-surface border border-kavana-border rounded-sm p-4">
        <summary className="label-industrial text-xs text-kavana-text-dim cursor-pointer">
          Detalles de la orden
        </summary>
        <p className="mt-2 text-sm text-kavana-text-dim">
          Aquí se mostrará material, dimensiones, peso y piezas objetivo.
        </p>
      </details>
    </div>
  )
}
