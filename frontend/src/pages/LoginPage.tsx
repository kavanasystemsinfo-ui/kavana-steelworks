import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getJwtPayload, ApiError } from '../lib/api'
import { HOME_BY_ROLE, type Role } from '../lib/roles'

const DEMO_ROLES = [
  { key: 'operator', label: 'Operario', description: 'Registra producción en la línea' },
  { key: 'supervisor', label: 'Supervisor', description: 'Ve la planta entera, OEE y paradas' },
  { key: 'materials', label: 'Materias Primas', description: 'Recibe bobinas, gestiona stock y calidad' },
  { key: 'admin', label: 'Admin', description: 'Configura puestos, usuarios y catálogos' },
] as const

type DemoRoleKey = typeof DEMO_ROLES[number]['key']

/** Login industrial: botones de rol para demo, formulario plegable para cuentas propias. */
export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [showCredentials, setShowCredentials] = useState(false)
  const [demoLoggingIn, setDemoLoggingIn] = useState<string | null>(null)
  const navigate = useNavigate()

  const goHomeByRole = () => {
    const role = getJwtPayload()?.role as Role | undefined
    navigate(role && HOME_BY_ROLE[role] ? HOME_BY_ROLE[role] : '/operario', {
      replace: true,
    })
  }

  // Auto demo login from query param ?demo=<role>
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const demoRole = params.get('demo')
    if (demoRole && DEMO_ROLES.some(r => r.key === demoRole)) {
      handleDemoLogin(demoRole as DemoRoleKey)
      window.history.replaceState({}, document.title, window.location.pathname)
    }
  }, [])

  const handleDemoLogin = async (role: DemoRoleKey) => {
    setError('')
    setDemoLoggingIn(role)

    try {
      const data = await api.demoLogin(role)
      sessionStorage.setItem('kavana_token', data.access_token)
      goHomeByRole()
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 404) {
          setError('Acceso demo desactivado. Contacta con el administrador.')
        } else if (err.status === 400) {
          setError('Rol no permitido para demo.')
        } else if (err.status === 429) {
          setError('Demasiados intentos. Espera un momento.')
        } else {
          setError(err.message)
        }
      } else {
        setError(err instanceof Error ? err.message : 'Error de conexión')
      }
    } finally {
      setDemoLoggingIn(null)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      const data = await api.login(email, password)
      sessionStorage.setItem('kavana_token', data.access_token)
      goHomeByRole()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error de conexión')
    }
  }

  return (
    <div className="min-h-screen bg-kavana-dark flex items-center justify-center p-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm bg-kavana-surface border border-kavana-border rounded-sm p-6 space-y-4"
      >
        <h1 className="label-industrial text-kavana-orange text-lg">
          KAVANA Steelworks
        </h1>
        <p className="text-kavana-text-dim text-sm">
          MES/MOM para el sector metalúrgico
        </p>

        {/* Demo role buttons */}
        <div className="space-y-3 mb-6">
          <p className="label-industrial text-xs text-kavana-text-dim text-center">
            Acceso rápido a la demo (sin credenciales)
          </p>
          <div className="space-y-2" role="group" aria-label="Roles de demo">
            {DEMO_ROLES.map(({ key, label, description }) => (
              <button
                key={key}
                type="button"
                disabled={demoLoggingIn === key}
                onClick={() => handleDemoLogin(key)}
                className="w-full text-left rounded-sm p-4 border transition-all active:scale-[0.99] flex items-center gap-3 bg-kavana-dark/50 border-kavana-border hover:bg-kavana-dark hover:border-kavana-orange text-kavana-text disabled:opacity-50 disabled:cursor-not-allowed"
                aria-busy={demoLoggingIn === key}
              >
                <span className="font-bold text-base text-kavana-text">{label}</span>
                <span className="text-sm text-kavana-text-dim">{description}</span>
                {demoLoggingIn === key && (
                  <span className="ml-auto animate-spin h-5 w-5 border-2 border-kavana-orange border-t-transparent rounded-full" aria-hidden="true" />
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Divider */}
        <div className="relative mb-6 text-kavana-text-dim">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-kavana-border" />
          </div>
          <div className="relative flex justify-center text-xs">
            <span className="bg-kavana-surface px-2">O</span>
          </div>
        </div>

        {/* Foldable credentials form */}
        <div className="space-y-5">
          <button
            type="button"
            onClick={() => setShowCredentials(!showCredentials)}
            className="w-full flex items-center justify-between font-medium text-sm rounded-sm py-2 px-3 transition-colors text-kavana-text-dim hover:text-kavana-text hover:bg-kavana-dark/50"
            aria-expanded={showCredentials}
          >
            <span>Tengo cuenta propia</span>
            <svg
              className={`h-5 w-5 transition-transform text-kavana-text-dim ${showCredentials ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {showCredentials && (
            <div className="space-y-4 animate-slide-down">
              {error && (
                <p className="text-kavana-danger text-sm border border-kavana-danger/40 rounded-sm p-2">
                  {error}
                </p>
              )}
              <label className="block">
                <span className="label-industrial text-xs text-kavana-text-dim" id="label-email">Usuario</span>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="mt-1 w-full bg-kavana-dark border border-kavana-border rounded-sm px-3 py-2 min-h-[48px] text-kavana-text focus:border-kavana-orange outline-none"
                  required
                  placeholder="usuario@empresa.com"
                  aria-labelledby="label-email"
                />
              </label>
              <label className="block">
                <span className="label-industrial text-xs text-kavana-text-dim" id="label-password">Contraseña</span>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="mt-1 w-full bg-kavana-dark border border-kavana-border rounded-sm px-3 py-2 min-h-[48px] text-kavana-text focus:border-kavana-orange outline-none"
                  required
                  placeholder="••••••••"
                  aria-labelledby="label-password"
                />
              </label>
              <button
                type="submit"
                className="w-full min-h-[52px] bg-kavana-orange text-black font-bold uppercase tracking-widest rounded-sm hover:opacity-90 transition-opacity"
              >
                Entrar
              </button>
            </div>
          )}
        </div>
      </form>
    </div>
  )
}