import { useEffect, useState } from 'react'

interface OeeData {
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

interface KpisData {
  orders_total: number
  orders_active: number
  orders_completed: number
  estimated_cost: number
  real_cost: number
  cost_variance: number
  cost_efficiency: number
  material_variance: number
  material_efficiency: number
  scrap_rate: number
}

/** Panel de Supervisor: "planta en un vistazo" (filosofía Jorge).
 *  OEE y KPIs reales del backend (spec 03), polling cada 10 s.
 */
export function SupervisorPage() {
  const [oee, setOee] = useState<OeeData | null>(null)
  const [kpis, setKpis] = useState<KpisData | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const cargar = () => {
      fetch('/api/v1/supervisor/oee')
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`OEE ${r.status}`))))
        .then(setOee)
        .catch((e) => setError(e instanceof Error ? e.message : 'Error OEE'))
      fetch('/api/v1/supervisor/kpis')
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`KPIs ${r.status}`))))
        .then(setKpis)
        .catch((e) => setError(e instanceof Error ? e.message : 'Error KPIs'))
    }
    cargar()
    const timer = setInterval(cargar, 10000)
    return () => clearInterval(timer)
  }, [])

  const fmtEur = (n: number | undefined) =>
    n === undefined ? '--' : `${n.toLocaleString('es-ES')} €`
  const fmtPct = (n: number | undefined) =>
    n === undefined ? '--' : `${n.toLocaleString('es-ES')} %`

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      <div className="step-guide">
        <p className="label-industrial text-xs text-kavana-text-dim">
          Planta en un vistazo
        </p>
        <p className="text-lg font-bold">Turno actual</p>
      </div>

      {error && (
        <p className="text-kavana-danger text-sm border border-kavana-danger/40 rounded-sm p-2">
          {error}
        </p>
      )}

      {/* OEE principal */}
      <div className="bg-kavana-surface border border-kavana-border rounded-sm p-6 flex items-center justify-between">
        <div>
          <p className="label-industrial text-xs text-kavana-text-dim">OEE global</p>
          <p className="mono-data text-6xl mt-1 text-kavana-orange">
            {oee ? oee.oee.toLocaleString('es-ES') : '--'}
            <span className="text-2xl text-kavana-text-dim">%</span>
          </p>
        </div>
        <div className="grid grid-cols-3 gap-6 text-right">
          <div>
            <p className="label-industrial text-[10px] text-kavana-text-dim">
              Disponibilidad
            </p>
            <p className="mono-data text-2xl">
              {oee ? oee.availability.toLocaleString('es-ES') : '--'}
              <span className="text-sm text-kavana-text-dim">%</span>
            </p>
          </div>
          <div>
            <p className="label-industrial text-[10px] text-kavana-text-dim">
              Rendimiento
            </p>
            <p className="mono-data text-2xl">
              {oee ? oee.performance.toLocaleString('es-ES') : '--'}
              <span className="text-sm text-kavana-text-dim">%</span>
            </p>
          </div>
          <div>
            <p className="label-industrial text-[10px] text-kavana-text-dim">
              Calidad
            </p>
            <p className="mono-data text-2xl">
              {oee ? oee.quality.toLocaleString('es-ES') : '--'}
              <span className="text-sm text-kavana-text-dim">%</span>
            </p>
          </div>
        </div>
      </div>

      {/* KPIs del turno */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label="Producción turno" value={oee ? oee.raw.total_pieces.toLocaleString('es-ES') : '--'} unit="uds" />
        <Kpi label="Merma" value={oee ? oee.raw.scrap_kg.toLocaleString('es-ES') : '--'} unit="kg" />
        <Kpi label="Coste real vs est." value={fmtEur(kpis?.cost_variance)} unit="€" />
        <Kpi label="Eficiencia coste" value={fmtPct(kpis?.cost_efficiency)} unit="" />
      </div>

      {/* Detalle de órdenes */}
      <div className="bg-kavana-surface border border-kavana-border rounded-sm p-4 space-y-2">
        <p className="label-industrial text-xs text-kavana-text-dim">Órdenes</p>
        {kpis ? (
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div>
              <p className="text-kavana-text-dim">Activas</p>
              <p className="mono-data text-xl">{kpis.orders_active}</p>
            </div>
            <div>
              <p className="text-kavana-text-dim">Completadas</p>
              <p className="mono-data text-xl">{kpis.orders_completed}</p>
            </div>
            <div>
              <p className="text-kavana-text-dim">Tasa de merma</p>
              <p className="mono-data text-xl">{fmtPct(kpis.scrap_rate)}</p>
            </div>
          </div>
        ) : (
          <p className="text-kavana-text-dim text-sm">
            Cargando datos del turno...
          </p>
        )}
      </div>
    </div>
  )
}

function Kpi({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="bg-kavana-surface border border-kavana-border rounded-sm p-4">
      <p className="label-industrial text-xs text-kavana-text-dim">{label}</p>
      <p className="mono-data text-3xl mt-1">
        {value}
        <span className="text-base text-kavana-text-dim">{unit}</span>
      </p>
    </div>
  )
}
