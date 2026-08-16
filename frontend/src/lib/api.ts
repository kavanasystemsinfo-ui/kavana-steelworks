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
}

const BASE = '/api/v1'

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
    throw new Error(body.detail ?? `Error ${res.status}`)
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

  logout(): Promise<void> {
    return request<void>('/auth/logout', { method: 'POST', body: JSON.stringify({}) }).finally(
      () => sessionStorage.removeItem('kavana_token'),
    )
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
