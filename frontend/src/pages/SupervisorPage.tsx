/** Panel de Supervisor: filosofía "un vistazo".
 *  Fase 3 inicial: KPIs clave en tarjetas (OEE, merma, coste).
 *  Se conectará al backend en la Fase 3 (endpoints OEE/KPIs de la spec 03).
 */
const kpis = [
  { label: 'OEE', value: '--', unit: '%' },
  { label: 'Producción turno', value: '--', unit: 'uds' },
  { label: 'Merma', value: '--', unit: 'kg' },
  { label: 'Coste real vs est.', value: '--', unit: '€' },
]

export function SupervisorPage() {
  return (
    <div className="max-w-5xl mx-auto space-y-4">
      <div className="step-guide">
        <p className="label-industrial text-xs text-kavana-text-dim">
          Planta en un vistazo
        </p>
        <p className="text-lg font-bold">Turno actual</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {kpis.map((kpi) => (
          <div
            key={kpi.label}
            className="bg-kavana-surface border border-kavana-border rounded-sm p-4"
          >
            <p className="label-industrial text-xs text-kavana-text-dim">
              {kpi.label}
            </p>
            <p className="mono-data text-3xl mt-1">
              {kpi.value}
              <span className="text-base text-kavana-text-dim">{kpi.unit}</span>
            </p>
          </div>
        ))}
      </div>

      <div className="bg-kavana-surface border border-kavana-border rounded-sm p-4">
        <p className="label-industrial text-xs text-kavana-text-dim">
          Órdenes activas
        </p>
        <p className="mt-2 text-kavana-text-dim">
          Pendiente de conectar con la API (spec 02, órdenes de producción).
        </p>
      </div>
    </div>
  )
}
