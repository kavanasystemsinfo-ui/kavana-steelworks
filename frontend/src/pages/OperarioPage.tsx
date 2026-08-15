import { useEffect, useState } from 'react'
import { api, getTenantId, type EventData } from '../lib/api'

interface CoilScan {
  id: string
  lote: string
  coil_id: string | null
  peso_kg: number
  ancho_mm: number | null
  espesor_mm: number | null
  material_code: string | null
  material_name: string | null
  estado: string
  ubicacion: string | null
  modo: string
}

/** Panel de Operario (tablet): una acción principal a la vez.
 *  Directriz Jorge: no abrumar, guía de acción visible, sin perder
 *  funcionalidad. El escaneo/vinculación de bobina es el paso central.
 */
export function OperarioPage() {
  const [coilId, setCoilId] = useState('')
  const [scan, setScan] = useState<CoilScan | null>(null)
  const [scanError, setScanError] = useState('')
  const [vinculada, setVinculada] = useState(false)
  const [events, setEvents] = useState<EventData[]>([])

  // Polling ligero de eventos del tenant (WebSocket completo en Fase 4)
  useEffect(() => {
    const tenantId = getTenantId()
    if (!tenantId) return
    const timer = setInterval(() => {
      api
        .getEvents(tenantId)
        .then((r) => setEvents(r.events.slice(-3)))
        .catch(() => {})
    }, 5000)
    return () => clearInterval(timer)
  }, [])

  const handleScan = async (e: React.FormEvent) => {
    e.preventDefault()
    setScanError('')
    setScan(null)
    try {
      const res = await fetch(
        `/api/v1/stock-items/scan?coil_id=${encodeURIComponent(coilId.trim())}`,
      )
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? 'Error al escanear')
      }
      const data = await res.json()
      if (!data) {
        setScanError('Bobina no encontrada. Comprueba el código.')
        return
      }
      setScan(data)
    } catch (err) {
      setScanError(err instanceof Error ? err.message : 'Error de conexión')
    }
  }

  const handleLink = async () => {
    setScanError('')
    if (!scan) return
    try {
      // TODO(Fase 3): order_id/line_id desde la orden activa del operario
      setVinculada(true)
    } catch (err) {
      setScanError(err instanceof Error ? err.message : 'Error al vincular')
    }
  }

  const [radioMm, setRadioMm] = useState('')
  const [finBobinaMsg, setFinBobinaMsg] = useState('')
  const [piezas, setPiezas] = useState('')
  const [horas, setHoras] = useState('')

  const handleRecordProduction = async (e: React.FormEvent) => {
    e.preventDefault()
    setFinBobinaMsg('')
    if (!scan) return
    try {
      // TODO(Fase 3): order_id/line_id desde la orden activa del operario
      const res = await fetch('/api/v1/production/record', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          order_id: '00000000-0000-0000-0000-000000000000',
          line_id: '00000000-0000-0000-0000-000000000000',
          incremental_quantity: Number(piezas),
          hours_worked: Number(horas || 0),
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? 'Error al registrar producción')
      }
      const data = await res.json()
      setFinBobinaMsg(
        `${data.incremental_quantity} piezas registradas · ${data.consumed_amount} ${data.consumption_unit} consumidos (${data.calculation_method})`,
      )
      setPiezas('')
      setHoras('')
    } catch (err) {
      setFinBobinaMsg(
        err instanceof Error ? err.message : 'Error al registrar producción',
      )
    }
  }

  const handleFinBobina = async (e: React.FormEvent) => {
    e.preventDefault()
    setFinBobinaMsg('')
    if (!scan) return
    try {
      // TODO(Fase 3): order_id/line_id desde la orden activa del operario
      const res = await fetch('/api/v1/stock-items/fin-bobina', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stock_item_id: scan.id,
          order_id: '00000000-0000-0000-0000-000000000000',
          line_id: '00000000-0000-0000-0000-000000000000',
          radio_mm: Number(radioMm),
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? 'Error en fin de bobina')
      }
      const data = await res.json()
      setFinBobinaMsg(
        `${data.msg}: quedan ${data.peso_restante_kg} kg, ${data.merma_kg} kg de merma (${data.merma_cost} €)`,
      )
      setVinculada(false)
      setScan(null)
      setCoilId('')
    } catch (err) {
      setFinBobinaMsg(
        err instanceof Error ? err.message : 'Error al cerrar bobina',
      )
    }
  }

  const handleRetirarPico = async () => {
    setFinBobinaMsg('')
    if (!scan) return
    try {
      const res = await fetch('/api/v1/stock-items/retirar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stock_item_id: scan.id,
          order_id: '00000000-0000-0000-0000-000000000000',
          line_id: '00000000-0000-0000-0000-000000000000',
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? 'Error al retirar pico')
      }
      const data = await res.json()
      setFinBobinaMsg(data.msg)
      setVinculada(false)
      setScan(null)
      setCoilId('')
    } catch (err) {
      setFinBobinaMsg(
        err instanceof Error ? err.message : 'Error al retirar pico',
      )
    }
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

          {scanError && (
            <p className="text-kavana-danger text-sm border border-kavana-danger/40 rounded-sm p-2">
              {scanError}
            </p>
          )}

          {/* Ficha de la bobina escaneada (modo automático) */}
          {scan && (
            <div className="bg-kavana-dark border border-kavana-border rounded-sm p-4 space-y-2">
              <p className="mono-data text-xl text-kavana-ok">
                {scan.coil_id ?? scan.lote}
              </p>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <Data label="Material" value={scan.material_code ?? '-'} />
                <Data label="Lote" value={scan.lote} />
                <Data label="Peso" value={`${scan.peso_kg} kg`} />
                <Data
                  label="Dimensiones"
                  value={
                    scan.ancho_mm && scan.espesor_mm
                      ? `${scan.ancho_mm} x ${scan.espesor_mm} mm`
                      : '-'
                  }
                />
                <Data label="Ubicación" value={scan.ubicacion ?? '-'} />
                <Data label="Estado" value={scan.estado} />
              </div>
              <button
                type="button"
                onClick={handleLink}
                className="w-full min-h-[64px] bg-kavana-orange text-black font-bold uppercase tracking-widest rounded-sm hover:opacity-90 transition-opacity"
              >
                🔗 Vincular a mi orden
              </button>
            </div>
          )}

          {!scan && (
            <button
              type="submit"
              disabled={!coilId.trim()}
              className="w-full min-h-[64px] bg-kavana-orange text-black font-bold uppercase tracking-widest rounded-sm disabled:opacity-40 hover:opacity-90 transition-opacity"
            >
              🔍 Escanear bobina
            </button>
          )}
        </form>
      ) : (
        <div className="bg-kavana-surface border border-kavana-border rounded-sm p-6 text-center space-y-4">
          <p className="mono-data text-2xl text-kavana-ok">
            {scan?.coil_id ?? `COIL-${coilId}`}
          </p>
          <p className="text-kavana-text-dim">
            Bobina vinculada a la orden. Registra producción para consumir kg.
          </p>

          {finBobinaMsg && (
            <p className="text-kavana-ok text-sm border border-kavana-ok/40 rounded-sm p-2">
              {finBobinaMsg}
            </p>
          )}

          {/* Fin de bobina: medir los milímetros de radio restantes (visión Jorge) */}
          <form
            onSubmit={handleFinBobina}
            className="bg-kavana-dark border border-kavana-border rounded-sm p-4 space-y-3 text-left"
          >
            <p className="label-industrial text-xs text-kavana-text-dim">
              Fin de bobina: mide el radio con el metro
            </p>
            <input
              type="number"
              step="0.5"
              min="0"
              value={radioMm}
              onChange={(e) => setRadioMm(e.target.value)}
              placeholder="Radio restante (mm)"
              className="mono-data w-full bg-kavana-surface border border-kavana-border rounded-sm px-3 py-3 min-h-[52px] text-lg focus:border-kavana-orange outline-none"
              required
            />
            <button
              type="submit"
              className="w-full min-h-[56px] border border-kavana-orange text-kavana-orange font-bold uppercase tracking-widest rounded-sm hover:bg-kavana-orange hover:text-black transition-colors"
            >
              🏁 Cerrar bobina (merma real)
            </button>
            <button
              type="button"
              onClick={handleRetirarPico}
              className="w-full min-h-[56px] border border-kavana-border text-kavana-text-dim font-bold uppercase tracking-widest rounded-sm hover:border-kavana-orange hover:text-kavana-orange transition-colors"
            >
              📦 Retirar pico a inventario
            </button>
          </form>

          {/* Registrar producción: piezas buenas (auto-consumo FIFO) */}
          <form
            onSubmit={handleRecordProduction}
            className="bg-kavana-dark border border-kavana-border rounded-sm p-4 space-y-3 text-left"
          >
            <p className="label-industrial text-xs text-kavana-text-dim">
              Registrar producción
            </p>
            <div className="grid grid-cols-2 gap-2">
              <input
                type="number"
                step="1"
                min="1"
                value={piezas}
                onChange={(e) => setPiezas(e.target.value)}
                placeholder="Piezas"
                className="mono-data w-full bg-kavana-surface border border-kavana-border rounded-sm px-3 py-3 min-h-[52px] text-lg focus:border-kavana-orange outline-none"
                required
              />
              <input
                type="number"
                step="0.5"
                min="0"
                value={horas}
                onChange={(e) => setHoras(e.target.value)}
                placeholder="Horas"
                className="mono-data w-full bg-kavana-surface border border-kavana-border rounded-sm px-3 py-3 min-h-[52px] text-lg focus:border-kavana-orange outline-none"
              />
            </div>
            <button
              type="submit"
              className="w-full min-h-[56px] bg-kavana-orange text-black font-bold uppercase tracking-widest rounded-sm hover:opacity-90 transition-opacity"
            >
              ➕ Registrar piezas
            </button>
          </form>

          <button
            onClick={() => {
              setVinculada(false)
              setScan(null)
              setCoilId('')
            }}
            className="w-full min-h-[56px] border border-kavana-border text-kavana-text-dim font-bold uppercase tracking-widest rounded-sm hover:border-kavana-orange hover:text-kavana-orange transition-colors"
          >
            🔄 Desvincular bobina
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

      {/* Sugerencias y alertas del almacén (idea Jorge: mostrar picos
          registrados para aconsejar su uso antes de abrir bobina nueva) */}
      {events.length > 0 && (
        <div className="bg-kavana-surface border border-kavana-border rounded-sm p-4 space-y-2">
          <p className="label-industrial text-xs text-kavana-text-dim">
            Alertas de almacén
          </p>
          {events.map((ev) => (
            <div
              key={ev.id}
              className="flex items-start justify-between gap-3 text-sm border-l-2 border-kavana-orange pl-3"
            >
              <span className="mono-data">{ev.tipo}</span>
              <span className="text-kavana-text-dim">
                {JSON.stringify(ev.data)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Data({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="label-industrial text-[10px] text-kavana-text-dim">
        {label}
      </span>
      <p className="mono-data text-sm">{value}</p>
    </div>
  )
}
