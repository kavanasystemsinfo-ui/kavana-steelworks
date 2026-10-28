import { useEffect, useRef, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { api, getTenantId, type EventData, type FichaOrden as FichaOrdenData, type OrderItem, type WorkstationItem } from '../lib/api'
import { usePlantEvents, type ConexionEstado } from '../hooks/usePlantEvents'
import { useQualityReminders } from '../lib/useQualityReminders'
import { Numpad } from '../components/Numpad'
import { AltaManualBobina } from '../components/AltaManualBobina'
import { BobinasDisponibles } from '../components/BobinasDisponibles'
import { MedirCierre } from '../components/MedirCierre'
import { FichaOrden } from '../components/FichaOrden'

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

interface OrdenDetalle {
  id: string
  line_id: string
  workstation_id: string | null
  material_id?: string | null
}

/** Traducción del estado evaluado del autocontrol (spec 04). */
function estadoCalidad(estado: string): string {
  if (estado === 'approved') return 'Aprobado'
  if (estado === 'rejected') return 'Rechazado (no bloquea la producción)'
  if (estado === 'rework') return 'Requiere retrabajo (no bloquea la producción)'
  return estado
}

/** Panel de Operario (PC de 15-17" junto a la máquina): una acción principal
 *  a la vez. Directriz Jorge: no abrumar, guía de acción visible, sin perder
 *  funcionalidad. Rediseño 28-10 (maqueta aprobada): tema claro, la ficha de
 *  la orden siempre arriba, registrar a la izquierda y la bobina, el
 *  autocontrol y la jornada a la derecha; las horas se apuntan solas.
 */
export function OperarioPage() {
  const [coilId, setCoilId] = useState('')
  const [scan, setScan] = useState<CoilScan | null>(null)
  const [vinculada, setVinculada] = useState(false)
  const [ordenDetalle, setOrdenDetalle] = useState<OrdenDetalle | null>(null)
  const [toasts, setToasts] = useState<Array<{id: string; type: "success" | "error"; message: string}>>([]);
  const showToast = (type: "success" | "error", message: string) => {
    if (!message) return // las llamadas con '' solo limpiaban el antiguo aviso
    const id = Math.random().toString(36).substr(2, 9);
    setToasts(prev => [...prev, {id, type, message}]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 5000);
  };

  // Recordatorios de autocontrol NO bloqueantes (spec 04 §3.2.5): el
  // backend expone el estado; aquí se calculan los 15 min del primer aviso
  // y el ciclo de 2 h. Nunca bloquean la interfaz.
  const { notifyCheckRegistered, reminderToast } = useQualityReminders()

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
    showToast("error", '')
    setScan(null)
    try {
      const res = await api.scanCoil(coilId.trim(), '')
      if (!res) {
        showToast("error", 'Bobina no encontrada. Comprueba el código.')
        return
      }
      setScan(res)
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : 'Error de conexión')
    }
  }

  // Ficha de la orden (datos clave + bobina montada), refrescada tras cada acción
  const [ficha, setFicha] = useState<FichaOrdenData | null>(null)
  const [fichaVersion, setFichaVersion] = useState(0)
  const refrescarFicha = () => setFichaVersion((v) => v + 1)
  const [ahora, setAhora] = useState(() => Date.now())

  useEffect(() => {
    if (!ordenDetalle?.id || !ordenDetalle.line_id) {
      setFicha(null)
      return
    }
    let vivo = true
    api
      .getFicha(ordenDetalle.id, ordenDetalle.line_id)
      .then((d) => {
        if (!vivo) return
        const valida = d && typeof d.numero === 'string' && typeof d.total === 'number'
        setFicha(valida ? d : null)
        // Al volver al panel con una bobina ya montada, se sigue produciendo con ella
        if (valida && d.bobina) {
          const montada = d.bobina
          setScan((actual) =>
            actual ?? {
              id: montada.id,
              lote: montada.codigo,
              coil_id: montada.codigo,
              peso_kg: montada.kg,
              ancho_mm: d.ancho_mm,
              espesor_mm: d.espesor_mm,
              material_code: d.material,
              material_name: d.material_nombre,
              estado: 'activo',
              ubicacion: wsSel,
              modo: 'auto',
            },
          )
          setVinculada(true)
        }
      })
      .catch(() => vivo && setFicha(null))
    return () => {
      vivo = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ordenDetalle?.id, ordenDetalle?.line_id, fichaVersion])

  // El tiempo desde el último registro se ve correr (las horas se apuntan solas)
  useEffect(() => {
    const t = setInterval(() => setAhora(Date.now()), 30000)
    return () => clearInterval(t)
  }, [])
  const minutosTramo = ficha?.tramo_desde
    ? Math.max(0, Math.round((ahora - new Date(ficha.tramo_desde).getTime()) / 60000))
    : null

  const handleLink = async () => {
    showToast("error", '')
    if (!scan) return
    if (!ordenDetalle || !ordenDetalle.line_id) {
      showToast("error", 'No se pudo obtener la línea de la orden activa')
      return
    }
    try {
      await api.linkCoil({
        stock_item_id: scan.id,
        order_id: ordenDetalle.id,
        line_id: ordenDetalle.line_id,
      })
      setVinculada(true)
      refrescarFicha()
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : 'Error al vincular')
    }
  }

  const handleUnlink = async () => {
    showToast("error", '')
    if (!scan || !ordenDetalle || !ordenDetalle.line_id) return
    try {
      await api.unlinkCoil({
        stock_item_id: scan.id,
        order_id: ordenDetalle.id,
        line_id: ordenDetalle.line_id,
      })
      setVinculada(false)
      setScan(null)
      setCoilId('')
      showToast("success", 'Bobina desvinculada. Se reembolsó lo no consumido.')
      refrescarFicha()
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : 'Error al desvincular')
    }
  }

  // Cierre de jornada (Fase 1): confirmación y resultado (horas, turno A/B/C)
  const [confirmarCierre, setConfirmarCierre] = useState(false)
  const [jornadaCerrada, setJornadaCerrada] = useState<{ total_hours: number; turno: string } | null>(null)
  const [cerrandoJornada, setCerrandoJornada] = useState(false)
  // Bobinas montadas sin medir: con alguna, no se puede cerrar (Jorge, 28-10)
  const [sinMedir, setSinMedir] = useState<number | null>(null)

  const handleCerrarJornada = async () => {
    setCerrandoJornada(true)
    try {
      const res = await api.closeShift()
      setJornadaCerrada({ total_hours: res.total_hours, turno: res.turno })
      setConfirmarCierre(false)
      showToast(
        "success",
        `Jornada cerrada: ${res.total_hours.toLocaleString('es-ES')} h \u00b7 Turno ${res.turno}`,
      )
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : 'Error al cerrar la jornada')
    } finally {
      setCerrandoJornada(false)
    }
  }

  const [radioMm, setRadioMm] = useState('')
  const [piezas, setPiezas] = useState('')

  // Autocontrol de calidad (spec 04): plantilla + orden de la demo
  const [models, setModels] = useState<QualityModel[]>([])
  const [mediciones, setMediciones] = useState<
    Record<string, number | boolean | string>
  >({})

  // Pulido registro de órdenes (port legacy kavanasystems): puesto -> cola
  // de órdenes del puesto -> panel. La URL ?ws=&order= salta directo al
  // panel (compatibilidad con enlaces y con el comportamiento previo).
  const [puestos, setPuestos] = useState<WorkstationItem[]>([])
  const [puestosCargados, setPuestosCargados] = useState(false)
  const [cola, setCola] = useState<OrderItem[]>([])
  const [wsSel, setWsSel] = useState<string | null>(null)
  const [ordenSelId, setOrdenSelId] = useState<string | null>(null)
  const [ordenNumero, setOrdenNumero] = useState<string | null>(null)
  const [ordenWs, setOrdenWs] = useState<string | null>(null)
  const [vista, setVista] = useState<'panel' | 'seleccion' | 'cola'>('panel')
  const [pasoManual, setPasoManual] = useState<'puesto' | 'orden' | null>(null)
  const puestosRef = useRef<WorkstationItem[]>([])
  const ordenWsRef = useRef<string | null>(null)

  useEffect(() => {
    api.getQualityModels()
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) setModels(data)
      })
      .catch(() => {})
    const params = new URLSearchParams(window.location.search)
    const ws = params.get('ws')
    const orden = params.get('order')
    if (ws) setWsSel(ws)
    if (orden) setOrdenSelId(orden)
    api.listWorkstations()
      .then((data) => setPuestos(Array.isArray(data) ? data : []))
      .catch(() => setPuestos([]))
      .finally(() => setPuestosCargados(true))
  }, [])

  useEffect(() => {
    puestosRef.current = puestos
  }, [puestos])

  useEffect(() => {
    ordenWsRef.current = ordenWs
  }, [ordenWs])

  useEffect(() => {
    if (!puestosCargados) return
    const activos = puestosRef.current.filter((w) => w.is_active !== false)
    if (pasoManual === 'puesto') {
      setVista('seleccion')
      return
    }
    if (!wsSel && activos.length > 1) {
      setVista('seleccion')
      return
    }
    if (!wsSel && activos.length === 1) {
      setWsSel(activos[0].code)
      return
    }
    const ws = wsSel ?? undefined
    let cancelled = false
    api.availableOrders(ws)
      .then((items) => {
        if (cancelled) return
        const lista = Array.isArray(items) ? items : []
        setCola(lista)
        const desdeUrl = new URLSearchParams(window.location.search).get('order')
        if (desdeUrl && lista.some((o) => o.id === desdeUrl)) {
          const item = lista.find((o) => o.id === desdeUrl)
          setOrdenSelId(desdeUrl)
          if (item) {
            setOrdenNumero(item.numero)
            setOrdenWs(item.workstation_id ?? null)
          }
          setVista('panel')
          return
        }
        if (pasoManual === 'orden') {
          setVista('cola')
          return
        }
        // Un puesto sin órdenes también va a la cola: dice que no hay y deja
        // cambiar de puesto (antes se quedaba en la selección sin avisar)
        if (lista.length > 1 || (ws && lista.length === 0)) {
          setVista('cola')
          return
        }
        if (lista.length === 1) {
          setOrdenSelId(lista[0].id)
          setOrdenNumero(lista[0].numero)
          setOrdenWs(lista[0].workstation_id ?? null)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [puestosCargados, wsSel, pasoManual])

  useEffect(() => {
    if (!ordenSelId) return
    let cancelled = false
    api.getOrder(ordenSelId)
      .then((orderDetail) => {
        if (cancelled) return
        if (
          orderDetail &&
          Array.isArray(orderDetail.lines) &&
          orderDetail.lines.length > 0
        ) {
          // La línea de este puesto (una orden pasa por varios puestos). Al
          // entrar por la URL aún no se conoce la orden de la cola: manda ?ws=
          const ws = ordenWsRef.current ?? new URLSearchParams(window.location.search).get('ws')
          const line =
            orderDetail.lines.find((l: { workstation_id?: string | null }) => ws && l.workstation_id === ws) ??
            orderDetail.lines[0]
          setOrdenDetalle({
            id: orderDetail.id ?? ordenSelId,
            line_id: line.id,
            workstation_id: line.workstation_id ?? ordenWsRef.current,
            material_id: line.material_id ?? null,
          })
        } else {
          setOrdenDetalle({
            id: orderDetail?.id ?? ordenSelId,
            line_id: '',
            workstation_id: orderDetail?.workstation_id ?? ordenWsRef.current,
          })
        }
        if (orderDetail && orderDetail.numero) setOrdenNumero(orderDetail.numero)
        setVista('panel')
      })
      .catch(() => {
        if (cancelled) return
        setOrdenDetalle({
          id: ordenSelId,
          line_id: '',
          workstation_id: ordenWsRef.current,
        })
        setVista('panel')
      })
    return () => {
      cancelled = true
    }
  }, [ordenSelId])

  const elegirPuesto = (code: string) => {
    setWsSel(code)
    setPasoManual(null)
    setOrdenSelId(null)
    setOrdenNumero(null)
    setOrdenDetalle(null)
    setCola([])
    const u = new URL(window.location.href)
    u.searchParams.set('ws', code)
    u.searchParams.delete('order')
    window.history.replaceState({}, '', u)
  }

  const elegirOrden = (o: OrderItem) => {
    setPasoManual(null)
    setScan(null)
    setVinculada(false)
    setCoilId('')
    setOrdenSelId(o.id)
    setOrdenNumero(o.numero)
    setOrdenWs(o.workstation_id ?? null)
    const u = new URL(window.location.href)
    u.searchParams.set('order', o.id)
    window.history.replaceState({}, '', u)
  }

  const cambiarPuesto = () => {
    setPasoManual('puesto')
    setWsSel(null)
    setOrdenSelId(null)
    setOrdenNumero(null)
    setOrdenWs(null)
    setOrdenDetalle(null)
    setCola([])
    setScan(null)
    setVinculada(false)
    setVista('seleccion')
    const u = new URL(window.location.href)
    u.searchParams.delete('order')
    u.searchParams.delete('ws')
    window.history.replaceState({}, '', u)
  }

  const cambiarOrden = () => {
    setPasoManual('orden')
    setOrdenSelId(null)
    setOrdenNumero(null)
    setOrdenWs(null)
    setOrdenDetalle(null)
    setScan(null)
    setVinculada(false)
    setVista('cola')
    const u = new URL(window.location.href)
    u.searchParams.delete('order')
    window.history.replaceState({}, '', u)
  }

  const modelo = models[0] ?? null
  const puedeAutocontrol = Boolean(modelo && ordenDetalle?.workstation_id)

  const setMedicion = (name: string, valor: number | boolean | string) => {
    setMediciones((prev) => ({ ...prev, [name]: valor }))
  }

  const handleQualityCheck = async (e: React.FormEvent) => {
    e.preventDefault()
    // Toast clearing removed - toasts now persist until next operation

    if (!modelo || !ordenDetalle || !scan) return
    const lista = Object.entries(mediciones)
      .filter(([, v]) => v !== '' && v !== undefined)
      .map(([name, value]) => ({ check_name: name, value_entered: value }))
    if (lista.length === 0) {
      showToast("error", 'Mide al menos un control antes de registrar.')
      return
    }
    try {
      const res = await api.createQualityCheck({
        order_id: ordenDetalle.id,
        workstation_id: ordenDetalle.workstation_id ?? '',
        manufacturing_model_id: modelo.id,
        stock_item_id: scan.id,
        measurements: lista,
      })
      showToast("success", estadoCalidad(res.record?.overall_status ?? ''))
      setMediciones({})
      // Un autocontrol registrado reinicia el temporizador de recordatorios
      notifyCheckRegistered()
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : 'Error de conexión')
    }
  }

  // Incidencia (spec 04 §3.3): formulario clásico + foto QR opcional.
  // El operario reporta siempre (observaciones + tipo); la foto es una vía
  // MÁS, no la única: el QR solo se activa si el operario pulsa "Adjuntar foto".
  const [incModalOpen, setIncModalOpen] = useState(false)
  const [incSession, setIncSession] = useState<{ sessionId: string; expiresAt: string } | null>(null)
  const [incPhotoUrl, setIncPhotoUrl] = useState<string | null>(null)
  const [incStatus, setIncStatus] = useState<
    'form' | 'creating' | 'waiting' | 'photo' | 'expired' | 'error' | 'submitting'
  >('form')
  const [incDescripcion, setIncDescripcion] = useState('')
  const [incTipo, setIncTipo] = useState('maquina')
  const [incFecha, setIncFecha] = useState('')
  const incPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopIncPoll = () => {
    if (incPollRef.current) {
      clearInterval(incPollRef.current)
      incPollRef.current = null
    }
  }

  const adjuntarFoto = () => {
    showToast("error", '')
    setIncStatus('creating')
    setIncSession(null)
    setIncPhotoUrl(null)
    api.createIncidenciaUploadSession()
      .then((sesion) => {
        setIncSession(sesion)
        setIncStatus('waiting')
        incPollRef.current = setInterval(() => {
          api.getIncidenciaUploadSession(sesion.sessionId)
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
        showToast("error", 'No se pudo crear la sesión de subida. Inténtalo de nuevo.')
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
    // Toast clearing removed - toasts now persist until next operation

    setIncFecha(new Date().toLocaleString('es-ES'))
  }

  const cerrarModalIncidencia = () => {
    stopIncPoll()
    setIncModalOpen(false)
  }

  const enviarIncidencia = async () => {
    // Toast clearing removed - toasts now persist until next operation

    if (!incDescripcion.trim()) {
      showToast("error", 'Describe el problema antes de reportar.')
      return
    }
    setIncStatus('submitting')
    try {
      await api.createIncidencia({
        linea_id: ordenDetalle?.workstation_id ?? '',
        descripcion: incDescripcion.trim(),
        tipo: incTipo,
        photo_session_id: incSession?.sessionId ?? null,
      })
      showToast("success", 'Incidencia registrada')
      setIncModalOpen(false)
      stopIncPoll()
    } catch (err) {
      setIncStatus(incPhotoUrl ? 'photo' : 'form')
      showToast("error", err instanceof Error ? err.message : 'Error de conexión')
    }
  }

  const handleRecordProduction = async (e: React.FormEvent) => {
    e.preventDefault()
    showToast("success", '')
    if (!scan) return
    if (!ordenDetalle || !ordenDetalle.line_id) {
      showToast("error", 'No se pudo obtener la orden activa')
      return
    }
    try {
      const res = await api.recordProduction({
        order_id: ordenDetalle.id,
        line_id: ordenDetalle.line_id,
        incremental_quantity: Number(piezas),
        // Sin horas: el servidor cuenta el tiempo desde el último registro
        observaciones: '',
      })
      showToast("success", 
        `${res.incremental_quantity ?? 0} piezas registradas · ${Number(res.consumed_amount ?? 0).toLocaleString('es-ES', { maximumFractionDigits: 1 })} ${res.consumption_unit ?? ''} consumidos`,
      )
      setPiezas('')
      refrescarFicha()
    } catch (err) {
      showToast("error", 
        err instanceof Error ? err.message : 'Error al registrar producción',
      )
    }
  }

  const handleFinBobina = async (e: React.FormEvent) => {
    e.preventDefault()
    showToast("success", '')
    if (!scan) return
    if (!ordenDetalle || !ordenDetalle.line_id) {
      showToast("error", 'No se pudo obtener la orden activa')
      return
    }
    try {
      const res = await api.finBobina({
        stock_item_id: scan.id,
        order_id: ordenDetalle.id,
        line_id: ordenDetalle.line_id,
        radio_mm: Number(radioMm),
      })
      showToast("success", 
        `${res.msg}: quedan ${res.peso_restante_kg} kg, ${res.merma_kg} kg de merma (${res.merma_cost} €)`,
      )
      refrescarFicha()
      setVinculada(false)
      setScan(null)
      setCoilId('')
    } catch (err) {
      showToast("error", 
        err instanceof Error ? err.message : 'Error al cerrar bobina',
      )
    }
  }

  const handleRetirarPico = async () => {
    showToast("success", '')
    if (!scan) return
    if (!ordenDetalle || !ordenDetalle.line_id) {
      showToast("error", 'No se pudo obtener la orden activa')
      return
    }
    try {
      const res = await api.retirarPico({ stock_item_id: scan.id })
      showToast("success", res.msg)
      setVinculada(false)
      setScan(null)
      setCoilId('')
    } catch (err) {
      showToast("error", 
        err instanceof Error ? err.message : 'Error al retirar pico',
      )
    }
  }

  if (vista === 'seleccion') {
    const activos = puestos.filter((w) => w.is_active !== false)
    return (
      <div className="max-w-3xl mx-auto space-y-4">
        <div className="step-guide">
          <p className="label-industrial text-xs text-kavana-text-dim">
            Paso 1 de 3
          </p>
          <p className="text-lg font-bold">Selecciona tu puesto de trabajo</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {activos.map((w) => (
            <button
              key={w.id}
              type="button"
              onClick={() => elegirPuesto(w.code)}
              className="bg-kavana-surface border-2 border-kavana-border rounded-xl p-5 text-left hover:border-kavana-orange transition-colors"
            >
              <span className="label-industrial text-[10px] text-kavana-text-dim">
                Puesto
              </span>
              <p className="text-xl font-black uppercase">{w.name || w.code}</p>
              <p className="mono-data text-sm text-kavana-orange">{w.code}</p>
            </button>
          ))}
        </div>
        {activos.length === 0 && (
          <div className="bg-kavana-surface border border-dashed border-kavana-border rounded-xl p-8 text-center text-kavana-text-dim">
            Sin puestos de trabajo configurados.
          </div>
        )}
      </div>
    )
  }

  if (vista === 'cola') {
    return (
      <div className="max-w-3xl mx-auto space-y-4">
        <div className="step-guide">
          <p className="label-industrial text-xs text-kavana-text-dim">
            Paso 2 de 3
          </p>
          <p className="text-lg font-bold">
            Cola de órdenes{wsSel ? ` · ${wsSel}` : ''}
          </p>
        </div>
        <div className="grid gap-3">
          {cola.map((o) => (
            <button
              key={o.id}
              type="button"
              onClick={() => elegirOrden(o)}
              className="bg-kavana-surface border-2 border-kavana-border rounded-xl p-5 text-left hover:border-kavana-orange transition-colors"
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-2xl font-black uppercase">#{o.numero}</p>
                <span className="label-industrial text-[10px] rounded border px-2 py-0.5 border-kavana-border text-kavana-text-dim">
                  {o.estado}
                </span>
              </div>
              <p className="mt-1 text-sm text-kavana-text-dim">
                {o.cliente ?? 'Sin cliente'}
              </p>
            </button>
          ))}
          {cola.length === 0 && (
            <div className="bg-kavana-surface border border-dashed border-kavana-border rounded-xl p-8 text-center text-kavana-text-dim">
              Sin órdenes para este puesto. Esperando planificación.
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={cambiarPuesto}
          className="w-full min-h-[52px] border border-kavana-border text-kavana-text-dim font-bold rounded-xl hover:border-kavana-orange transition-colors"
        >
          ← Cambiar puesto
        </button>
      </div>
    )
  }

  return (
    <div className="tema-panel tema-operario -m-4 min-h-[calc(100vh-3.5rem)] bg-p-fondo text-p-texto font-panel tabular-nums">
    <div className="max-w-[1400px] mx-auto px-4 py-4 lg:px-6 space-y-4">
      {/* Toast container for success/error */}
      <div className="top-6 right-6 fixed z-[90]">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role={toast.type === 'error' ? 'alert' : 'status'}
            className={`mb-3 max-w-md px-4 py-3 rounded-xl border shadow-lg text-sm font-semibold
            ${toast.type === "success"
              ? "border-p-ok-borde bg-p-ok-bg text-p-ok"
              : "border-p-mal-borde bg-p-mal-bg text-p-mal"}`}
          >
            {toast.message}
          </div>
        ))}
      </div>
      {/* Recordatorio de autocontrol NO bloqueante (spec 04 §3.2.5): toast
          fijo visible, no interrumpe el flujo ni detiene la línea. */}
      {reminderToast && (
        <div
          role="status"
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[80] border border-kavana-orange/60 bg-kavana-dark px-4 py-3 text-sm shadow-lg"
        >
          {reminderToast}
        </div>
      )}

      {/* Guía de acción: el siguiente paso siempre identificable */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div>
          <p className="text-xs text-p-texto2">Paso actual</p>
          <p className="text-lg font-bold">{vinculada ? 'Producir piezas' : 'Vincular bobina'}</p>
        </div>
        <span className="flex-1" />
        <span className="text-sm text-p-texto2">{wsSel ?? 'puesto por defecto'}</span>
        <button
          type="button"
          onClick={cambiarOrden}
          className="min-h-[40px] rounded-lg border border-p-borde bg-p-tarjeta px-3 text-sm font-semibold hover:border-p-plan"
        >
          Cambiar orden
        </button>
        <button
          type="button"
          onClick={cambiarPuesto}
          className="min-h-[40px] rounded-lg border border-p-borde bg-p-tarjeta px-3 text-sm font-semibold hover:border-p-plan"
        >
          Cambiar puesto
        </button>
      </div>

      <FichaOrden ficha={ficha} numero={ordenNumero} />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)] items-start">
        {/* Izquierda: la acción principal (vincular o registrar) */}
        <div className="space-y-4">
          {!vinculada ? (
            <>
        <form
          onSubmit={handleScan}
          className="bg-p-tarjeta border border-p-borde rounded-2xl p-6 space-y-4"
        >
          <label className="block">
            <span className="label-industrial text-xs text-kavana-text-dim">
              Código de bobina
            </span>
            <input
              value={coilId}
              onChange={(e) => setCoilId(e.target.value)}
              placeholder="Escanea la etiqueta o escribe el ID"
              className="mono-data mt-1 w-full bg-kavana-dark border border-kavana-border rounded-xl px-3 py-3 min-h-[52px] text-lg focus:border-kavana-orange outline-none"
              autoFocus
            />
          </label>



          {/* Ficha de la bobina escaneada (modo automático) */}
          {scan && (
            <div className="bg-kavana-dark border border-kavana-border rounded-xl p-4 space-y-2">
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
                className="w-full min-h-[64px] bg-kavana-orange text-black font-bold rounded-xl hover:opacity-90 transition-opacity"
              >
                Vincular a mi orden
              </button>
            </div>
          )}

          {!scan && (
            <button
              type="submit"
              disabled={!coilId.trim()}
              className="w-full min-h-[64px] bg-kavana-orange text-black font-bold rounded-xl disabled:opacity-40 hover:opacity-90 transition-opacity"
            >
              Escanear bobina
            </button>
          )}
        </form>
        {!scan && ordenDetalle?.line_id && (
          <BobinasDisponibles
            lineId={ordenDetalle.line_id}
            onElegir={(bobina) => {
              setScan(bobina)
              setCoilId(bobina.coil_id ?? '')
            }}
          />
        )}
        {!scan && (
          <AltaManualBobina
            puesto={wsSel}
            materialId={ordenDetalle?.material_id ?? null}
            onAlta={(bobina) => {
              setScan(bobina)
              setCoilId(bobina.coil_id ?? '')
              showToast('success', `Bobina ${bobina.coil_id} registrada con ${bobina.peso_kg} kg de etiqueta`)
            }}
          />
        )}
            </>
          ) : (
            /* Registrar producción: piezas buenas (auto-consumo FIFO) */
            <form
              onSubmit={handleRecordProduction}
              aria-label="Registrar piezas"
              className="bg-p-tarjeta border border-p-borde rounded-2xl p-6 space-y-4"
            >
              <h2 className="text-xl font-bold">Registrar producción</h2>
              <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] items-start">
                <div className="space-y-3">
                  <label className="block">
                    <span className="text-sm text-p-texto2">Piezas buenas</span>
                    <input
                      type="number"
                      step="1"
                      min="1"
                      value={piezas}
                      onChange={(e) => setPiezas(e.target.value)}
                      placeholder="Piezas"
                      className="mono-data mt-1 w-full bg-p-tarjeta border border-p-borde rounded-xl px-4 min-h-[64px] text-3xl font-extrabold focus:border-kavana-orange outline-none"
                      required
                    />
                  </label>
                  <div className="rounded-xl bg-p-fondo px-4 py-3">
                    <p className="text-sm text-p-texto2">Tiempo desde el último registro</p>
                    <p className="text-xl font-bold">
                      {minutosTramo === null
                        ? '—'
                        : minutosTramo >= 60
                          ? `${Math.floor(minutosTramo / 60)} h ${String(minutosTramo % 60).padStart(2, '0')} min`
                          : `${minutosTramo} min`}
                    </p>
                    <p className="text-xs text-p-texto2">Se apunta solo, no hace falta escribirlo</p>
                  </div>
                </div>
                <Numpad value={piezas} onChange={setPiezas} step={1} allowDecimals={false} min={1} />
              </div>
              <button
                type="submit"
                className="w-full min-h-[60px] rounded-xl bg-kavana-orange text-white text-lg font-extrabold hover:opacity-90 transition-opacity"
              >
                {piezas ? `Registrar ${piezas} piezas` : 'Registrar piezas'}
              </button>
            </form>
          )}
        </div>

        {/* Derecha: bobina montada, autocontrol, incidencias y jornada */}
        <div className="space-y-4">
          {vinculada && (
            <section aria-label="Bobina montada" className="bg-p-tarjeta border border-p-borde rounded-2xl p-5 space-y-3">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold">Bobina montada</h2>
                <span className="flex-1" />
                <span className="mono-data text-sm text-p-texto2">{scan?.coil_id ?? `COIL-${coilId}`}</span>
              </div>
              {ficha?.bobina && (
                <>
                  <p className="flex flex-wrap items-baseline gap-x-3">
                    <span className="text-3xl font-extrabold">≈ {Math.round(ficha.bobina.kg).toLocaleString('es-ES')} kg</span>
                    {ficha.bobina.piezas_estimadas !== null && (
                      <span className="text-base text-p-texto2">
                        dan para ≈ {ficha.bobina.piezas_estimadas.toLocaleString('es-ES')} piezas
                      </span>
                    )}
                  </p>
                  <div className="h-2.5 rounded-full bg-p-linea">
                    <div
                      className="h-2.5 rounded-full bg-p-plan"
                      style={{ width: `${Math.min(100, Math.max(0, (ficha.bobina.kg / (ficha.bobina.kg_inicial || 1)) * 100))}%` }}
                    />
                  </div>
                </>
              )}
              <details className="rounded-xl border border-p-borde px-4 py-3">
                <summary className="cursor-pointer text-sm font-semibold">Fin de bobina o retirar pico</summary>
                <div className="mt-3 space-y-3">
          {/* Fin de bobina: medir los milímetros de radio restantes (visión Jorge) */}
          <form
            onSubmit={handleFinBobina}
            className="bg-kavana-dark border border-kavana-border rounded-xl p-4 space-y-3 text-left"
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
              className="mono-data w-full bg-kavana-surface border border-kavana-border rounded-xl px-3 py-3 min-h-[52px] text-lg focus:border-kavana-orange outline-none"
              required
            />
            <button
              type="submit"
              className="w-full min-h-[56px] border border-kavana-orange text-kavana-orange font-bold rounded-xl hover:bg-kavana-orange hover:text-black transition-colors"
            >
              Cerrar bobina (merma real)
            </button>
            <button
              type="button"
              onClick={handleRetirarPico}
              className="w-full min-h-[56px] border border-kavana-border text-kavana-text-dim font-bold rounded-xl hover:border-kavana-orange hover:text-kavana-orange transition-colors"
            >
              Retirar pico a inventario
            </button>
          </form>

                </div>
              </details>
              <button
                onClick={handleUnlink}
                className="w-full min-h-[48px] rounded-xl border border-p-borde text-sm font-semibold hover:border-p-plan"
              >
                Desvincular bobina
              </button>
            </section>
          )}

          {vinculada && puedeAutocontrol && (
            <div className="bg-p-tarjeta border border-p-borde rounded-2xl p-5">
          {/* Autocontrol de calidad (spec 04): no bloquea, solo informa */}
          {puedeAutocontrol && (
            <form
              onSubmit={handleQualityCheck}
              className="bg-kavana-dark border border-kavana-border rounded-xl p-4 space-y-3 text-left"
            >
              <p className="label-industrial text-xs text-kavana-text-dim">
                Autocontrol de calidad
              </p>
              <p className="text-xs text-kavana-text-dim">
                {modelo?.name} · {modelo?.code}
              </p>




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
                      className="mono-data w-full bg-kavana-surface border border-kavana-border rounded-xl px-3 py-2 text-base focus:border-kavana-orange outline-none"
                    />
                  ) : (
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        aria-label={`Aprobar ${check.name}`}
                        onClick={() => setMedicion(check.name, true)}
                        className={`min-h-[44px] border rounded-xl font-bold transition-colors ${
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
                        className={`min-h-[44px] border rounded-xl font-bold transition-colors ${
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
                className="w-full min-h-[52px] border border-kavana-orange text-kavana-orange font-bold rounded-xl hover:bg-kavana-orange hover:text-black transition-colors"
              >
                Registrar autocontrol
              </button>
            </form>
          )}

            </div>
          )}

      {/* Reportar incidencia (spec 04 §3.3): modal QR + móvil, siempre accesible */}
      {ordenDetalle?.workstation_id && (
        <div className="space-y-3">
          <button
            onClick={abrirModalIncidencia}
            className="w-full min-h-[52px] border border-kavana-danger text-kavana-danger font-bold rounded-xl hover:bg-kavana-danger hover:text-white transition-colors"
          >
            Reportar incidencia
          </button>

        </div>
      )}

      {/* Cierre de jornada (Fase 1): total_hours + turno A/B/C (spec 02 3.11) */}
      <div className="space-y-3">
        {jornadaCerrada ? (
          <div className="bg-kavana-surface border border-kavana-ok rounded-xl p-4 text-center space-y-1">
            <p className="label-industrial text-xs text-kavana-text-dim">Jornada cerrada</p>
            <p className="font-display font-black text-3xl text-kavana-ok">
              {`${jornadaCerrada.total_hours.toLocaleString('es-ES')} h \u00b7 Turno ${jornadaCerrada.turno}`}
            </p>
          </div>
        ) : confirmarCierre ? (
          <div className="bg-kavana-surface border border-kavana-orange/50 rounded-xl p-4 space-y-3">
            <p className="text-sm text-kavana-text-dim">
              ¿Cerrar turno? Se registrará la hora de salida y las horas trabajadas.
            </p>
            <MedirCierre onPendientes={setSinMedir} />
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setConfirmarCierre(false)}
                className="min-h-[52px] border border-kavana-border text-kavana-text-dim font-bold rounded-xl hover:border-kavana-orange hover:text-kavana-orange transition-colors"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleCerrarJornada}
                disabled={cerrandoJornada || sinMedir !== 0}
                className="min-h-[52px] bg-kavana-orange text-black font-bold rounded-xl disabled:opacity-40 hover:opacity-90 transition-opacity"
              >
                {cerrandoJornada ? 'Cerrando…' : 'Sí, cerrar'}
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirmarCierre(true)}
            className="w-full min-h-[52px] border border-kavana-border text-kavana-text-dim font-bold rounded-xl hover:border-kavana-orange hover:text-kavana-orange transition-colors"
          >
            Cerrar jornada
          </button>
        )}
      </div>

        </div>
      </div>

      {incModalOpen && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg bg-kavana-surface border border-kavana-orange/50 rounded-xl p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-kavana-border pb-3">
              <h2 className="text-lg font-bold">
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



            {/* Datos auto-importados (formulario clásico): el sistema conoce
                operario, puesto, modelo y fecha; el operario solo observa. */}
            <div className="grid grid-cols-2 gap-2 text-xs border border-kavana-border rounded-xl p-3">
              <div>
                <span className="label-industrial text-kavana-text-dim">Operario</span>
                <p className="font-semibold">Operario Demo</p>
              </div>
              <div>
                <span className="label-industrial text-kavana-text-dim">Puesto</span>
                <p className="font-semibold">{ordenDetalle?.workstation_id}</p>
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
                <p className="text-sm font-bold">
                  Creando sesión…
                </p>
              </div>
            )}

            {incStatus === 'form' && (
              <button
                type="button"
                onClick={adjuntarFoto}
                className="w-full min-h-[48px] border border-dashed border-kavana-border text-kavana-text-dim font-bold rounded-xl hover:border-kavana-orange hover:text-kavana-orange transition-colors"
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
                        className="mx-auto max-h-56 w-full rounded-xl object-cover"
                      />
                      <span className="absolute right-2 top-2 rounded-xl bg-kavana-ok/90 px-3 py-1 text-xs font-bold uppercase text-black">
                        Foto recibida
                      </span>
                      <button
                        onClick={quitarFoto}
                        className="absolute bottom-2 right-2 rounded-xl bg-kavana-danger px-3 py-1.5 text-xs font-bold text-white"
                      >
                        Quitar foto
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="mx-auto w-fit rounded-xl bg-white p-3">
                        <QRCodeSVG
                          value={`${window.location.origin}/mobile-upload/${incSession.sessionId}`}
                          size={150}
                          title="QR de subida de foto"
                        />
                      </div>
                      <p className="text-sm font-bold">
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
                  className="w-full bg-kavana-dark border border-kavana-border rounded-xl px-3 py-2 text-base focus:border-kavana-orange outline-none"
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
                  className="w-full bg-kavana-dark border border-kavana-border rounded-xl px-3 py-2 text-base focus:border-kavana-orange outline-none"
                />
              </label>

              <button
                type="button"
                onClick={enviarIncidencia}
                disabled={incStatus === 'submitting' || incStatus === 'creating'}
                className="w-full min-h-[52px] bg-kavana-orange text-black font-bold rounded-xl disabled:cursor-not-allowed disabled:opacity-50"
              >
                {incStatus === 'submitting' ? 'Enviando…' : 'Enviar incidencia'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Datos de apoyo colapsados: solo si el operario los necesita */}
      <details className="bg-kavana-surface border border-kavana-border rounded-xl p-4">
        <summary className="label-industrial text-xs text-kavana-text-dim cursor-pointer">
          Detalles de la orden
        </summary>
        {ordenDetalle && (
          <div className="mt-2 space-y-1 text-sm text-kavana-text-dim">
            <p><strong>Orden:</strong> {ordenDetalle.id}</p>
            <p><strong>Línea:</strong> {ordenDetalle.line_id || '—'}</p>
            <p><strong>Puesto:</strong> {ordenDetalle.workstation_id || '—'}</p>
          </div>
        )}
      </details>

      {/* Alertas de almacén en tiempo real (ADR-014): WS con fallback REST */}
      <div className="bg-kavana-surface border border-kavana-border rounded-xl p-4 space-y-2">
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
      className={`label-industrial text-[10px] rounded-xl border px-2 py-0.5 ${clase}`}
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
