import { useEffect, useRef, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { api, getTenantId, type EventData } from '../lib/api'
import { usePlantEvents, type ConexionEstado } from '../hooks/usePlantEvents'

interface UploadSession {
  session_id: string
  status: string
  expires_at: string
  has_photo: boolean
  incidencia_id: string | null
  photo_data_url?: string | null
}

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

interface PlanCheck {
  id: string
  name: string
  tipo: string
  tool_id: string | null
  nominal_value: number | null
  tolerance_plus: number | null
  tolerance_minus: number | null
  is_critical: boolean
}

interface QualityModel {
  id: string
  code: string
  name: string
  material_code: string | null
  quality_plan: PlanCheck[]
}

interface OrdenInfo {
  id: string
  workstation_id: string | null
}

/** Traducción del estado evaluado del autocontrol (spec 04). */
function estadoCalidad(estado: string): string {
  if (estado === 'approved') return 'Aprobado'
  if (estado === 'rejected') return 'Rechazado (no bloquea la producción)'
  if (estado === 'rework') return 'Requiere retrabajo (no bloquea la producción)'
  return estado
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

  // Alertas de planta por WebSocket (ADR-014): el polling de 5 s desaparece.
  // El hook reconecta solo con backoff; aquí orquestamos conexión y el
  // fallback REST honesto para el caso de Vercel sin reenvío de upgrades.
  const { conectar, desconectar, eventos, estado } = usePlantEvents()
  const [restEvents, setRestEvents] = useState<EventData[]>([])
  const [usandoWs, setUsandoWs] = useState(false)
  const tenantRef = useRef<string | null>(null)

  useEffect(() => {
    const t = getTenantId()
    if (!t) return
    tenantRef.current = t
    conectar(t)
    return () => {
      tenantRef.current = null
      desconectar()
    }
  }, [conectar, desconectar])

  useEffect(() => {
    if (estado === 'conectado') setUsandoWs(true)
  }, [estado])

  // Fallback REST: solo si el WS llegó a fallar y nunca conectó. Una vez
  // conectado, el WS manda; si luego cae, se muestra lo último recibido
  // mientras el hook reintenta en segundo plano.
  useEffect(() => {
    if (estado !== 'reconectando' || usandoWs || !tenantRef.current) return
    const t = tenantRef.current
    const cargar = () => {
      api
        .getEvents(t)
        .then((r) => setRestEvents(r.events.slice(-3)))
        .catch(() => {})
    }
    cargar()
    const timer = setInterval(cargar, 5000)
    return () => clearInterval(timer)
  }, [estado, usandoWs])

  const eventosVisibles = usandoWs ? eventos : restEvents

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

  // Autocontrol de calidad (spec 04): plantilla + orden de la demo
  const [models, setModels] = useState<QualityModel[]>([])
  const [ordenActual, setOrdenActual] = useState<OrdenInfo | null>(null)
  const [mediciones, setMediciones] = useState<
    Record<string, number | boolean | string>
  >({})
  const [qcMsg, setQcMsg] = useState('')
  const [qcError, setQcError] = useState('')

  useEffect(() => {
    fetch('/api/v1/quality/models')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error())))
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) setModels(data)
      })
      .catch(() => {})
    fetch('/api/v1/orders')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error())))
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setOrdenActual({
            id: data[0].id,
            workstation_id: data[0].workstation_id ?? null,
          })
        }
      })
      .catch(() => {})
  }, [])

  const modelo = models[0] ?? null
  const puedeAutocontrol = Boolean(modelo && ordenActual?.workstation_id)

  const setMedicion = (name: string, valor: number | boolean | string) => {
    setMediciones((prev) => ({ ...prev, [name]: valor }))
  }

  const handleQualityCheck = async (e: React.FormEvent) => {
    e.preventDefault()
    setQcMsg('')
    setQcError('')
    if (!modelo || !ordenActual || !scan) return
    const lista = Object.entries(mediciones)
      .filter(([, v]) => v !== '' && v !== undefined)
      .map(([name, value]) => ({ check_name: name, value_entered: value }))
    if (lista.length === 0) {
      setQcError('Mide al menos un control antes de registrar.')
      return
    }
    try {
      const res = await fetch('/api/v1/quality/checks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          order_id: ordenActual.id,
          workstation_id: ordenActual.workstation_id,
          manufacturing_model_id: modelo.id,
          stock_item_id: scan.id,
          measurements: lista,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? 'Error al registrar autocontrol')
      }
      const data = await res.json()
      setQcMsg(estadoCalidad(data.record?.overall_status ?? ''))
      setMediciones({})
    } catch (err) {
      setQcError(err instanceof Error ? err.message : 'Error de conexión')
    }
  }

  // Incidencia (spec 04 §3.3): formulario clásico + foto QR opcional.
  // El operario reporta siempre (observaciones + tipo); la foto es una vía
  // MÁS, no la única: el QR solo se activa si el operario pulsa "Adjuntar foto".
  const [incModalOpen, setIncModalOpen] = useState(false)
  const [incSession, setIncSession] = useState<UploadSession | null>(null)
  const [incPhotoUrl, setIncPhotoUrl] = useState<string | null>(null)
  const [incStatus, setIncStatus] = useState<
    'form' | 'creating' | 'waiting' | 'photo' | 'expired' | 'error' | 'submitting'
  >('form')
  const [incDescripcion, setIncDescripcion] = useState('')
  const [incTipo, setIncTipo] = useState('maquina')
  const [incMsg, setIncMsg] = useState('')
  const [incError, setIncError] = useState('')
  const [incFecha, setIncFecha] = useState('')
  const incPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopIncPoll = () => {
    if (incPollRef.current) {
      clearInterval(incPollRef.current)
      incPollRef.current = null
    }
  }

  const adjuntarFoto = () => {
    setIncError('')
    setIncStatus('creating')
    setIncSession(null)
    setIncPhotoUrl(null)
    fetch('/api/v1/incidencias/upload-session', { method: 'POST' })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error())))
      .then((sesion) => {
        setIncSession(sesion)
        setIncStatus('waiting')
        incPollRef.current = setInterval(() => {
          fetch(`/api/v1/incidencias/upload-session/${sesion.session_id}`)
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error())))
            .then((estado) => {
              if (estado.has_photo && estado.photo_data_url) {
                setIncPhotoUrl(estado.photo_data_url)
                setIncStatus('photo')
                stopIncPoll()
              } else if (estado.status === 'expired') {
                setIncStatus('expired')
                stopIncPoll()
              }
            })
            .catch(() => {})
        }, 2000)
      })
      .catch(() => {
        setIncStatus('form')
        setIncError('No se pudo crear la sesión de subida. Inténtalo de nuevo.')
      })
  }

  const quitarFoto = () => {
    stopIncPoll()
    setIncSession(null)
    setIncPhotoUrl(null)
    setIncStatus('form')
  }

  const abrirModalIncidencia = () => {
    setIncModalOpen(true)
    setIncStatus('form')
    setIncSession(null)
    setIncPhotoUrl(null)
    setIncDescripcion('')
    setIncTipo('maquina')
    setIncMsg('')
    setIncError('')
    setIncFecha(new Date().toLocaleString('es-ES'))
  }

  const cerrarModalIncidencia = () => {
    stopIncPoll()
    setIncModalOpen(false)
  }

  const enviarIncidencia = async () => {
    setIncMsg('')
    setIncError('')
    if (!incDescripcion.trim()) {
      setIncError('Describe el problema antes de reportar.')
      return
    }
    setIncStatus('submitting')
    try {
      const res = await fetch('/api/v1/incidencias', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          linea_id: ordenActual?.workstation_id,
          descripcion: incDescripcion.trim(),
          tipo: incTipo,
          photo_session_id: incSession?.session_id ?? null,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? 'Error al reportar incidencia')
      }
      await res.json()
      setIncMsg('Incidencia registrada')
      setIncModalOpen(false)
      stopIncPoll()
    } catch (err) {
      setIncStatus(incPhotoUrl ? 'photo' : 'form')
      setIncError(err instanceof Error ? err.message : 'Error de conexión')
    }
  }

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

          {/* Autocontrol de calidad (spec 04): no bloquea, solo informa */}
          {puedeAutocontrol && (
            <form
              onSubmit={handleQualityCheck}
              className="bg-kavana-dark border border-kavana-border rounded-sm p-4 space-y-3 text-left"
            >
              <p className="label-industrial text-xs text-kavana-text-dim">
                Autocontrol de calidad
              </p>
              <p className="text-xs text-kavana-text-dim">
                {modelo?.name} · {modelo?.code}
              </p>

              {qcMsg && (
                <p className="text-kavana-ok text-sm border border-kavana-ok/40 rounded-sm p-2">
                  {qcMsg}
                </p>
              )}
              {qcError && (
                <p className="text-kavana-danger text-sm border border-kavana-danger/40 rounded-sm p-2">
                  {qcError}
                </p>
              )}

              {modelo?.quality_plan.map((check) => (
                <div key={check.id} className="space-y-1">
                  <label
                    htmlFor={`qc-${check.id}`}
                    className="block text-sm"
                  >
                    {check.name}
                    {check.is_critical && (
                      <span className="text-kavana-orange"> *</span>
                    )}
                    {check.tool_id && (
                      <span className="text-kavana-text-dim text-xs">
                        {' '}· {check.tool_id}
                      </span>
                    )}
                  </label>
                  {check.tipo === 'numeric' ? (
                    <input
                      id={`qc-${check.id}`}
                      type="number"
                      step="any"
                      value={
                        (mediciones[check.name] as
                          | string
                          | number
                          | undefined) ?? ''
                      }
                      onChange={(e) =>
                        setMedicion(
                          check.name,
                          e.target.value === ''
                            ? ''
                            : Number(e.target.value),
                        )
                      }
                      placeholder={
                        check.nominal_value != null
                          ? `Nominal ${check.nominal_value} ±${check.tolerance_plus ?? 0}/${check.tolerance_minus ?? 0}`
                          : 'Valor'
                      }
                      className="mono-data w-full bg-kavana-surface border border-kavana-border rounded-sm px-3 py-2 text-base focus:border-kavana-orange outline-none"
                    />
                  ) : (
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        aria-label={`Aprobar ${check.name}`}
                        onClick={() => setMedicion(check.name, true)}
                        className={`min-h-[44px] border rounded-sm font-bold uppercase tracking-widest transition-colors ${
                          mediciones[check.name] === true
                            ? 'bg-kavana-ok text-black border-kavana-ok'
                            : 'border-kavana-border text-kavana-text-dim hover:border-kavana-ok hover:text-kavana-ok'
                        }`}
                      >
                        OK
                      </button>
                      <button
                        type="button"
                        aria-label={`Rechazar ${check.name}`}
                        onClick={() => setMedicion(check.name, false)}
                        className={`min-h-[44px] border rounded-sm font-bold uppercase tracking-widest transition-colors ${
                          mediciones[check.name] === false
                            ? 'bg-kavana-danger text-white border-kavana-danger'
                            : 'border-kavana-border text-kavana-text-dim hover:border-kavana-danger hover:text-kavana-danger'
                        }`}
                      >
                        NO
                      </button>
                    </div>
                  )}
                </div>
              ))}

              <button
                type="submit"
                className="w-full min-h-[52px] border border-kavana-orange text-kavana-orange font-bold uppercase tracking-widest rounded-sm hover:bg-kavana-orange hover:text-black transition-colors"
              >
                📋 Registrar autocontrol
              </button>
            </form>
          )}

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

      {/* Reportar incidencia (spec 04 §3.3): modal QR + móvil, siempre accesible */}
      {ordenActual?.workstation_id && (
        <div className="space-y-3">
          <button
            onClick={abrirModalIncidencia}
            className="w-full min-h-[52px] border border-kavana-danger text-kavana-danger font-bold uppercase tracking-widest rounded-sm hover:bg-kavana-danger hover:text-white transition-colors"
          >
            ⚠️ Reportar incidencia
          </button>
          {incMsg && (
            <p className="text-kavana-ok text-sm border border-kavana-ok/40 rounded-sm p-2">
              {incMsg}
            </p>
          )}
        </div>
      )}

      {incModalOpen && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg bg-kavana-surface border border-kavana-orange/50 rounded-sm p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-kavana-border pb-3">
              <h2 className="text-lg font-bold uppercase tracking-widest">
                Reportar incidencia
              </h2>
              <button
                onClick={cerrarModalIncidencia}
                aria-label="Cerrar"
                className="text-kavana-text-dim hover:text-white"
              >
                ✕
              </button>
            </div>

            {incError && (
              <p className="text-kavana-danger text-sm border border-kavana-danger/40 rounded-sm p-2">
                {incError}
              </p>
            )}

            {/* Datos auto-importados (formulario clásico): el sistema conoce
                operario, puesto, modelo y fecha; el operario solo observa. */}
            <div className="grid grid-cols-2 gap-2 text-xs border border-kavana-border rounded-sm p-3">
              <div>
                <span className="label-industrial text-kavana-text-dim">Operario</span>
                <p className="font-semibold">Operario Demo</p>
              </div>
              <div>
                <span className="label-industrial text-kavana-text-dim">Puesto</span>
                <p className="font-semibold">{ordenActual?.workstation_id}</p>
              </div>
              <div>
                <span className="label-industrial text-kavana-text-dim">Modelo</span>
                <p className="font-semibold">
                  {modelo ? `${modelo.name} · ${modelo.code}` : '—'}
                </p>
              </div>
              <div>
                <span className="label-industrial text-kavana-text-dim">Fecha y hora</span>
                <p className="font-semibold">{incFecha}</p>
              </div>
            </div>

            {incStatus === 'creating' && (
              <div className="flex flex-col items-center gap-4 py-10 text-kavana-text-dim">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-kavana-orange border-t-transparent" />
                <p className="text-sm font-bold uppercase tracking-wider">
                  Creando sesión…
                </p>
              </div>
            )}

            {incStatus === 'form' && (
              <button
                type="button"
                onClick={adjuntarFoto}
                className="w-full min-h-[48px] border border-dashed border-kavana-border text-kavana-text-dim font-bold uppercase tracking-widest rounded-sm hover:border-kavana-orange hover:text-kavana-orange transition-colors"
              >
                📷 Adjuntar foto (opcional)
              </button>
            )}

            {(incStatus === 'waiting' ||
              incStatus === 'photo' ||
              incStatus === 'expired') &&
              incSession && (
                <div className="border-2 border-dashed border-kavana-border bg-kavana-dark/60 p-5 text-center space-y-3">
                  {incStatus === 'photo' && incPhotoUrl ? (
                    <div className="relative">
                      <img
                        src={incPhotoUrl}
                        alt="Evidencia"
                        className="mx-auto max-h-56 w-full rounded-sm object-cover"
                      />
                      <span className="absolute right-2 top-2 rounded-sm bg-kavana-ok/90 px-3 py-1 text-xs font-bold uppercase text-black">
                        Foto recibida
                      </span>
                      <button
                        onClick={quitarFoto}
                        className="absolute bottom-2 right-2 rounded-sm bg-kavana-danger px-3 py-1.5 text-xs font-bold text-white"
                      >
                        Quitar foto
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="mx-auto w-fit rounded-sm bg-white p-3">
                        <QRCodeSVG
                          value={`${window.location.origin}/mobile-upload/${incSession.session_id}`}
                          size={150}
                          title="QR de subida de foto"
                        />
                      </div>
                      <p className="text-sm font-bold uppercase tracking-wider">
                        Escanea con tu móvil
                      </p>
                      <p className="text-xs text-kavana-text-dim">
                        Abre la cámara del móvil, escanea el QR y sube la foto de
                        la incidencia.
                      </p>
                      {incStatus === 'expired' && (
                        <p className="text-xs font-bold text-amber-400">
                          La sesión caducó. Cierra y vuelve a abrir el modal para
                          generar un QR nuevo.
                        </p>
                      )}
                    </>
                  )}
                </div>
              )}

            <div className="space-y-3">
              <label className="block">
                <span className="label-industrial text-xs text-kavana-text-dim">
                  Tipo de incidencia
                </span>
                <select
                  value={incTipo}
                  onChange={(e) => setIncTipo(e.target.value)}
                  className="w-full bg-kavana-dark border border-kavana-border rounded-sm px-3 py-2 text-base focus:border-kavana-orange outline-none"
                >
                  <option value="maquina">Máquina</option>
                  <option value="material">Material</option>
                  <option value="seguridad">Seguridad</option>
                  <option value="otro">Otro</option>
                </select>
              </label>

              <label className="block">
                <span className="label-industrial text-xs text-kavana-text-dim">
                  Observaciones
                </span>
                <textarea
                  value={incDescripcion}
                  onChange={(e) => setIncDescripcion(e.target.value)}
                  placeholder="Detalla la incidencia"
                  rows={3}
                  className="w-full bg-kavana-dark border border-kavana-border rounded-sm px-3 py-2 text-base focus:border-kavana-orange outline-none"
                />
              </label>

              <button
                type="button"
                onClick={enviarIncidencia}
                disabled={incStatus === 'submitting' || incStatus === 'creating'}
                className="w-full min-h-[52px] bg-kavana-orange text-black font-bold uppercase tracking-widest rounded-sm disabled:cursor-not-allowed disabled:opacity-50"
              >
                {incStatus === 'submitting' ? 'Enviando…' : 'Enviar incidencia'}
              </button>
            </div>
          </div>
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

      {/* Alertas de almacén en tiempo real (ADR-014): WS con fallback REST */}
      <div className="bg-kavana-surface border border-kavana-border rounded-sm p-4 space-y-2">
        <div className="flex items-center justify-between gap-3">
          <p className="label-industrial text-xs text-kavana-text-dim">
            Alertas de almacén
          </p>
          <ConexionBadge estado={estado} />
        </div>
        {eventosVisibles.length === 0 ? (
          <p className="text-xs text-kavana-text-dim">Sin alertas recientes.</p>
        ) : (
          eventosVisibles.slice(-3).map((ev) => (
            <div
              key={ev.id}
              className="flex items-start justify-between gap-3 text-sm border-l-2 border-kavana-orange pl-3"
            >
              <span className="mono-data">{ev.tipo}</span>
              <span className="text-kavana-text-dim">
                {JSON.stringify(ev.data)}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

/** Badge del estado de la conexión de eventos (ADR-014). */
function ConexionBadge({ estado }: { estado: ConexionEstado }) {
  const texto =
    estado === 'conectado'
      ? 'En vivo'
      : estado === 'reconectando'
        ? 'Reconectando...'
        : estado === 'conectando'
          ? 'Conectando...'
          : 'Sin conexión'
  const clase =
    estado === 'conectado'
      ? 'border-kavana-ok/40 bg-kavana-ok/10 text-kavana-ok'
      : estado === 'reconectando'
        ? 'border-amber-400/40 bg-amber-400/10 text-amber-400'
        : 'border-kavana-border bg-kavana-text-dim/10 text-kavana-text-dim'
  return (
    <span
      className={`label-industrial text-[10px] uppercase tracking-wider rounded-sm border px-2 py-0.5 ${clase}`}
    >
      {texto}
    </span>
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
