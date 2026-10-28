/** Cliente API tipado para KAVANA Steelworks.
 *  El token JWT (8h, un turno) vive en sessionStorage (patrón del v2).
 */

export interface LoginResponse {
  access_token: string
  token_type: string
}

export interface StockItemOut {
  id: string
  lote: string
  coil_id: string | null
  material_id: string
  cantidad_disponible: number
  estado: string
  ubicacion: string | null
  fecha_entrada: string | null
}

export interface ReceiveCoilRequest {
  tenant_id: string
  material_id: string
  lote: string
  coil_id?: string
  peso: number
  width_mm?: number
  thickness_mm?: number
  coste_real?: number
  ubicacion?: string
  heat_number?: string
  grado_acero?: string
  supplier_coil_id?: string
}

export interface EventData {
  id: string
  tipo: string
  data: Record<string, unknown>
  timestamp: string
}

export interface MaterialOut {
  id: string
  code: string
  name: string
  cost_per_unit: number | null
  unit: string | null
  stock_current: number | null
  dimension_ancho_mm: number | null
  dimension_espesor_mm: number | null
}

export interface IncidenciaItem {
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

export interface OeeData {
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

export interface KpisData {
  orders_total: number
  orders_active: number
  orders_completed: number
  /** Material estimado (€/kg × objetivo); null si ninguna orden tiene base. */
  estimated_cost: number | null
  real_cost: number
  real_material_cost: number
  labor_cost: number
  real_material_comparable: number
  orders_with_estimate: number
  scrap_cost: number
  /** Material real - estimado, solo en órdenes con estimado; null sin base. */
  cost_variance: number | null
  cost_efficiency: number
  material_variance: number
  material_efficiency: number
  scrap_rate: number
}

/** Alertas del centro de mando (GET /supervisor/alertas). */
export interface AlertasData {
  stock_bajo_minimos: { code: string; name: string; stock: number; minimo: number; unidad: string }[]
  incidencias_abiertas: number
}

export interface InformeTurnoPuesto {
  puesto: string
  ordenes: number
  piezas: number
  consumo_kg: number
  consumo_m: number
  merma_kg: number
  merma_coste: number
  autocontroles: number
  autocontroles_nok: number
  incidencias: number
  parada_min: number
}

/** Balance de kilos del turno por operario, orden y material. */
export interface InformeTurnoOperario {
  operario: string
  orden: string
  material: string
  piezas: number
  consumo_kg: number
  piezas_kg: number
  chatarra_kg: number
  chatarra_pct: number | null
}

/** Bobina montada que el operario debe medir antes de cerrar su turno. */
export interface MedicionPendiente {
  stock_item_id: string
  coil_code: string | null
  order_id: string
  line_id: string
  puesto: string | null
}

/** Informe de un turno A/B/C (GET /supervisor/informe-turno). */
export interface InformeTurno {
  fecha: string
  turno: string
  inicio: string
  fin: string
  puestos: InformeTurnoPuesto[]
  totales: Omit<InformeTurnoPuesto, 'puesto' | 'ordenes'>
  por_operario: InformeTurnoOperario[]
}

/** Estado de un puesto en planta (GET /supervisor/puestos). */
export interface PuestoEstado {
  code: string
  name: string
  color: string | null
  estado: 'incidencia' | 'en_curso' | 'parado' | 'pendiente' | 'libre'
  orden: {
    id: string
    numero: string
    cliente: string | null
    linea_id: string
    piezas: number
    objetivo: number
    bobina: string | null
  } | null
  ultima_actividad: {
    accion: string
    timestamp: string
    operario: string | null
  } | null
  incidencias_abiertas: { id: string; tipo: string; descripcion: string }[]
}

/** Coste real vs estimado de una orden (GET /supervisor/costes-ordenes). */
export interface CosteOrden {
  order_id: string
  numero: string
  cliente: string | null
  estado: string
  piezas: number
  objetivo: number
  real_material: number
  mano_obra: number
  real_total: number
  estimado_material: number | null
  desviacion_material: number | null
  real_material_comparable: number
  scrap_kg: number
  scrap_coste: number
}

export interface PlanCheck {
  id: string
  name: string
  tipo: string
  tool_id: string | null
  nominal_value: number | null
  tolerance_plus: number | null
  tolerance_minus: number | null
  is_critical: boolean
}

/** Periodo natural de la vista Costes (ventana de planta, TZ_PLANTA). */
export type PeriodoPanel = 'semana' | 'mes' | 'trimestre'

/** €/kg del periodo con su comparativa y el objetivo de empresa, si existe. */
export interface PanelCostesCosteKg {
  valor: number
  periodo_anterior: number
  objetivo: number | null
  material: number
  transformacion: number
}

export interface PanelCostesFamilia {
  familia: string
  etiqueta: string
  kg: number
  material: number
  transformacion: number
  merma_pct: number
  ordenes: number
}

export interface PanelCostesReparto {
  clave: string
  etiqueta: string
  euros: number
  pct: number
}

export interface PanelCostesParadas {
  total: number
  por_tipo: { tipo: string; etiqueta: string; euros: number }[]
  horas: number
}

export interface PanelCostesTendencia {
  semana: string
  valor: number
}

export interface PanelCostesOrden {
  order_id: string
  numero: string
  producto: string | null
  kg: number
  estimado: number | null
  real: number
  desv_euros: number | null
  desv_pct: number | null
  causa: string
}

/** Vista Costes del panel de mando (GET /supervisor/panel/costes).
 *  El cliente NO recalcula: muestra tal cual lo que devuelve el backend. */
export interface PanelCostes {
  periodo: PeriodoPanel
  desde: string
  hasta: string
  coste_kg: PanelCostesCosteKg
  coste_total: number
  kg_total: number
  lineas_metros_excluidas: number
  ordenes_completadas: number
  desviacion: { pct: number | null; euros: number | null; ordenes_con_estimado: number }
  chatarra: { euros: number; pct_material: number }
  por_familia: PanelCostesFamilia[]
  reparto: PanelCostesReparto[]
  coste_paradas: PanelCostesParadas
  tendencia: PanelCostesTendencia[]
  ordenes: PanelCostesOrden[]
}

export interface QualityModel {
  id: string
  code: string
  name: string
  material_code: string | null
  quality_plan: PlanCheck[]
}

export interface OrderItem {
  id: string
  numero: string
  estado: string
  cliente: string | null
  fecha_entrega: string | null
  workstation_id: string | null
}

export interface WorkstationItem {
  id: string
  code: string
  name: string
  color?: string
  group_id?: string | null
  is_active?: boolean
}

export interface OrderLineOut {
  id: string
  linea_numero: number
  product_id: string | null
  modelo_id: string | null
  workstation_id: string
  estado: string
  total_quantity: number
  produced_quantity: number
  material_id: string | null
  meters_per_piece: number | null
}

export interface OrderDetailOut {
  id: string
  numero: string
  estado: string
  cliente: string | null
  fecha_entrega: string | null
  notas: string | null
  lines: OrderLineOut[]
}

export interface OrderLineIn {
  workstation_id: string
  total_quantity: number
  linea_numero?: number
  product_id?: string
  modelo_id?: string
  material_id?: string
  meters_per_piece?: number
}

export interface OrderCreateIn {
  cliente?: string | null
  fecha_entrega?: string | null
  notas?: string | null
  estado_inicial?: 'draft' | 'active'
  lines: OrderLineIn[]
}

export interface ProductComponentOut {
  id: string
  manufacturing_model_id: string | null
  material_id: string | null
  quantity: number
  unit: string
  position: number
}

export interface ProductOut {
  id: string
  code: string
  name: string
  description: string | null
  is_active: boolean
  components: ProductComponentOut[]
}

export interface ProductComponentIn {
  manufacturing_model_id?: string
  material_id?: string
  quantity: number
  unit?: string
}

export interface ProductCreateIn {
  code: string
  name: string
  description?: string | null
  is_active?: boolean
  components?: ProductComponentIn[]
}

export interface QualityMeasurementOut {
  check_name: string
  value_entered: number | boolean | string
  is_passed: boolean
  nominal: number | null
  tol_plus: number | null
  tol_minus: number | null
}

export interface QualityRecordOut {
  id: string
  order_id: string | null
  workstation_id: string | null
  overall_status: string
  notes: string | null
  created_at: string
  operator: { id: string; name: string } | null
  measurements: QualityMeasurementOut[]
}

export interface TraceEvent {
  id: string
  action: string
  quantity: string
  timestamp: string
  metadata: Record<string, unknown> | null
  shift: string | null
  operator: { id: string; name: string } | null
}

// Admin types
export interface TenantOut {
  id: string
  name: string
  slug: string
  status: string
  is_active: boolean
  auth: Record<string, unknown>
  theme: Record<string, unknown>
  finances: Record<string, unknown>
  sequences_config: Record<string, unknown>
}

export interface UserOut {
  id: string
  email: string
  name: string
  role: string
  is_active: boolean
  employee_number: string | null
  default_workstation_code: string | null
  last_login_at: string | null
}

export interface SeqCfg {
  prefix: string
  padding: number
}

export interface SequencesOut {
  order: SeqCfg
  lot: SeqCfg
}

export interface WorkstationOut {
  id: string
  group_id: string | null
  code: string
  name: string
  color: string
  hourly_cost: number
  /** Ritmo nominal (piezas/hora): base del plan del turno. null = sin configurar. */
  piezas_hora_nominal?: number | null
  registration_method: string
  maintenance_interval_hours: number
  maintenance_pre_warning_hours: number
  last_maintenance_reset: string | null
  accumulated_hours: number
  is_active: boolean
}

/** Objetivos de planta de la empresa (los no configurados llegan con su valor por defecto). */
export interface Objetivos {
  oee: number
  disponibilidad: number
  rendimiento: number
  calidad: number
  chatarra_max_pct: number
}

/** Vista Turno del panel de mando (GET /supervisor/turno). */
export type EstadoPuestoTurno =
  | 'en_marcha'
  | 'sin_registrar'
  | 'parado'
  | 'preparado'
  | 'sin_orden'
export type EstadoOrdenTurno = 'retraso' | 'en_riesgo' | 'a_tiempo' | 'sin_ritmo' | 'sin_plazo'

export interface PanelTurno {
  turno: { codigo: 'A' | 'B' | 'C'; inicio: string; fin: string; transcurrido_min: number; duracion_min: number }
  piezas: number
  /** null = ningún puesto con orden tiene ritmo nominal: no hay plan. */
  plan_turno: number | null
  plan_ahora: number | null
  prevision_cierre: number | null
  serie: { minuto: number; piezas: number }[]
  eficiencia: {
    oee: number
    disponibilidad: number
    rendimiento: number
    calidad: number
    mas_resta: 'disponibilidad' | 'rendimiento' | 'calidad'
  } | null
  paradas: {
    minutos: number
    numero: number
    mayor: { puesto: string; motivo: string; descripcion: string; minutos: number; abierta: boolean } | null
  }
  chatarra: { kg: number; pct: number | null }
  objetivos: Objetivos
  puestos: {
    code: string
    name: string
    grupo: string | null
    estado: EstadoPuestoTurno
    motivo: string | null
    minutos: number | null
    ritmo_nominal: number | null
    orden: { numero: string; producto: string | null; piezas: number; objetivo: number } | null
  }[]
  ordenes: {
    numero: string
    producto: string | null
    puesto: string | null
    piezas: number
    objetivo: number
    entrega: string | null
    horas_faltan: number | null
    horas_quedan: number | null
    estado: EstadoOrdenTurno
  }[]
  pendientes: {
    urgencia: 'urgente' | 'hoy' | 'revisar'
    titulo: string
    detalle: string
    minutos: number | null
    accion: 'incidencia' | 'stock' | 'orden' | 'puesto'
    ref: string
  }[]
}

/** Vista Planta del panel de mando (GET /supervisor/planta). */
export type PeriodoPlanta = 'hoy' | 'semana' | '8semanas'

export interface FactoresEficiencia {
  oee: number
  disponibilidad: number
  rendimiento: number
  calidad: number
}

export interface PanelPlanta {
  periodo: PeriodoPlanta
  desde: string
  hasta: string
  piezas: number
  plan: number | null
  eficiencia: FactoresEficiencia | null
  paradas: {
    minutos: number
    numero: number
    media_min: number | null
    por_causa: { causa: string; minutos: number; pct: number | null }[]
  }
  chatarra_pct: number | null
  puestos: ({ puesto: string } & FactoresEficiencia)[]
  anterior: { eficiencia: number | null; piezas: number; paradas_min: number }
  entregas: { total: number; a_tiempo: number; tarde: string[] }
  tendencia: { semana: string; oee: number | null }[]
  ordenes: PanelTurno['ordenes']
  objetivos: Objetivos
}

export interface WorkstationGroupOut {
  id: string
  name: string
  color: string
}

export interface RoleOut {
  id: string
  role_key: string
  name: string
  permissions: string[]
  is_system: boolean
}

const BASE = '/api/v1'

/** Error de la API con su código HTTP (409: falta medir la bobina, etc.). */
export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = sessionStorage.getItem('kavana_token')
  const authHeader: Record<string, string> = token
    ? { Authorization: `Bearer ${token}` }
    : {}
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...authHeader,
      ...init?.headers,
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(body.detail ?? `Error ${res.status}`, res.status)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  login(email: string, password: string): Promise<LoginResponse> {
    return request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
  },

