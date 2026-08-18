/** Roles y acceso por panel (Fase 6). Matriz espejo del backend.

 * operator → /operario (escaneo, vincular, producir, autocontrol, incidencias)
 * materials → /materias-primas (recepción e inventario)
 * supervisor → /supervisor (OEE, KPIs, trazabilidad, incidencias)
 * admin → hereda supervisor (y puede operar)
 */

export type Role = 'operator' | 'materials' | 'supervisor' | 'admin'

export const ROLE_LABELS: Record<Role, string> = {
  operator: 'Operario',
  materials: 'Materias Primas',
  supervisor: 'Supervisor',
  admin: 'Admin',
}

export const HOME_BY_ROLE: Record<Role, string> = {
  operator: '/operario',
  materials: '/materias-primas',
  supervisor: '/supervisor',
  admin: '/admin',
}

export interface NavItem {
  to: string
  label: string
  icon: string
}

export const ALL_NAV: NavItem[] = [
  { to: '/operario', label: 'Operario', icon: '🔧' },
  { to: '/materias-primas', label: 'Materias Primas', icon: '📦' },
  { to: '/supervisor', label: 'Supervisor', icon: '📊' },
  { to: '/admin', label: 'Admin', icon: '⚙️' },
]

/** Paneles permitidos por rol (las páginas también validan backend). */
const ACCESS: Record<Role, string[]> = {
  operator: ['/operario'],
  materials: ['/materias-primas'],
  supervisor: ['/operario', '/materias-primas', '/supervisor'],
  admin: ['/operario', '/materias-primas', '/supervisor', '/admin'],
}

export function canAccess(role: Role, path: string): boolean {
  return ACCESS[role]?.includes(path) ?? false
}

export function navForRole(role: Role | null): NavItem[] {
  if (!role) return []
  return ALL_NAV.filter((item) => canAccess(role, item.to))
}
