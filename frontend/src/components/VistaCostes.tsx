import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { PanelCostes as PanelCostesData, PeriodoPanel } from '../lib/api'

const PERIODOS: { valor: PeriodoPanel; etiqueta: string }[] = [
  { valor: 'semana', etiqueta: 'Semana' },
  { valor: 'mes', etiqueta: 'Mes' },
  { valor: 'trimestre', etiqueta: 'Trimestre' },
]

const fmtNum = (n: number | null | undefined, dec = 0) =>
  n === null || n === undefined ? '--' : n.toLocaleString('es-ES', { maximumFractionDigits: dec })
/** Decimales fijos: el importe se muestra con los dos decimales que manda el
 *  backend (640,00 €), sin redondear a la vista lo que el servicio calculó. */
const fmtDec = (n: number | null | undefined, dec = 2) =>
  n === null || n === undefined
    ? '--'
    : n.toLocaleString('es-ES', {
        minimumFractionDigits: dec,
        maximumFractionDigits: dec,
      })
const fmtEur = (n: number | null | undefined) => (n == null ? '--' : `${fmtDec(n, 2)} €`)
const fmtPct = (n: number | null | undefined) => (n == null ? '--' : `${fmtDec(n, 2)} %`)
const conSigno = (n: number, sufijo: string) => `${n > 0 ? '+' : ''}${fmtDec(n, 2)}${sufijo}`

/** Fecha de la ventana tal como la manda el backend (sin reinterpretar la zona
 *  horaria: la ventana es la de planta, no la del navegador). */
const fmtFechaVentana = (iso: string) => {
  const [anio, mes, dia] = iso.slice(0, 10).split('-')
  return `${dia}/${mes}/${anio}`
}

const fmtSemana = (iso: string) => `Semana del ${fmtFechaVentana(iso)}`

/** Vista Costes del panel de mando (fase 3).
 *  Todo lo que se ve viene del endpoint: el cliente formatea, no recalcula
 *  €/kg, porcentajes ni desviaciones. Periodo natural de planta.
 */