  /** Cierra la sesión. Con bobinas sin medir (409) la sesión sigue abierta. */
  async logout(): Promise<void> {
    try {
      await request<void>('/auth/logout', { method: 'POST', body: JSON.stringify({}) })
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) throw err
    }
    sessionStorage.removeItem('kavana_token')
  },

  listStock(): Promise<StockItemOut[]> {
    return request('/stock-items')
  },

  listMaterials(): Promise<MaterialOut[]> {
    return request('/stock-items/materials')
  },

  receiveCoil(body: ReceiveCoilRequest): Promise<StockItemOut> {
    return request('/stock-items', { method: 'POST', body: JSON.stringify(body) })
  },

  getEvents(tenantId: string): Promise<{ events: EventData[] }> {
    return request(`/events/${tenantId}`)
  },

  listIncidencias(): Promise<{ incidencias: IncidenciaItem[] }> {
    return request('/incidencias')
  },

  getOee(): Promise<OeeData> {
    return request('/supervisor/oee')
  },

  getKpis(): Promise<KpisData> {
    return request('/supervisor/kpis')
  },

  getCostesOrdenes(): Promise<CosteOrden[]> {
    return request('/supervisor/costes-ordenes')
  },

  /** Vista Costes del periodo (servicio panel_costes; el cliente no calcula). */
  getPanelCostes(periodo: PeriodoPanel = 'mes'): Promise<PanelCostes> {
    return request(`/supervisor/panel/costes?periodo=${periodo}`)
  },

