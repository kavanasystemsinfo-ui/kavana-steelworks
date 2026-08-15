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

interface IncidenciaItem {
  id: string
  linea_id: string | null
  puesto: string
  descripcion: string
  tipo: string
  estado: string
  foto_data_url: string | null
  resolucion_tipo: string | null
  resolucion_descripcion: string | null
  tiempo_parada_min: number | null
  coste: number | null
  created_at: string
  operario: { id: string; name: string } | null
  responsable: { id: string; name: string } | null
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

  // Incidencias de planta (spec 04 §3.3): listado y resolución
  const [incidencias, setIncidencias] = useState<IncidenciaItem[]>([])
  const [incError, setIncError] = useState('')
  const [incMsg, setIncMsg] = useState('')
  const [resolviendoId, setResolviendoId] = useState<string | null>(null)
  const [resForm, setResForm] = useState({
    estado: 'resuelta',
    resolucion_tipo: '',
    resolucion_descripcion: '',
    tiempo_parada_min: '',
    coste: '',
  })

  const cargarIncidencias = () => {
    fetch('/api/v1/incidencias')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Incidencias ${r.status}`))))
      .then((data) => {
        if (data && Array.isArray(data.incidencias)) setIncidencias(data.incidencias)
      })
      .catch(() => setIncError('No se pudieron cargar las incidencias'))
  }

  useEffect(() => {
    cargarIncidencias()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleResolver = async (id: string) => {
    setIncMsg('')
    setIncError('')
    try {
      const res = await fetch(`/api/v1/incidencias/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          estado: resForm.estado,
          resolucion_tipo: resForm.resolucion_tipo || null,
          resolucion_descripcion: resForm.resolucion_descripcion || null,
          tiempo_parada_min:
            resForm.tiempo_parada_min === ''
              ? null
              : Number(resForm.tiempo_parada_min),
          coste: resForm.coste === '' ? null : Number(resForm.coste),
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? 'Error al resolver incidencia')
      }
      await res.json()
      setIncMsg('Incidencia actualizada')
      setResolviendoId(null)
      setResForm({
        estado: 'resuelta',
        resolucion_tipo: '',
        resolucion_descripcion: '',
        tiempo_parada_min: '',
        coste: '',
      })
      cargarIncidencias()
    } catch (e) {
      setIncError(e instanceof Error ? e.message : 'Error de conexión')
    }
  }

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

      {/* Incidencias de planta (spec 04 §3.3) */}
      <div className="bg-kavana-surface border border-kavana-border rounded-sm p-4 space-y-3">
        <div className="flex items-center justify-between">
          <p className="label-industrial text-xs text-kavana-text-dim">
            Incidencias de planta
          </p>
          <span className="text-[10px] text-kavana-text-dim">
            {incidencias.length} reportadas
          </span>
        </div>

        {incMsg && (
          <p className="text-kavana-ok text-sm border border-kavana-ok/40 rounded-sm p-2">
            {incMsg}
          </p>
        )}
        {incError && <p className="text-kavana-danger text-sm">{incError}</p>}

        {incidencias.length === 0 && !incError && (
          <p className="text-kavana-text-dim text-sm">
            Sin incidencias reportadas.
          </p>
        )}

        {incidencias.length > 0 && (
          <ul className="space-y-3">
            {incidencias.map((inc) => (
              <li key={inc.id} className="border-t border-kavana-border pt-2 text-sm">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold">{inc.descripcion}</p>
                    <p className="text-kavana-text-dim text-xs">
                      {inc.puesto || inc.linea_id || '—'} · {inc.tipo} ·{' '}
                      {inc.operario?.name ?? '—'} ·{' '}
                      {new Date(inc.created_at).toLocaleString('es-ES')}
                    </p>
                    {inc.foto_data_url && (
                      <img
                        src={inc.foto_data_url}
                        alt={`Evidencia de ${inc.descripcion}`}
                        className="mt-2 max-h-32 rounded-sm border border-kavana-border object-cover"
                      />
                    )}
                    {inc.resolucion_descripcion && (
                      <p className="text-kavana-text-dim text-xs">
                        Resolución: {inc.resolucion_descripcion}
                      </p>
                    )}
                    {inc.tiempo_parada_min != null && (
                      <p className="text-kavana-text-dim text-xs">
                        {inc.tiempo_parada_min} min parada · {inc.coste ?? 0} €
                      </p>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span className="mono-data text-xs uppercase">{inc.estado}</span>
                    {inc.estado !== 'cerrada' && (
                      <button
                        type="button"
                        onClick={() => setResolviendoId(inc.id)}
                        className="text-kavana-orange text-xs uppercase tracking-widest hover:underline"
                      >
                        Resolver
                      </button>
                    )}
                  </div>
                </div>

                {resolviendoId === inc.id && (
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <label className="block">
                      <span className="label-industrial text-[10px] text-kavana-text-dim">
                        Estado final
                      </span>
                      <select
                        value={resForm.estado}
                        onChange={(e) =>
                          setResForm({ ...resForm, estado: e.target.value })
                        }
                        className="w-full bg-kavana-dark border border-kavana-border rounded-sm px-2 py-1 text-sm"
                      >
                        <option value="resuelta">Resuelta</option>
                        <option value="cerrada">Cerrada</option>
                      </select>
                    </label>
                    <label className="block">
                      <span className="label-industrial text-[10px] text-kavana-text-dim">
                        Tipo de resolución
                      </span>
                      <select
                        value={resForm.resolucion_tipo}
                        onChange={(e) =>
                          setResForm({ ...resForm, resolucion_tipo: e.target.value })
                        }
                        className="w-full bg-kavana-dark border border-kavana-border rounded-sm px-2 py-1 text-sm"
                      >
                        <option value="">—</option>
                        <option value="reparacion">Reparación</option>
                        <option value="cambio_pieza">Cambio de pieza</option>
                        <option value="ajuste">Ajuste</option>
                      </select>
                    </label>
                    <input
                      type="number"
                      step="0.5"
                      min="0"
                      placeholder="Minutos de parada"
                      value={resForm.tiempo_parada_min}
                      onChange={(e) =>
                        setResForm({ ...resForm, tiempo_parada_min: e.target.value })
                      }
                      className="w-full bg-kavana-dark border border-kavana-border rounded-sm px-2 py-1 text-sm"
                    />
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      placeholder="Coste (€)"
                      value={resForm.coste}
                      onChange={(e) =>
                        setResForm({ ...resForm, coste: e.target.value })
                      }
                      className="w-full bg-kavana-dark border border-kavana-border rounded-sm px-2 py-1 text-sm"
                    />
                    <button
                      type="button"
                      onClick={() => handleResolver(inc.id)}
                      className="col-span-2 min-h-[44px] border border-kavana-orange text-kavana-orange font-bold uppercase tracking-widest rounded-sm hover:bg-kavana-orange hover:text-black transition-colors"
                    >
                      Confirmar resolución
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
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
