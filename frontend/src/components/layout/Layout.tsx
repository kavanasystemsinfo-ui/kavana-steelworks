import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { api, getJwtPayload } from '../../lib/api'
import { navForRole, type Role } from '../../lib/roles'

function currentRole(): Role | null {
  const payload = getJwtPayload()
  return (payload?.role as Role) ?? null
}

/** Layout industrial: barra superior fina, contenido a pantalla completa.
 *  Diseño "no abrumar": solo navegación del rol, el contenido manda.
 *  Fase 6: cada rol ve solo sus paneles y puede salir (logout).
 */
export function Layout() {
  const navigate = useNavigate()
  const role = currentRole()
  const navItems = navForRole(role)

  const handleLogout = async () => {
    try {
      await api.logout()
    } catch {
      // el token se limpia igual aunque el servidor no responda
    }
    sessionStorage.removeItem('kavana_token')
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen bg-kavana-dark text-kavana-text">
      <header className="border-b border-kavana-border bg-kavana-surface">
        <nav className="flex items-center gap-6 px-4 h-14">
          <span className="label-industrial text-kavana-orange text-sm">
            KAVANA Steelworks
          </span>
          <div className="flex gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `px-3 py-2 text-sm uppercase tracking-wider rounded-sm transition-colors ${
                    isActive
                      ? 'bg-kavana-orange text-black font-bold'
                      : 'text-kavana-text-dim hover:text-kavana-text'
                  }`
                }
              >
                {item.icon} {item.label}
              </NavLink>
            ))}
          </div>
          <div className="ml-auto flex items-center gap-3">
            {role && (
              <span className="text-xs uppercase tracking-wider text-kavana-text-dim">
                {role}
              </span>
            )}
            <button
              onClick={handleLogout}
              className="px-3 py-2 text-sm uppercase tracking-wider rounded-sm border border-kavana-border text-kavana-text-dim hover:text-kavana-text hover:border-kavana-orange transition-colors"
            >
              Salir
            </button>
          </div>
        </nav>
      </header>
      <main className="p-4">
        <Outlet />
      </main>
    </div>
  )
}
