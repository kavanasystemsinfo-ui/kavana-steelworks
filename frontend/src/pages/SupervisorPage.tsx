import { useEffect, useState } from 'react'

interface OeeData {
  availability: number
  performance: number
  quality: number
  oee: number
  raw: {
    total_pieces: number
    total_objetivo: number
    total_tiempo_min: number
    scrap_kg: number
    material_kg: number
  }
}

interface KpisData {
  orders_total: number
  orders_active: number
  orders_completed: number
  estimated_cost: number
  real_cost: number
  cost_variance: number
  cost_efficiency: number
  material_variance: number
  material_efficiency: number
  scrap_rate: number
}

interface OrderItem {
  id: string
  numero: string
  estado: string
  cliente: string | null
  fecha_entrega: string | null
}

interface TraceEvent {
  id: string
  action: string
  quantity: string
  timestamp: string
  metadata: Record<string, unknown> | null
  shift: string | null
  operator: { id: string; name: string } | null
}

/** Etiquetas humanas de las acciones del ProductionLog (spec 04 §2.1). */
const ACCIONES_TRACE: Record<string, string> = {
  start: 'Inicio de sesión',
  pause: 'Pausa',
  resume: 'Reanudar',
  finish: 'Fin de bobina',
  produce: 'Producción',
  scrap: 'Merma',
  setup_start: 'Setup: inicio',
  setup_finish: 'Setup: fin',
  close_shift: 'Cierre de turno',
  stopped: 'Parada',
  quality_check: 'Control de calidad',
}

/** Panel de Supervisor: "planta en un vistazo" (filosofía Jorge).
 *  OEE y KPIs reales del backend (spec 03), polling cada 10 s.
 *  Trazabilidad ISO 9001 (spec 04): selector de orden + serie temporal
 *  de eventos inmutables, carga bajo demanda (no polling).
 */