  /** Descarga el panel de costes en CSV para Excel (con auth) como fichero. */
  async descargarPanelCostesCsv(periodo: PeriodoPanel = 'mes'): Promise<void> {
    const token = sessionStorage.getItem('kavana_token')
    const res = await fetch(`${BASE}/supervisor/panel/costes?periodo=${periodo}&formato=csv`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) throw new Error(`Error ${res.status}`)
    const nombre =
      res.headers.get('content-disposition')?.match(/filename="?([^";]+)"?/)?.[1] ??
      `panel-costes-${periodo}.csv`
    const url = URL.createObjectURL(await res.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = nombre
    a.click()
    URL.revokeObjectURL(url)
  },

  getPuestos(): Promise<PuestoEstado[]> {
    return request('/supervisor/puestos')
  },

  getObjetivos(): Promise<Objetivos> {
    return request('/supervisor/objetivos')
  },

  /** Solo administración; los objetivos no enviados conservan su valor. */
  putObjetivos(cambios: Partial<Objetivos>): Promise<Objetivos> {
    return request('/supervisor/objetivos', { method: 'PUT', body: JSON.stringify(cambios) })
  },

  getTurno(): Promise<PanelTurno> {
    return request('/supervisor/turno')
  },

  getPlanta(periodo: PeriodoPlanta): Promise<PanelPlanta> {
    return request(`/supervisor/planta?periodo=${periodo}`)
  },

