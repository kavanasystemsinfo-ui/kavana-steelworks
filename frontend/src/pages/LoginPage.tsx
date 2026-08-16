import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getJwtPayload } from '../lib/api'
import { HOME_BY_ROLE, type Role } from '../lib/roles'

const DEMO_ACCOUNTS: { email: string; label: string; role: Role }[] = [
  { email: 'operario@demo.local', label: 'Operario', role: 'operator' },
  { email: 'supervisor@demo.local', label: 'Supervisor', role: 'supervisor' },
  { email: 'materias@demo.local', label: 'Materias Primas', role: 'materials' },
  { email: 'admin@demo.local', label: 'Admin', role: 'admin' },
]

const DEMO_PASSWORD = 'kavana'

/** Login industrial: tarjeta única, un solo campo a la vez (no abrumar).
 *  Fase 6: redirige al panel según el rol del token y muestra las cuentas
 *  demo con su contraseña para que cualquiera pueda entrar fácil.
 */
export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const goHomeByRole = () => {
    const role = getJwtPayload()?.role as Role | undefined
    navigate(role && HOME_BY_ROLE[role] ? HOME_BY_ROLE[role] : '/operario', {
      replace: true,
    })
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

  const fillDemo = (demoEmail: string) => {
    setEmail(demoEmail)
    setPassword(DEMO_PASSWORD)
    setError('')
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
        {error && (
          <p className="text-kavana-danger text-sm border border-kavana-danger/40 rounded-sm p-2">
            {error}
          </p>
        )}
        <label className="block">
          <span className="label-industrial text-xs text-kavana-text-dim">
            Usuario
          </span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full bg-kavana-dark border border-kavana-border rounded-sm px-3 py-2 min-h-[48px] text-kavana-text focus:border-kavana-orange outline-none"
            required
          />
        </label>
        <label className="block">
          <span className="label-industrial text-xs text-kavana-text-dim">
            Contraseña
          </span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full bg-kavana-dark border border-kavana-border rounded-sm px-3 py-2 min-h-[48px] text-kavana-text focus:border-kavana-orange outline-none"
            required
          />
        </label>
        <button
          type="submit"
          className="w-full min-h-[52px] bg-kavana-orange text-black font-bold uppercase tracking-widest rounded-sm hover:opacity-90 transition-opacity"
        >
          Entrar
        </button>

        <div className="border-t border-kavana-border pt-3">
          <p className="label-industrial text-xs text-kavana-text-dim mb-2">
            Acceso demo · contraseña: {DEMO_PASSWORD}
          </p>
          <ul className="space-y-1">
            {DEMO_ACCOUNTS.map((acc) => (
              <li key={acc.email}>
                <button
                  type="button"
                  onClick={() => fillDemo(acc.email)}
                  className="w-full text-left text-xs px-2 py-1.5 rounded-sm border border-kavana-border/50 text-kavana-text-dim hover:text-kavana-text hover:border-kavana-orange transition-colors"
                >
                  <span className="font-bold">{acc.label}</span>
                  <span className="ml-2">{acc.email}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </form>
    </div>
  )
}
