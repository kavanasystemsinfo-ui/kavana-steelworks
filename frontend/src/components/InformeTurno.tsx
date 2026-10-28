import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { InformeTurno as InformeTurnoData } from '../lib/api'
import { turnoActual } from '../lib/tiempo'

const fmt = (n: number, dec = 0) => n.toLocaleString('es-ES', { maximumFractionDigits: dec })

/** Informe de turno (adopción de "Reports" del legacy): fecha + turno A/B/C,
 *  tabla por puesto, descarga CSV para Excel e impresión (guardar como PDF).
 */
export function InformeTurno() {
  const inicial = turnoActual()
  const [fecha, setFecha] = useState(inicial.fecha)
  const [turno, setTurno] = useState<string>(inicial.turno)
  const [informe, setInforme] = useState<InformeTurnoData | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setInforme(null)
    setError('')
    api.getInformeTurno(fecha, turno)
      .then(setInforme)
      .catch((e) => setError(e instanceof Error ? e.message : 'No se pudo cargar el informe'))
  }, [fecha, turno])

  const descargar = () => {
    api.descargarInformeCsv(fecha, turno).catch(() => setError('No se pudo descargar el CSV'))
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <label htmlFor="informe-fecha" className="text-kavana-text-dim">Fecha</label>
        <input
          id="informe-fecha"
          type="date"
          className="bg-kavana-surface border border-kavana-border rounded-sm px-2 py-1"
          value={fecha}
          onChange={(e) => setFecha(e.target.value)}
        />
        <label htmlFor="informe-turno" className="text-kavana-text-dim">Turno</label>
        <select
          id="informe-turno"
          className="bg-kavana-surface border border-kavana-border rounded-sm px-2 py-1"
          value={turno}
          onChange={(e) => setTurno(e.target.value)}
        >
          <option value="A">A · 06-14</option>
          <option value="B">B · 14-22</option>
          <option value="C">C · 22-06</option>
        </select>
        <div className="ml-auto flex gap-2 print:hidden">
          <button
            type="button"
            className="border border-kavana-border rounded-sm px-3 py-1"
            onClick={descargar}
            disabled={!informe || informe.puestos.length === 0}
          >
            Descargar CSV
          </button>
          <button
            type="button"
            className="border border-kavana-border rounded-sm px-3 py-1"
            onClick={() => window.print()}
          >
            Imprimir / PDF
          </button>
        </div>
      </div>

      {error && <p className="text-kavana-danger text-sm">{error}</p>}
      {!error && informe === null && (
        <p className="text-kavana-text-dim text-sm">Cargando informe...</p>
      )}
      {informe && informe.puestos.length === 0 && (
        <p className="text-kavana-text-dim text-sm">Sin actividad registrada en este turno.</p>
      )}
      {informe && informe.puestos.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-kavana-text-dim text-xs">
                <th className="py-1 pr-2">Puesto</th>
                <th className="py-1 pr-2 text-right">Piezas</th>
                <th className="py-1 pr-2 text-right">Consumo</th>
                <th className="py-1 pr-2 text-right">Merma</th>
                <th className="py-1 pr-2 text-right">Autocontroles</th>
                <th className="py-1 text-right">Incidencias</th>
              </tr>
            </thead>
            <tbody>
              {informe.puestos.map((p) => (
                <tr key={p.puesto} className="border-t border-kavana-border">
                  <td className="py-1 pr-2 font-semibold">{p.puesto}</td>
                  <td className="py-1 pr-2 text-right mono-data">{fmt(p.piezas)}</td>
                  <td className="py-1 pr-2 text-right mono-data">
                    {fmt(p.consumo_kg, 1)} kg{p.consumo_m > 0 ? ` · ${fmt(p.consumo_m, 1)} m` : ''}
                  </td>
                  <td className="py-1 pr-2 text-right mono-data">
                    {fmt(p.merma_kg, 1)} kg · {fmt(p.merma_coste, 2)} €
                  </td>
                  <td className="py-1 pr-2 text-right mono-data">
                    {p.autocontroles}
                    {p.autocontroles_nok > 0 && (
                      <span className="text-kavana-danger"> ({p.autocontroles_nok} NOK)</span>
                    )}
                  </td>
                  <td className="py-1 text-right mono-data">
                    {p.incidencias}
                    {p.parada_min > 0 ? ` · ${fmt(p.parada_min)} min` : ''}
                  </td>
                </tr>
              ))}
              <tr className="border-t-2 border-kavana-border font-bold">
                <td className="py-1 pr-2">Total</td>
                <td className="py-1 pr-2 text-right mono-data">{fmt(informe.totales.piezas)}</td>
                <td className="py-1 pr-2 text-right mono-data">{fmt(informe.totales.consumo_kg, 1)} kg</td>
                <td className="py-1 pr-2 text-right mono-data">
                  {fmt(informe.totales.merma_kg, 1)} kg · {fmt(informe.totales.merma_coste, 2)} €
                </td>
                <td className="py-1 pr-2 text-right mono-data">{informe.totales.autocontroles}</td>
                <td className="py-1 text-right mono-data">{informe.totales.incidencias}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
      {informe && (informe.por_operario ?? []).length > 0 && (
        <div className="overflow-x-auto">
          <p className="label-industrial text-xs text-kavana-text-dim mt-4 mb-1">
            Chatarra por operario · kilos consumidos frente a piezas buenas
          </p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-kavana-text-dim text-xs">
                <th className="py-1 pr-2">Operario</th>
                <th className="py-1 pr-2">Orden</th>
                <th className="py-1 pr-2">Material</th>
                <th className="py-1 pr-2 text-right">Piezas</th>
                <th className="py-1 pr-2 text-right">Consumido</th>
                <th className="py-1 pr-2 text-right">Chatarra</th>
                <th className="py-1 pr-2 text-right">Prevista</th>
                <th className="py-1 text-right">De más</th>
              </tr>
            </thead>
            <tbody>
              {informe.por_operario.map((o) => (
                <tr key={`${o.operario}-${o.orden}-${o.material}`} className="border-t border-kavana-border">
                  <td className="py-1 pr-2 font-semibold">{o.operario}</td>
                  <td className="py-1 pr-2">{o.orden}</td>
                  <td className="py-1 pr-2">{o.material}</td>
                  <td className="py-1 pr-2 text-right mono-data">{fmt(o.piezas)}</td>
                  <td className="py-1 pr-2 text-right mono-data">{fmt(o.consumo_kg, 1)} kg</td>
                  <td className="py-1 pr-2 text-right mono-data">
                    {fmt(o.chatarra_kg, 1)} kg
                    {o.chatarra_pct !== null ? ` · ${fmt(o.chatarra_pct, 1)} %` : ''}
                  </td>
                  <td className="py-1 pr-2 text-right mono-data">
                    {o.chatarra_prevista_kg != null ? `${fmt(o.chatarra_prevista_kg, 1)} kg` : 'aprendiendo'}
                  </td>
                  <td
                    className={`py-1 text-right mono-data ${
                      (o.chatarra_de_mas_kg ?? 0) > 0 ? 'text-kavana-orange font-semibold' : ''
                    }`}
                  >
                    {o.chatarra_de_mas_kg != null ? `${fmt(o.chatarra_de_mas_kg, 1)} kg` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs text-kavana-text-dim mt-1">
            La chatarra aparece cuando el operario mide la bobina (cierre de turno o fin de bobina).
            Prevista: la que el modelo genera sí o sí (exacta si tiene el peso de la pieza terminada;
            si no, la normal aprendida tras 3 órdenes medidas). De más: la que se podía evitar.
          </p>
        </div>
      )}
    </div>
  )
}