export function SupervisorPage() {
  const [oee, setOee] = useState<OeeData | null>(null)
  const [kpis, setKpis] = useState<KpisData | null>(null)
  const [error, setError] = useState('')

  const [orders, setOrders] = useState<OrderItem[]>([])
  const [selectedOrder, setSelectedOrder] = useState('')
  const [trace, setTrace] = useState<TraceEvent[] | null>(null)
  const [traceError, setTraceError] = useState('')

  useEffect(() => {
    const cargar = () => {
      fetch('/api/v1/supervisor/oee')
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`OEE ${r.status}`))))
        .then(setOee)
        .catch((e) => setError(e instanceof Error ? e.message : 'Error OEE'))
      fetch('/api/v1/supervisor/kpis')
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`KPIs ${r.status}`))))
        .then(setKpis)
        .catch((e) => setError(e instanceof Error ? e.message : 'Error KPIs'))
    }
    cargar()
    const timer = setInterval(cargar, 10000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    fetch('/api/v1/orders')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Órdenes ${r.status}`))))
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setOrders(data)
          setSelectedOrder(data[0].id)
        } else {
          setOrders([])
        }
      })
      .catch(() => setTraceError('No se pudieron cargar las órdenes'))
  }, [])

  useEffect(() => {
    if (!selectedOrder) {
      setTrace(null)
      return
    }
    setTrace(null)
    setTraceError('')
    fetch(`/api/v1/trace/orders/${selectedOrder}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Traza ${r.status}`))))
      .then(setTrace)
      .catch(() => setTraceError('No se pudo cargar la trazabilidad'))
  }, [selectedOrder])

  const fmtEur = (n: number | undefined) =>
    n === undefined ? '--' : `${n.toLocaleString('es-ES')} €`
  const fmtPct = (n: number | undefined) =>
    n === undefined ? '--' : `${n.toLocaleString('es-ES')} %`

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      <div className="step-guide">
        <p className="label-industrial text-xs text-kavana-text-dim">
          Planta en un vistazo
        </p>
        <p className="text-lg font-bold">Turno actual</p>
      </div>

      {error && (
        <p className="text-kavana-danger text-sm border border-kavana-danger/40 rounded-sm p-2">
          {error}
        </p>
      )}

      {/* OEE principal */}
      <div className="bg-kavana-surface border border-kavana-border rounded-sm p-6 flex items-center justify-between">
        <div>
          <p className="label-industrial text-xs text-kavana-text-dim">OEE global</p>
          <p className="mono-data text-6xl mt-1 text-kavana-orange">
            {oee ? oee.oee.toLocaleString('es-ES') : '--'}
            <span className="text-2xl text-kavana-text-dim">%</span>
          </p>
        </div>
        <div className="grid grid-cols-3 gap-6 text-right">
          <div>
            <p className="label-industrial text-[10px] text-kavana-text-dim">
              Disponibilidad
            </p>
            <p className="mono-data text-2xl">
              {oee ? oee.availability.toLocaleString('es-ES') : '--'}
              <span className="text-sm text-kavana-text-dim">%</span>
            </p>
          </div>
          <div>
            <p className="label-industrial text-[10px] text-kavana-text-dim">
              Rendimiento
            </p>
            <p className="mono-data text-2xl">
              {oee ? oee.performance.toLocaleString('es-ES') : '--'}
              <span className="text-sm text-kavana-text-dim">%</span>
            </p>
          </div>
          <div>
            <p className="label-industrial text-[10px] text-kavana-text-dim">
              Calidad
            </p>
            <p className="mono-data text-2xl">
              {oee ? oee.quality.toLocaleString('es-ES') : '--'}
              <span className="text-sm text-kavana-text-dim">%</span>
            </p>
          </div>
        </div>
      </div>

      {/* KPIs del turno */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label="Producción turno" value={oee ? oee.raw.total_pieces.toLocaleString('es-ES') : '--'} unit="uds" />
        <Kpi label="Merma" value={oee ? oee.raw.scrap_kg.toLocaleString('es-ES') : '--'} unit="kg" />
        <Kpi label="Coste real vs est." value={fmtEur(kpis?.cost_variance)} unit="€" />
        <Kpi label="Eficiencia coste" value={fmtPct(kpis?.cost_efficiency)} unit="" />
      </div>

      {/* Detalle de órdenes */}
      <div className="bg-kavana-surface border border-kavana-border rounded-sm p-4 space-y-2">
        <p className="label-industrial text-xs text-kavana-text-dim">Órdenes</p>
        {kpis ? (
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div>
              <p className="text-kavana-text-dim">Activas</p>
              <p className="mono-data text-xl">{kpis.orders_active}</p>
            </div>
            <div>
              <p className="text-kavana-text-dim">Completadas</p>
              <p className="mono-data text-xl">{kpis.orders_completed}</p>
            </div>
            <div>
              <p className="text-kavana-text-dim">Tasa de merma</p>
              <p className="mono-data text-xl">{fmtPct(kpis.scrap_rate)}</p>
            </div>
          </div>
        ) : (
          <p className="text-kavana-text-dim text-sm">
            Cargando datos del turno...
          </p>
        )}
      </div>

      {/* Trazabilidad ISO 9001 (spec 04) */}
      <div className="bg-kavana-surface border border-kavana-border rounded-sm p-4 space-y-3">
        <div className="flex items-center justify-between">
          <p className="label-industrial text-xs text-kavana-text-dim">
            Trazabilidad ISO 9001
          </p>
          <span className="text-[10px] text-kavana-text-dim">eventos inmutables</span>
        </div>

        <div className="flex items-center gap-2">
          <label htmlFor="trace-order" className="text-sm text-kavana-text-dim">
            Orden
          </label>
          <select
            id="trace-order"
            className="bg-kavana-surface border border-kavana-border rounded-sm px-2 py-1 text-sm"
            value={selectedOrder}
            onChange={(e) => setSelectedOrder(e.target.value)}
          >
            {orders.length === 0 && <option value="">Sin órdenes</option>}
            {orders.map((o) => (
              <option key={o.id} value={o.id}>
                {o.numero} · {o.estado}
              </option>
            ))}
          </select>
        </div>

        {traceError && (
          <p className="text-kavana-danger text-sm">{traceError}</p>
        )}

        {orders.length === 0 && !traceError && (
          <p className="text-kavana-text-dim text-sm">Sin órdenes disponibles.</p>
        )}

        {selectedOrder && !traceError && trace !== null && trace.length === 0 && (
          <p className="text-kavana-text-dim text-sm">
            Sin eventos de trazabilidad para esta orden.
          </p>
        )}

        {selectedOrder && trace !== null && trace.length > 0 && (
          <ol className="space-y-2">
            {trace.map((ev) => (
              <li
                key={ev.id}
                className="flex items-start justify-between gap-3 border-t border-kavana-border pt-2 text-sm"
              >
                <div>
                  <p className="font-semibold">
                    {ACCIONES_TRACE[ev.action] ?? ev.action}
                  </p>
                  <p className="text-kavana-text-dim text-xs">
                    {new Date(ev.timestamp).toLocaleString('es-ES')} ·{' '}
                    {ev.operator?.name ?? '—'}
                    {ev.shift ? ` · turno ${ev.shift}` : ''}
                  </p>
                  <DetalleEvento evento={ev} />
                </div>
                {Number(ev.quantity) > 0 && (
                  <p className="mono-data whitespace-nowrap">
                    {ev.quantity} {ev.action === 'scrap' ? 'kg' : 'uds'}
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  )
}

function Kpi({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="bg-kavana-surface border border-kavana-border rounded-sm p-4">
      <p className="label-industrial text-xs text-kavana-text-dim">{label}</p>
      <p className="mono-data text-3xl mt-1">
        {value}
        <span className="text-base text-kavana-text-dim">{unit}</span>
      </p>
    </div>
  )
}

/** Detalle del metadata del evento: solo las claves útiles para el supervisor. */
function DetalleEvento({ evento }: { evento: TraceEvent }) {
  const m = evento.metadata ?? {}
  const partes: string[] = []
  if (m.consumedAmount != null) partes.push(`${m.consumedAmount} kg consumidos`)
  if (m.activeCoilCode != null) partes.push(`bobina ${m.activeCoilCode}`)
  if (m.reason != null) partes.push(`motivo: ${m.reason}`)
  if (m.efficiency != null) partes.push(`eficiencia ${m.efficiency} %`)

  if (partes.length === 0) return null
  return <p className="text-kavana-text-dim text-xs">{partes.join(' · ')}</p>
}
