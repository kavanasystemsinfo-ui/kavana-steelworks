import { NavLink, Outlet } from 'react-router-dom'

const navItems = [
  { to: '/operario', label: 'Operario', icon: '🔧' },
  { to: '/materias-primas', label: 'Materias Primas', icon: '📦' },
  { to: '/supervisor', label: 'Supervisor', icon: '📊' },
]

/** Layout industrial: barra superior fina, contenido a pantalla completa.
 *  Diseño "no abrumar": solo navegación esencial, el contenido manda.
 */
export function Layout() {
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
        </nav>
      </header>
      <main className="p-4">
        <Outlet />
      </main>
    </div>
  )
}
