import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

/** Login industrial: tarjeta única, un solo campo a la vez (no abrumar). */
export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? 'Credenciales incorrectas')
      }
      const data = await res.json()
      sessionStorage.setItem('kavana_token', data.access_token)
      navigate('/operario')
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
      </form>
    </div>
  )
}
