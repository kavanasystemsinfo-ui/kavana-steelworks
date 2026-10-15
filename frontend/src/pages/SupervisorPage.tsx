import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type {
  MaterialOut,
  OrderDetailOut,
  OrderItem,
  OrderLineIn,
  ProductOut,
  QualityModel,
  QualityRecordOut,
  WorkstationOut,
} from '../lib/api'

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
    api.listIncidencias?.().then((data) => {
      if (data && Array.isArray(data.incidencias)) setIncidencias(data.incidencias)
    }).catch(() => setIncError('No se pudieron cargar las incidencias'))
  }

  useEffect(() => {
    cargarIncidencias()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleResolver = async (id: string) => {
    setIncMsg('')
    setIncError('')
    try {
      await api.updateIncidencia(id, {
        estado: resForm.estado,
        resolucion_tipo: resForm.resolucion_tipo || null,
        resolucion_descripcion: resForm.resolucion_descripcion || null,
        tiempo_parada_min:
          resForm.tiempo_parada_min === ''
            ? null
            : Number(resForm.tiempo_parada_min),
        coste: resForm.coste === '' ? null : Number(resForm.coste),
      })
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
      api.getOee()
        .then(setOee)
        .catch((e) => setError(e instanceof Error ? e.message : 'Error OEE'))
      api.getKpis()
        .then(setKpis)
        .catch((e) => setError(e instanceof Error ? e.message : 'Error KPIs'))
    }
    cargar()
    const timer = setInterval(cargar, 10000)
    return () => clearInterval(timer)
  }, [])

  const cargarOrders = () => {
    api.listOrders()
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setOrders(data)
          setSelectedOrder((prev) => (prev ? prev : data[0].id))
        } else {
          setOrders([])
        }
      })
      .catch(() => setTraceError('No se pudieron cargar las órdenes'))
  }

  useEffect(() => {
    cargarOrders()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!selectedOrder) {
      setTrace(null)
      return
    }
    setTrace(null)
    setTraceError('')
    api.getTrace(selectedOrder)
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

      {/* Gestión de órdenes (Fase A1): crear, lanzar, completar, descartar */}
      <OrdersManager onCambio={cargarOrders} />

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

      {/* Bandeja de calidad (Fase A3): últimos autocontroles de la planta */}
      <QualityBoard />

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

const ESTADOS_ORDEN: Record<string, { label: string; badge: string }> = {
  draft: { label: 'Borrador', badge: 'border-kavana-border text-kavana-text-dim' },
  active: { label: 'Activa', badge: 'border-kavana-orange text-kavana-orange' },
  completed: { label: 'Completada', badge: 'border-kavana-ok text-kavana-ok' },
  cancelled: { label: 'Cancelada', badge: 'border-red-500/50 text-red-400' },
}

const ESTADOS_LINEA: Record<string, string> = {
  pending: 'pendiente',
  in_progress: 'en curso',
  stopped: 'parada',
  completed: 'completada',
}

interface LineDraft {
  workstation_id: string
  modelo_id: string
  product_id: string
  material_id: string
  total_quantity: string
  meters_per_piece: string
}

const LINEA_VACIA: LineDraft = {
  workstation_id: '',
  modelo_id: '',
  product_id: '',
  material_id: '',
  total_quantity: '',
  meters_per_piece: '',
}

const selectCls =
  'bg-kavana-dark border border-kavana-border rounded-sm px-2 py-1 text-sm min-h-[40px] w-full'
const inputSmCls =
  'bg-kavana-dark border border-kavana-border rounded-sm px-2 py-1 text-sm min-h-[40px] w-full'

/** Gestión de órdenes (Fase A1): CRUD y máquina de estados desde la UI. */
function OrdersManager({ onCambio }: { onCambio: () => void }) {
  const [orders, setOrders] = useState<OrderItem[]>([])
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [creando, setCreando] = useState(false)
  const [ocupoId, setOcupoId] = useState<string | null>(null)
  const [form, setForm] = useState({
    cliente: '',
    fecha_entrega: '',
    notas: '',
    estado_inicial: 'draft',
  })
  const [lines, setLines] = useState<LineDraft[]>([{ ...LINEA_VACIA }])
  const [workstations, setWorkstations] = useState<WorkstationOut[]>([])
  const [models, setModels] = useState<QualityModel[]>([])
  const [products, setProducts] = useState<ProductOut[]>([])
  const [materials, setMaterials] = useState<MaterialOut[]>([])
  const [detalle, setDetalle] = useState<OrderDetailOut | null>(null)
  const [editForm, setEditForm] = useState({ cliente: '', fecha_entrega: '', notas: '' })

  const cargar = () =>
    api
      .listOrders()
      .then(setOrders)
      .catch(() => setErr('No se pudieron cargar las órdenes'))

  useEffect(() => {
    cargar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const abrirForm = () => {
    const siguiente = !showForm
    setShowForm(siguiente)
    setMsg('')
    setErr('')
    if (siguiente) {
      if (workstations.length === 0)
        api.getWorkstations().then(setWorkstations).catch(() => undefined)
      if (models.length === 0)
        api.getQualityModels().then(setModels).catch(() => undefined)
      if (products.length === 0)
        api.listProducts().then(setProducts).catch(() => undefined)
      if (materials.length === 0)
        api.listMaterials().then(setMaterials).catch(() => undefined)
    }
  }

  const trasCambio = async () => {
    await cargar()
    onCambio()
  }

  const handleCrear = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr('')
    setMsg('')
    const payload: OrderLineIn[] = []
    for (const [i, ln] of lines.entries()) {
      if (!ln.workstation_id) {
        setErr(`La línea ${i + 1} necesita puesto de trabajo`)
        return
      }
      if (!ln.total_quantity || Number(ln.total_quantity) <= 0) {
        setErr(`La línea ${i + 1} necesita una cantidad mayor que 0`)
        return
      }
      payload.push({
        workstation_id: ln.workstation_id,
        total_quantity: Number(ln.total_quantity),
        linea_numero: i + 1,
        ...(ln.product_id ? { product_id: ln.product_id } : {}),
        ...(ln.modelo_id ? { modelo_id: ln.modelo_id } : {}),
        ...(ln.material_id ? { material_id: ln.material_id } : {}),
        ...(ln.meters_per_piece && Number(ln.meters_per_piece) > 0
          ? { meters_per_piece: Number(ln.meters_per_piece) }
          : {}),
      })
    }
    setCreando(true)
    try {
      const creada = await api.createOrder({
        cliente: form.cliente || null,
        fecha_entrega: form.fecha_entrega || null,
        notas: form.notas || null,
        estado_inicial: form.estado_inicial as 'draft' | 'active',
        lines: payload,
      })
      setMsg(`Orden ${creada.numero} creada`)
      setForm({ cliente: '', fecha_entrega: '', notas: '', estado_inicial: 'draft' })
      setLines([{ ...LINEA_VACIA }])
      setShowForm(false)
      await trasCambio()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Error al crear la orden')
    } finally {
      setCreando(false)
    }
  }

  const transitar = async (o: OrderItem, to: 'active' | 'completed' | 'cancelled') => {
    setErr('')
    setMsg('')
    setOcupoId(o.id)
    try {
      await api.transitionOrder(o.id, to)
      setMsg(`${o.numero}: ${ESTADOS_ORDEN[to]?.label ?? to}`)
      if (detalle?.id === o.id) setDetalle(null)
      await trasCambio()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Error de transición')
    } finally {
      setOcupoId(null)
    }
  }

  const eliminar = async (o: OrderItem) => {
    if (!window.confirm(`¿Eliminar el borrador ${o.numero}?`)) return
    setErr('')
    setMsg('')
    setOcupoId(o.id)
    try {
      await api.deleteOrder(o.id)
      setMsg(`Orden ${o.numero} eliminada`)
      if (detalle?.id === o.id) setDetalle(null)
      await trasCambio()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Error al eliminar')
    } finally {
      setOcupoId(null)
    }
  }

  const abrirDetalle = async (o: OrderItem) => {
    if (detalle?.id === o.id) {
      setDetalle(null)
      return
    }
    setErr('')
    try {
      const d = await api.getOrder(o.id)
      setDetalle(d)
      setEditForm({
        cliente: d.cliente ?? '',
        fecha_entrega: (d.fecha_entrega ?? '').slice(0, 10),
        notas: d.notas ?? '',
      })
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'No se pudo cargar la orden')
    }
  }

  const guardarCabecera = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!detalle) return
    setErr('')
    setMsg('')
    try {
      await api.updateOrder(detalle.id, {
        cliente: editForm.cliente || null,
        fecha_entrega: editForm.fecha_entrega || null,
        notas: editForm.notas || null,
      })
      setMsg(`Orden ${detalle.numero} actualizada`)
      await trasCambio()
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : 'Error al guardar')
    }
  }

  const setLinea = (idx: number, campo: keyof LineDraft, valor: string) => {
    setLines((prev) => prev.map((ln, i) => (i === idx ? { ...ln, [campo]: valor } : ln)))
  }

  return (
    <div className="bg-kavana-surface border border-kavana-border rounded-sm p-4 space-y-3">
      <div className="flex items-center justify-between">
        <p className="label-industrial text-xs text-kavana-text-dim">Gestión de órdenes</p>
        <button
          type="button"
          onClick={abrirForm}
          className="min-h-[40px] px-4 border border-kavana-orange text-kavana-orange text-xs font-bold uppercase tracking-widest rounded-sm hover:bg-kavana-orange hover:text-black transition-colors"
        >
          {showForm ? 'Cerrar' : '+ Nueva orden'}
        </button>
      </div>

      {msg && (
        <p className="text-kavana-ok text-sm border border-kavana-ok/40 rounded-sm p-2">{msg}</p>
      )}
      {err && <p className="text-kavana-danger text-sm">{err}</p>}

      {showForm && (
        <form onSubmit={handleCrear} className="border border-kavana-border rounded-sm p-3 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <label className="block">
              <span className="label-industrial text-[10px] text-kavana-text-dim">Cliente</span>
              <input
                className={inputSmCls}
                value={form.cliente}
                onChange={(e) => setForm({ ...form, cliente: e.target.value })}
              />
            </label>
            <label className="block">
              <span className="label-industrial text-[10px] text-kavana-text-dim">
                Fecha de entrega
              </span>
              <input
                type="date"
                className={inputSmCls}
                value={form.fecha_entrega}
                onChange={(e) => setForm({ ...form, fecha_entrega: e.target.value })}
              />
            </label>
            <label className="block">
              <span className="label-industrial text-[10px] text-kavana-text-dim">
                Estado inicial
              </span>
              <select
                className={selectCls}
                value={form.estado_inicial}
                onChange={(e) => setForm({ ...form, estado_inicial: e.target.value })}
              >
                <option value="draft">Borrador</option>
                <option value="active">Activa</option>
              </select>
            </label>
            <label className="block">
              <span className="label-industrial text-[10px] text-kavana-text-dim">Notas</span>
              <input
                className={inputSmCls}
                value={form.notas}
                onChange={(e) => setForm({ ...form, notas: e.target.value })}
              />
            </label>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="label-industrial text-[10px] text-kavana-text-dim">Líneas</span>
              <button
                type="button"
                onClick={() => setLines((prev) => [...prev, { ...LINEA_VACIA }])}
                className="text-kavana-orange text-xs uppercase tracking-widest hover:underline"
              >
                + Añadir línea
              </button>
            </div>
            {lines.map((ln, idx) => (
              <div
                key={idx}
                className="grid grid-cols-2 md:grid-cols-6 gap-2 border-t border-kavana-border pt-2"
              >
                <label className="block">
                  <span className="label-industrial text-[10px] text-kavana-text-dim">Puesto</span>
                  <select
                    required
                    className={selectCls}
                    value={ln.workstation_id}
                    onChange={(e) => setLinea(idx, 'workstation_id', e.target.value)}
                  >
                    <option value="">—</option>
                    {workstations.map((w) => (
                      <option key={w.id} value={w.code}>
                        {w.code} · {w.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="label-industrial text-[10px] text-kavana-text-dim">Pieza</span>
                  <select
                    className={selectCls}
                    value={ln.modelo_id}
                    onChange={(e) => setLinea(idx, 'modelo_id', e.target.value)}
                  >
                    <option value="">—</option>
                    {models.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.code}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="label-industrial text-[10px] text-kavana-text-dim">
                    Producto
                  </span>
                  <select
                    className={selectCls}
                    value={ln.product_id}
                    onChange={(e) => setLinea(idx, 'product_id', e.target.value)}
                  >
                    <option value="">—</option>
                    {products.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.code}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="label-industrial text-[10px] text-kavana-text-dim">
                    Material
                  </span>
                  <select
                    className={selectCls}
                    value={ln.material_id}
                    onChange={(e) => setLinea(idx, 'material_id', e.target.value)}
                  >
                    <option value="">—</option>
                    {materials.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.code}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="label-industrial text-[10px] text-kavana-text-dim">Cant.</span>
                  <input
                    type="number"
                    min="1"
                    step="1"
                    required
                    className={inputSmCls}
                    value={ln.total_quantity}
                    onChange={(e) => setLinea(idx, 'total_quantity', e.target.value)}
                  />
                </label>
                <label className="block">
                  <span className="label-industrial text-[10px] text-kavana-text-dim">m/ud</span>
                  <div className="flex gap-1">
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      className={inputSmCls}
                      value={ln.meters_per_piece}
                      onChange={(e) => setLinea(idx, 'meters_per_piece', e.target.value)}
                    />
                    {lines.length > 1 && (
                      <button
                        type="button"
                        aria-label="Quitar línea"
                        onClick={() => setLines((prev) => prev.filter((_, i) => i !== idx))}
                        className="px-2 border border-red-500/50 text-red-400 rounded-sm text-sm hover:bg-red-500/10"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                </label>
              </div>
            ))}
          </div>

          <button
            type="submit"
            disabled={creando}
            className="w-full min-h-[44px] bg-kavana-orange text-black font-bold uppercase tracking-widest rounded-sm hover:opacity-90 disabled:opacity-40"
          >
            {creando ? 'Creando…' : 'Crear orden'}
          </button>
        </form>
      )}

      {orders.length === 0 && !err && (
        <p className="text-kavana-text-dim text-sm">Sin órdenes. Crea la primera desde aquí.</p>
      )}

      <ul className="space-y-2">
        {orders.map((o) => {
          const est = ESTADOS_ORDEN[o.estado] ?? { label: o.estado, badge: '' }
          const ocupada = ocupoId === o.id
          return (
            <li key={o.id} className="border-t border-kavana-border pt-2 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="mono-data font-semibold">{o.numero}</p>
                  <p className="text-kavana-text-dim text-xs">
                    {o.cliente ?? 'Sin cliente'}
                    {o.fecha_entrega
                      ? ` · entrega ${new Date(o.fecha_entrega).toLocaleDateString('es-ES')}`
                      : ''}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`mono-data text-[10px] uppercase px-2 py-0.5 border rounded-sm ${est.badge}`}
                  >
                    {est.label}
                  </span>
                  <button
                    type="button"
                    onClick={() => abrirDetalle(o)}
                    className="text-kavana-text-dim text-xs uppercase tracking-widest hover:underline"
                  >
                    {detalle?.id === o.id ? 'Cerrar' : 'Detalle'}
                  </button>
                  {o.estado === 'draft' && (
                    <>
                      <button
                        type="button"
                        disabled={ocupada}
                        onClick={() => transitar(o, 'active')}
                        className="text-kavana-orange text-xs uppercase tracking-widest hover:underline disabled:opacity-40"
                      >
                        Lanzar
                      </button>
                      <button
                        type="button"
                        disabled={ocupada}
                        onClick={() => eliminar(o)}
                        className="text-red-400 text-xs uppercase tracking-widest hover:underline disabled:opacity-40"
                      >
                        Eliminar
                      </button>
                    </>
                  )}
                  {o.estado === 'active' && (
                    <>
                      <button
                        type="button"
                        disabled={ocupada}
                        onClick={() => transitar(o, 'completed')}
                        className="text-kavana-ok text-xs uppercase tracking-widest hover:underline disabled:opacity-40"
                      >
                        Completar
                      </button>
                      <button
                        type="button"
                        disabled={ocupada}
                        onClick={() => transitar(o, 'cancelled')}
                        className="text-red-400 text-xs uppercase tracking-widest hover:underline disabled:opacity-40"
                      >
                        Cancelar
                      </button>
                    </>
                  )}
                </div>
              </div>

              {detalle?.id === o.id && (
                <div className="mt-2 border border-kavana-border rounded-sm p-3 space-y-3">
                  <form onSubmit={guardarCabecera} className="grid grid-cols-3 gap-2">
                    <label className="block">
                      <span className="label-industrial text-[10px] text-kavana-text-dim">
                        Cliente
                      </span>
                      <input
                        className={inputSmCls}
                        value={editForm.cliente}
                        onChange={(e) => setEditForm({ ...editForm, cliente: e.target.value })}
                      />
                    </label>
                    <label className="block">
                      <span className="label-industrial text-[10px] text-kavana-text-dim">
                        Entrega
                      </span>
                      <input
                        type="date"
                        className={inputSmCls}
                        value={editForm.fecha_entrega}
                        onChange={(e) =>
                          setEditForm({ ...editForm, fecha_entrega: e.target.value })
                        }
                      />
                    </label>
                    <label className="block">
                      <span className="label-industrial text-[10px] text-kavana-text-dim">
                        Notas
                      </span>
                      <input
                        className={inputSmCls}
                        value={editForm.notas}
                        onChange={(e) => setEditForm({ ...editForm, notas: e.target.value })}
                      />
                    </label>
                    <button
                      type="submit"
                      className="col-span-3 min-h-[40px] border border-kavana-orange text-kavana-orange text-xs font-bold uppercase tracking-widest rounded-sm hover:bg-kavana-orange hover:text-black transition-colors"
                    >
                      Guardar cabecera
                    </button>
                  </form>

                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-kavana-text-dim text-left">
                        <th className="py-1">Línea</th>
                        <th>Puesto</th>
                        <th>Estado</th>
                        <th className="text-right">Producido / total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detalle.lines.map((ln) => (
                        <tr key={ln.id} className="border-t border-kavana-border">
                          <td className="py-1 mono-data">#{ln.linea_numero}</td>
                          <td className="mono-data">{ln.workstation_id}</td>
                          <td>{ESTADOS_LINEA[ln.estado] ?? ln.estado}</td>
                          <td className="text-right mono-data">
                            {ln.produced_quantity} / {ln.total_quantity} uds
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

const ESTADOS_CALIDAD: Record<string, { label: string; badge: string }> = {
  approved: { label: 'Aprobado', badge: 'border-kavana-ok text-kavana-ok' },
  rejected: { label: 'Rechazado', badge: 'border-red-500/50 text-red-400' },
  rework: { label: 'Retrabajo', badge: 'border-kavana-orange text-kavana-orange' },
}

/** Bandeja de calidad (Fase A3): últimos autocontroles de la planta. */
function QualityBoard() {
  const [records, setRecords] = useState<QualityRecordOut[]>([])
  const [err, setErr] = useState('')
  const [abierto, setAbierto] = useState<string | null>(null)

  useEffect(() => {
    api
      .getQualityRecords(10)
      .then((r) => setRecords(r.records))
      .catch(() => setErr('No se pudieron cargar los registros de calidad'))
  }, [])

  return (
    <div className="bg-kavana-surface border border-kavana-border rounded-sm p-4 space-y-3">
      <div className="flex items-center justify-between">
        <p className="label-industrial text-xs text-kavana-text-dim">Autocontroles de calidad</p>
        <span className="text-[10px] text-kavana-text-dim">{records.length} últimos</span>
      </div>

      {err && <p className="text-kavana-danger text-sm">{err}</p>}
      {!err && records.length === 0 && (
        <p className="text-kavana-text-dim text-sm">Sin autocontroles registrados.</p>
      )}

      <ul className="space-y-2">
        {records.map((r) => {
          const est = ESTADOS_CALIDAD[r.overall_status] ?? {
            label: r.overall_status,
            badge: '',
          }
          const pasan = r.measurements.filter((m) => m.is_passed).length
          const total = r.measurements.length
          return (
            <li key={r.id} className="border-t border-kavana-border pt-2 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="mono-data">{r.workstation_id ?? '—'}</p>
                  <p className="text-kavana-text-dim text-xs">
                    {r.operator?.name ?? '—'} ·{' '}
                    {new Date(r.created_at).toLocaleString('es-ES')}
                    {total > 0 ? ` · ${pasan}/${total} controles conformes` : ''}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`mono-data text-[10px] uppercase px-2 py-0.5 border rounded-sm ${est.badge}`}
                  >
                    {est.label}
                  </span>
                  {total > 0 && (
                    <button
                      type="button"
                      onClick={() => setAbierto(abierto === r.id ? null : r.id)}
                      className="text-kavana-text-dim text-xs uppercase tracking-widest hover:underline"
                    >
                      {abierto === r.id ? 'Ocultar' : 'Medidas'}
                    </button>
                  )}
                </div>
              </div>

              {abierto === r.id && (
                <ul className="mt-2 space-y-1 text-xs">
                  {r.measurements.map((m, i) => (
                    <li key={i} className="flex items-center justify-between gap-2">
                      <span className={m.is_passed ? 'text-kavana-ok' : 'text-kavana-danger'}>
                        {m.is_passed ? '✓' : '✗'} {m.check_name}
                      </span>
                      <span className="mono-data text-kavana-text-dim">
                        {String(m.value_entered)}
                        {m.nominal != null
                          ? ` (nominal ${m.nominal}${m.tol_plus != null ? ` +${m.tol_plus}` : ''}${
                              m.tol_minus != null ? ` -${m.tol_minus}` : ''
                            })`
                          : ''}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