  getAlertas(): Promise<AlertasData> {
    return request('/supervisor/alertas')
  },

  getInformeTurno(fecha: string, turno: string): Promise<InformeTurno> {
    return request(`/supervisor/informe-turno?fecha=${fecha}&turno=${turno}`)
  },

  /** Descarga el informe en CSV (con auth) y lo entrega como fichero. */
  async descargarInformeCsv(fecha: string, turno: string): Promise<void> {
    const token = sessionStorage.getItem('kavana_token')
    const res = await fetch(
      `${BASE}/supervisor/informe-turno?fecha=${fecha}&turno=${turno}&formato=csv`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} },
    )
    if (!res.ok) throw new Error(`Error ${res.status}`)
    const url = URL.createObjectURL(await res.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = `informe-turno-${fecha}-${turno}.csv`
    a.click()
    URL.revokeObjectURL(url)
  },

  listOrders(): Promise<OrderItem[]> {
    return request('/orders')
  },

  createOrder(data: OrderCreateIn): Promise<OrderDetailOut> {
    return request('/orders', { method: 'POST', body: JSON.stringify(data) })
  },

  updateOrder(orderId: string, data: { cliente?: string | null; fecha_entrega?: string | null; notas?: string | null }): Promise<OrderDetailOut> {
    return request(`/orders/${orderId}`, { method: 'PUT', body: JSON.stringify(data) })
  },

  transitionOrder(orderId: string, to: 'active' | 'completed' | 'cancelled'): Promise<OrderDetailOut> {
    return request(`/orders/${orderId}/transition`, { method: 'POST', body: JSON.stringify({ to }) })
  },

  deleteOrder(orderId: string): Promise<void> {
    return request<void>(`/orders/${orderId}`, { method: 'DELETE' })
  },

  listProducts(): Promise<ProductOut[]> {
    return request('/products')
  },

  createProduct(data: ProductCreateIn): Promise<ProductOut> {
    return request('/products', { method: 'POST', body: JSON.stringify(data) })
  },

  updateProduct(productId: string, data: Partial<ProductCreateIn>): Promise<ProductOut> {
    return request(`/products/${productId}`, { method: 'PUT', body: JSON.stringify(data) })
  },

  deleteProduct(productId: string): Promise<void> {
    return request<void>(`/products/${productId}`, { method: 'DELETE' })
  },

  getQualityRecords(limit = 20): Promise<{ success: boolean; records: QualityRecordOut[] }> {
    return request(`/quality/records?limit=${limit}`)
  },

  availableOrders(workstation?: string): Promise<OrderItem[]> {
    const q = workstation ? `?workstation=${encodeURIComponent(workstation)}` : ''
    return request(`/orders/available${q}`)
  },

  listWorkstations(): Promise<WorkstationItem[]> {
    return request('/admin/workstations')
  },

  getOrder(orderId: string): Promise<any> {
    return request(`/orders/${orderId}`)
  },

  getTrace(orderId: string): Promise<TraceEvent[]> {
    return request(`/trace/orders/${orderId}`)
  },

  getQualityModels(): Promise<QualityModel[]> {
    return request('/quality/models')
  },

  createQualityCheck(data: { order_id: string; workstation_id: string; manufacturing_model_id: string; stock_item_id: string; measurements: { check_name: string; value_entered: number | boolean | string }[] }): Promise<{ record: { overall_status: string } }> {
    return request('/quality/checks', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  createIncidencia(data: { descripcion: string; tipo: string; linea_id: string; foto_data_url?: string | null; photo_session_id?: string | null }): Promise<{ id: string }> {
    return request('/incidencias', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  createIncidenciaUploadSession(): Promise<{ sessionId: string; expiresAt: string }> {
    return request('/incidencias/upload-session', {
      method: 'POST',
    })
  },

  getIncidenciaUploadSession(sessionId: string): Promise<{ sessionId: string; status: string; expires_at: string; has_photo: boolean; photo_data_url?: string | null }> {
    return request(`/incidencias/upload-session/${sessionId}`)
  },

  scanCoil(coil_id?: string, lote?: string): Promise<{ id: string; lote: string; coil_id: string | null; peso_kg: number; ancho_mm: number | null; espesor_mm: number | null; material_code: string | null; material_name: string | null; estado: string; ubicacion: string | null; modo: string } | null> {
    return request(`/stock-items/scan?coil_id=${coil_id ?? ''}&lote=${lote ?? ''}`)
  },

  recordProduction(data: { order_id: string; line_id: string; incremental_quantity: number; hours_worked?: number; observaciones?: string }): Promise<{ incremental_quantity: number; consumed_amount: number; consumption_unit: string; calculation_method: string }> {
    return request('/production/record', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  finBobina(data: { stock_item_id: string; order_id: string; line_id: string; radio_mm: number }): Promise<{ msg: string; peso_restante_kg: number; merma_kg: number; merma_cost: number }> {
    return request('/stock-items/fin-bobina', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /** Bobinas que el operario puede vincular sin saberse el código. */
  bobinasDisponibles(lineId: string): Promise<Array<{ id: string; lote: string; coil_id: string | null; peso_kg: number; ancho_mm: number | null; espesor_mm: number | null; material_code: string | null; material_name: string | null; estado: string; ubicacion: string | null; modo: string; en_puesto: boolean }>> {
    return request(`/stock-items/disponibles?line_id=${encodeURIComponent(lineId)}`)
  },

  getMedicionesPendientes(): Promise<MedicionPendiente[]> {
    return request('/stock-items/mediciones-pendientes')
  },

  /** Cierre de turno: mide el radio y deja la bobina montada para el relevo. */
  medirBobina(data: { stock_item_id: string; order_id: string; line_id: string; radio_mm: number }): Promise<{ msg: string; chatarra_kg: number; chatarra_coste: number; peso_restante_kg: number }> {
    return request('/stock-items/medir', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  /** Modo manual: alta de bobina con los datos de la etiqueta del proveedor. */
  altaManualBobina(data: { material_id: string; peso_kg: number; lote: string; coil_id?: string; width_mm?: number; thickness_mm?: number; puesto?: string }): Promise<{ id: string; lote: string; coil_id: string | null; peso_kg: number; ancho_mm: number | null; espesor_mm: number | null; material_code: string | null; material_name: string | null; estado: string; ubicacion: string | null; modo: string }> {
    return request('/stock-items/alta-manual', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  retirarPico(data: { stock_item_id: string }): Promise<{ msg: string }> {
    return request('/stock-items/retirar', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  linkCoil(data: { stock_item_id: string; order_id: string; line_id: string }): Promise<{ success: boolean; coil_weight: number; order: string }> {
    return request('/stock-items/link', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  unlinkCoil(data: { stock_item_id: string; order_id: string; line_id: string }): Promise<{ success: boolean; refunded_qty: number; refunded_cost: number }> {
    return request('/stock-items/unlink', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  closeShift(): Promise<{ success: boolean; status: string; total_hours: number; turno: string; logout_time: string }> {
    return request('/auth/close-shift', {
      method: 'POST',
    });
  },

  // Admin endpoints
  getTenant(): Promise<TenantOut> {
    return request('/admin/tenant')
  },

  updateTenant(data: Partial<TenantOut>): Promise<TenantOut> {
    return request('/admin/tenant', {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  },

  getUsers(): Promise<UserOut[]> {
    return request('/admin/users')
  },

  createUser(data: Omit<UserOut, 'id' | 'is_active' | 'last_login_at'> & { password: string }): Promise<UserOut> {
    return request('/admin/users', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  updateUser(id: string, data: Partial<UserOut>): Promise<UserOut> {
    return request(`/admin/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  },

  deleteUser(id: string): Promise<void> {
    return request<void>(`/admin/users/${id}`, {
      method: 'DELETE',
    })
  },

  getSequences(): Promise<SequencesOut> {
    return request('/admin/sequences')
  },

  updateSequences(data: SequencesOut): Promise<SequencesOut> {
    return request('/admin/sequences', {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  },

  getWorkstations(): Promise<WorkstationOut[]> {
    return request('/admin/workstations')
  },

  createWorkstation(data: Omit<WorkstationOut, 'id'>): Promise<WorkstationOut> {
    return request('/admin/workstations', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  updateWorkstation(id: string, data: Partial<WorkstationOut>): Promise<WorkstationOut> {
    return request(`/admin/workstations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  },

  deleteWorkstation(id: string): Promise<void> {
    return request<void>(`/admin/workstations/${id}`, {
      method: 'DELETE',
    })
  },

  updateIncidencia(id: string, data: Partial<IncidenciaItem & { resolucion_tipo?: string | null; resolucion_descripcion?: string | null; tiempo_parada_min?: number | null; coste?: number | null }>): Promise<IncidenciaItem> {
    return request(`/incidencias/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  },

  getNextOrder(): Promise<string> {
    return request<{ next: string }>('/admin/sequences/next/order')
      .then(r => r.next)
  },

  getNextLot(): Promise<string> {
    return request<{ next: string }>('/admin/sequences/next/lot')
      .then(r => r.next)
  },

  getWorkstationGroups(): Promise<WorkstationGroupOut[]> {
    return request('/admin/workstations/groups')
  },

  getRoles(): Promise<RoleOut[]> {
    return request('/admin/roles')
  },

  updateRole(id: string, data: Partial<RoleOut>): Promise<RoleOut> {
    return request(`/admin/roles/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  },
}

/** Hook ligero de autenticación: estado del turno en sessionStorage. */
export function getToken(): string | null {
  return sessionStorage.getItem('kavana_token')
}

export function isLoggedIn(): boolean {
  return getToken() !== null
}

export interface JwtPayload {
  sub: string
  tenant_id: string
  role: string
  /** Tenant de demostración: la interfaz lo marca como DATOS DE DEMO. */
  demo?: boolean
  exp: number
}

/** Decodifica el payload del JWT sin verificar firma (solo lectura local). */
export function getJwtPayload(): JwtPayload | null {
  const token = getToken()
  if (!token) return null
  try {
    const part = token.split('.')[1]
    const json = atob(part.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(decodeURIComponent(escape(json))) as JwtPayload
  } catch {
    return null
  }
}

export function getTenantId(): string | null {
  return getJwtPayload()?.tenant_id ?? null
}
