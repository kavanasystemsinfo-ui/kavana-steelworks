import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { api, getJwtPayload } from '../../lib/api'
import { estadoCola } from '../../lib/colaProduccion'
import { navForRole, type Role } from '../../lib/roles'
import { TOUR_DE_VISTA, TOUR_INICIAL, crearTours, tourDelOperario } from '../../lib/tours'
import { useTour } from '../useTour'

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

  const [aviso, setAviso] = useState('')
  // Partes sin enviar en esta tablet al pulsar Salir (null: sin aviso abierto)
  const [partesAlSalir, setPartesAlSalir] = useState<number | null>(null)

  // Tour guiado: uno por rol (y por pantalla en el operario y por pestaña en el supervisor).
  // Se abre solo la primera vez que un visitante de la demo entra con cada rol, y se repite
  // con el botón de la barra. La pantalla en la que está se lee de la URL en el momento de
  // pulsar: el operario la cambia con replaceState y el router no se entera.
  const claveVisto = `steelworks-tour-visto-${role ?? 'sin-rol'}`
  const tour = useTour(crearTours({ ir: (ruta) => navigate(ruta) }), claveVisto)
  const claveTourAhora = (): string | null => {
    if (!role) return null
    const params = new URLSearchParams(window.location.search)
    if (role === 'supervisor') return TOUR_DE_VISTA[params.get('vista') ?? 'turno'] ?? 'turno'
    if (role === 'operator') return tourDelOperario(params)
    return TOUR_INICIAL[role]
  }
  useEffect(() => {
    if (!role || !getJwtPayload()?.demo) return
    let visto = false
    try {
      visto = localStorage.getItem(claveVisto) === 'true'
    } catch {
      /* sin almacenamiento: se abre */
    }
    if (visto) return
    const retraso = setTimeout(() => tour.start(claveTourAhora() ?? TOUR_INICIAL[role]), 1200)
    return () => clearTimeout(retraso)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role])

  const pulsarSalir = () => {
    const cola = estadoCola(getJwtPayload()?.sub ?? null)
    const sinEnviar = cola.pendientesMios + cola.fallidosMios
    if (sinEnviar > 0) {
      setPartesAlSalir(sinEnviar)
      return
    }
    handleLogout()
  }

  const handleLogout = async () => {
    setPartesAlSalir(null)
    try {
      await api.logout()
    } catch (err) {
      // 409: el operario tiene una bobina sin medir; la sesión sigue abierta
      setAviso(err instanceof Error ? err.message : 'No se pudo cerrar la sesión')
      return
    }
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
            {getJwtPayload()?.demo && (
              <span
                className="label-industrial text-[10px] border border-kavana-warn text-kavana-warn rounded-sm px-2 py-0.5"
                title="Empresa de demostración: datos ficticios generados por un simulador"
              >
                Datos de demo
              </span>
            )}
            {role && (
              <span className="text-xs uppercase tracking-wider text-kavana-text-dim">
                {role}
              </span>
            )}
            {role && (
              <button
                type="button"
                onClick={() => {
                  const clave = claveTourAhora()
                  if (clave) tour.start(clave)
                }}
                title="Tour guiado de esta pantalla"
                aria-label="Tour guiado"
                className="px-3 py-2 text-sm uppercase tracking-wider rounded-sm border border-kavana-orange text-kavana-orange hover:bg-kavana-orange hover:text-black transition-colors"
              >
                🧭<span className="hidden sm:inline"> Tour</span>
              </button>
            )}
            <button
              onClick={pulsarSalir}
              className="px-3 py-2 text-sm uppercase tracking-wider rounded-sm border border-kavana-border text-kavana-text-dim hover:text-kavana-text hover:border-kavana-orange transition-colors"
            >
              Salir
            </button>
          </div>
        </nav>
      </header>
      {partesAlSalir !== null && (
        <div
          role="alertdialog"
          aria-label="Partes sin enviar"
          className="border-b border-kavana-warn bg-kavana-surface px-4 py-3 text-sm text-kavana-warn flex flex-wrap items-center justify-between gap-3"
        >
          <span>
            {`Quedan ${partesAlSalir} ${partesAlSalir === 1 ? 'parte' : 'partes'} sin enviar en esta tablet. Se conservan y podrás enviarlos cuando vuelvas a entrar.`}
          </span>
          <span className="flex gap-2">
            <button
              type="button"
              onClick={() => setPartesAlSalir(null)}
              className="min-h-[44px] px-3 rounded-sm border border-kavana-border text-kavana-text font-semibold"
            >
              Seguir aquí
            </button>
            <button
              type="button"
              onClick={handleLogout}
              className="min-h-[44px] px-3 rounded-sm border border-kavana-warn text-kavana-warn font-semibold"
            >
              Salir igualmente
            </button>
          </span>
        </div>
      )}
      {aviso && (
        <div
          role="alert"
          className="border-b border-kavana-warn bg-kavana-surface px-4 py-2 text-sm text-kavana-warn flex items-center justify-between gap-3"
        >
          <span>{aviso} Hazlo en «Cerrar jornada» del panel de operario.</span>
          <button type="button" className="underline" onClick={() => setAviso('')}>
            Entendido
          </button>
        </div>
      )}
      <main className="p-4">
        <Outlet />
      </main>
      <tour.TourComponent {...tour.tourProps} />
    </div>
  )
}