export function VistaCostes() {
  const [periodo, setPeriodo] = useState<PeriodoPanel>('mes')
  const [datos, setDatos] = useState<PanelCostesData | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let vigente = true
    setDatos(null)
    setError('')
    api
      .getPanelCostes(periodo)
      .then((d) => {
        if (vigente) setDatos(d)
      })
      .catch((e) => {
        if (vigente) setError(e instanceof Error ? e.message : 'No se pudo cargar el panel de costes')
      })
    return () => {
      vigente = false
    }
  }, [periodo])

  const descargar = () => {
    api
      .descargarPanelCostesCsv(periodo)
      .catch(() => setError('No se pudo descargar el CSV'))
  }

  const maxTendencia = datos ? Math.max(...datos.tendencia.map((t) => t.valor), 0) : 0

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <div className="flex gap-1" role="group" aria-label="Periodo">
          {PERIODOS.map((p) => (
            <button
              key={p.valor}
              type="button"
              aria-pressed={periodo === p.valor}
              className={`px-3 py-1 rounded-sm border ${
                periodo === p.valor
                  ? 'border-kavana-orange text-kavana-orange'
                  : 'border-kavana-border text-kavana-text-dim'
              }`}
              onClick={() => setPeriodo(p.valor)}
            >
              {p.etiqueta}
            </button>
          ))}
        </div>
        {datos && (
          <span className="text-xs text-kavana-text-dim">
            {fmtFechaVentana(datos.desde)} — {fmtFechaVentana(datos.hasta)}
          </span>
        )}
        <button
          type="button"
          className="ml-auto border border-kavana-border rounded-sm px-3 py-1"
          onClick={descargar}
          disabled={!datos}
        >
          Descargar CSV de costes
        </button>
      </div>

      {error && <p className="text-kavana-danger text-sm">{error}</p>}
      {!error && datos === null && (
        <p className="text-kavana-text-dim text-sm">Cargando costes del periodo...</p>
      )}

      {datos && (
        <>
          {/* Cabecera: €/kg con su comparativa y el objetivo, si está configurado */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="border border-kavana-border rounded-sm p-3">
              <p className="text-xs text-kavana-text-dim">€/kg del periodo</p>
              <p className="text-3xl font-black mono-data">
                {fmtDec(datos.coste_kg.valor, 2)}
                <span className="text-base text-kavana-text-dim"> €/kg</span>
              </p>
              <p className="text-xs text-kavana-text-dim">
                Material {fmtDec(datos.coste_kg.material, 2)} €/kg · Transformación{' '}
                {fmtDec(datos.coste_kg.transformacion, 2)} €/kg
              </p>
              <p className="text-xs text-kavana-text-dim">
                Periodo anterior {fmtDec(datos.coste_kg.periodo_anterior, 2)} €/kg
              </p>
              <p className="text-xs text-kavana-text-dim">
                {datos.coste_kg.objetivo === null
                  ? 'Sin objetivo de €/kg configurado'
                  : `Objetivo ${fmtDec(datos.coste_kg.objetivo, 2)} €/kg`}
              </p>
            </div>

            <div className="border border-kavana-border rounded-sm p-3">
              <p className="text-xs text-kavana-text-dim">Coste total</p>
              <p className="text-2xl font-bold mono-data">{fmtEur(datos.coste_total)}</p>
              <p className="text-xs text-kavana-text-dim">
                {fmtNum(datos.kg_total, 1)} kg valorados · {datos.ordenes_completadas} órdenes
                completadas
              </p>
              {datos.lineas_metros_excluidas > 0 && (
                <p className="text-xs text-kavana-text-dim">
                  {datos.lineas_metros_excluidas} líneas en metros fuera del €/kg
                </p>
              )}
            </div>

            <div className="border border-kavana-border rounded-sm p-3">
              <p className="text-xs text-kavana-text-dim">Chatarra</p>
              <p className="text-2xl font-bold mono-data">{fmtEur(datos.chatarra.euros)}</p>
              <p className="text-xs text-kavana-text-dim">
                {fmtPct(datos.chatarra.pct_material)} del material cargado
              </p>
            </div>

            <div className="border border-kavana-border rounded-sm p-3">
              <p className="text-xs text-kavana-text-dim">Desviación sobre lo estimado</p>
              {datos.desviacion.ordenes_con_estimado === 0 ? (
                <p className="text-sm text-kavana-text-dim">
                  Sin órdenes con estimado: no hay desviación que comparar.
                </p>
              ) : (
                <>
                  <p
                    className={`text-2xl font-bold mono-data ${
                      (datos.desviacion.euros ?? 0) > 0 ? 'text-kavana-danger' : 'text-kavana-ok'
                    }`}
                  >
                    {datos.desviacion.euros === null ? '--' : conSigno(datos.desviacion.euros, ' €')}
                  </p>
                  <p className="text-xs text-kavana-text-dim">
                    {datos.desviacion.pct === null ? '--' : conSigno(datos.desviacion.pct, ' %')} ·{' '}
                    {datos.desviacion.ordenes_con_estimado} órdenes con estimado
                  </p>
                </>
              )}
            </div>
          </div>

          {/* En qué se va el dinero */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <div className="border border-kavana-border rounded-sm p-3 space-y-2">
              <p className="text-xs text-kavana-text-dim">Reparto del coste</p>
              {datos.reparto.length === 0 && (
                <p className="text-sm text-kavana-text-dim">Sin coste que repartir en el periodo.</p>
              )}
              {datos.reparto.map((r) => (
                <div key={r.clave} className="space-y-1">
                  <div className="flex justify-between text-sm">
                    <span>{r.etiqueta}</span>
                    <span className="mono-data">
                      {fmtEur(r.euros)} · {fmtPct(r.pct)}
                    </span>
                  </div>
                  <div className="h-1.5 bg-kavana-dark rounded-sm overflow-hidden">
                    <div className="h-full bg-kavana-orange" style={{ width: `${r.pct}%` }} />
                  </div>
                </div>
              ))}
            </div>

            <div className="border border-kavana-border rounded-sm p-3 space-y-2">
              <p className="text-xs text-kavana-text-dim">Coste de paradas</p>
              {datos.coste_paradas.total === 0 ? (
                <p className="text-sm text-kavana-text-dim">
                  Sin paradas valoradas en el periodo.
                </p>
              ) : (
                <>
                  <p className="text-xl font-bold mono-data">
                    {fmtEur(datos.coste_paradas.total)}
                    <span className="text-sm text-kavana-text-dim">
                      {` · ${fmtDec(datos.coste_paradas.horas, 1)} h`}
                    </span>
                  </p>
                  {datos.coste_paradas.por_tipo.map((t) => (
                    <div key={t.tipo} className="flex justify-between text-sm">
                      <span>{t.etiqueta}</span>
                      <span className="mono-data">{fmtEur(t.euros)}</span>
                    </div>
                  ))}
                </>
              )}
            </div>
          </div>

          {/* Tendencia de 8 semanas: valores del backend, barra proporcional al máximo */}
          <div className="border border-kavana-border rounded-sm p-3 space-y-2">
            <p className="text-xs text-kavana-text-dim">Tendencia de €/kg (8 semanas)</p>
            {maxTendencia === 0 ? (
              <p className="text-sm text-kavana-text-dim">
                Sin coste registrado en las últimas 8 semanas.
              </p>
            ) : (
              datos.tendencia.map((t) => (
                <div key={t.semana} className="flex items-center gap-2 text-xs">
                  <span className="w-36 shrink-0 text-kavana-text-dim">{fmtSemana(t.semana)}</span>
                  <div className="h-1.5 flex-1 bg-kavana-dark rounded-sm overflow-hidden">
                    <div
                      className="h-full bg-kavana-orange"
                      style={{ width: `${Math.round((t.valor / maxTendencia) * 100)}%` }}
                    />
                  </div>
                  <span className="w-20 text-right mono-data">{fmtDec(t.valor, 2)} €/kg</span>
                </div>
              ))
            )}
          </div>

          {/* Órdenes con más desviación (máx. 10, las ordena el backend) */}
          <div className="border border-kavana-border rounded-sm p-3 space-y-2">
            <p className="text-xs text-kavana-text-dim">Órdenes con más desviación</p>
            {datos.ordenes.length === 0 ? (
              <p className="text-sm text-kavana-text-dim">Sin órdenes completadas en el periodo.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-kavana-text-dim text-xs">
                      <th className="py-1 pr-2">Orden</th>
                      <th className="py-1 pr-2">Producto</th>
                      <th className="py-1 pr-2 text-right">kg</th>
                      <th className="py-1 pr-2 text-right">Estimado</th>
                      <th className="py-1 pr-2 text-right">Real</th>
                      <th className="py-1 pr-2 text-right">Desviación</th>
                      <th className="py-1">Causa</th>
                    </tr>
                  </thead>
                  <tbody>
                    {datos.ordenes.map((o) => (
                      <tr key={o.order_id} className="border-t border-kavana-border">
                        <td className="py-1 pr-2 font-semibold">{o.numero}</td>
                        <td className="py-1 pr-2">{o.producto ?? '--'}</td>
                        <td className="py-1 pr-2 text-right mono-data">{fmtNum(o.kg, 1)}</td>
                        <td className="py-1 pr-2 text-right mono-data">{fmtEur(o.estimado)}</td>
                        <td className="py-1 pr-2 text-right mono-data">{fmtEur(o.real)}</td>
                        <td
                          className={`py-1 pr-2 text-right mono-data ${
                            (o.desv_euros ?? 0) > 0 ? 'text-kavana-danger' : 'text-kavana-ok'
                          }`}
                        >
                          {o.desv_euros === null ? '--' : conSigno(o.desv_euros, ' €')}
                          {o.desv_pct !== null && (
                            <span className="text-xs text-kavana-text-dim">
                              {' '}
                              ({conSigno(o.desv_pct, ' %')})
                            </span>
                          )}
                        </td>
                        <td className="py-1">{o.causa}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
