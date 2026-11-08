import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { PanelCostes, PeriodoPanel } from '../lib/api'
import { fmtNum, plural } from '../panel/formato'
import type { Tono } from '../panel/tokens'
import { EstadoBanner, KpiCard, Seccion, Selector } from '../panel/ui'
import { PicosAcumulados } from './PicosAcumulados'

const PERIODOS: { valor: PeriodoPanel; texto: string }[] = [
  { valor: 'semana', texto: 'Semana' },
  { valor: 'mes', texto: 'Mes' },
  { valor: 'trimestre', texto: 'Trimestre' },
]

const ESTE: Record<PeriodoPanel, string> = {
  semana: 'esta semana',
  mes: 'este mes',
  trimestre: 'este trimestre',
}

/** Objetivo por defecto de chatarra (el mismo que usa la vista Turno). */
const OBJETIVO_CHATARRA_PCT = 3

const fecha = (iso: string) => {
  const [anio, mes, dia] = iso.slice(0, 10).split('-')
  return `${dia}/${mes}/${anio}`
}

/** Vista Material: kilos transformados y merma, sin euros. Usa los mismos datos del
 *  servicio de costes (el cliente no recalcula nada) pero solo enseña lo físico. */
export function VistaMaterial() {
  const [periodo, setPeriodo] = useState<PeriodoPanel>('mes')
  const [datos, setDatos] = useState<PanelCostes | null>(null)
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
        if (vigente) setError(e instanceof Error ? e.message : 'No se pudo cargar el material')
      })
    return () => {
      vigente = false
    }
  }, [periodo])

  const vacio = datos !== null && (datos.ordenes_completadas === 0 || datos.kg_total === 0)
  const chatarra = datos?.chatarra.pct_material ?? null
  const tonoChatarra: Tono =
    chatarra === null ? 'gris' : chatarra <= OBJETIVO_CHATARRA_PCT ? 'ok' : 'aviso'

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="m-0 text-2xl font-bold tracking-tight">Material y merma</h1>
          {datos && (
            <p className="m-0 mt-1 text-sm text-p-texto2">
              Del {fecha(datos.desde)} al {fecha(datos.hasta)} · horario de planta
            </p>
          )}
        </div>
        <Selector etiqueta="Periodo" opciones={PERIODOS} valor={periodo} onCambio={setPeriodo} />
      </div>

      {error && (
        <p className="m-0 text-sm text-p-mal bg-p-mal-bg border border-p-mal-borde rounded-lg p-3">
          {error}
        </p>
      )}
      {!error && datos === null && (
        <p className="m-0 text-sm text-p-texto2">Cargando material del periodo…</p>
      )}

      {datos && (
        <>
          <EstadoBanner
            tono={vacio ? 'gris' : tonoChatarra}
            titular={
              vacio
                ? `Sin órdenes completadas ${ESTE[periodo]}`
                : `${fmtNum(datos.kg_total)} kg transformados ${ESTE[periodo]}`
            }
            detalle={
              vacio
                ? 'Cuando se cierren órdenes verás aquí cuánto material se ha usado y cuánto se ha perdido.'
                : `La chatarra es el ${fmtNum(chatarra, 1)} % del material cargado (objetivo: por debajo del ${OBJETIVO_CHATARRA_PCT} %). ${plural(datos.ordenes_completadas, 'orden completada', 'órdenes completadas')}.`
            }
          />

          <div className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-4">
            <KpiCard label="Kilos transformados" valor={fmtNum(datos.kg_total)} unidad="kg" />
            <KpiCard
              label="Chatarra"
              valor={fmtNum(chatarra, 1)}
              unidad="% del material"
              estado={{
                texto:
                  tonoChatarra === 'ok'
                    ? 'En objetivo'
                    : tonoChatarra === 'gris'
                      ? 'Sin datos'
                      : 'Por encima',
                tono: tonoChatarra,
              }}
            />
            <KpiCard label="Órdenes completadas" valor={fmtNum(datos.ordenes_completadas)} />
          </div>

          {datos.por_familia.length > 0 && (
            <Seccion
              titulo="¿Qué material se ha usado?"
              subtitulo="Kilos y merma de cada familia de material en las órdenes cerradas del periodo."
            >
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wide text-p-etiqueta">
                      <th className="py-2 pr-3 font-semibold">Material</th>
                      <th className="py-2 pr-3 font-semibold text-right">Kilos</th>
                      <th className="py-2 pr-3 font-semibold text-right">Merma</th>
                      <th className="py-2 font-semibold text-right">Órdenes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {datos.por_familia.map((f) => (
                      <tr key={f.familia} className="border-t border-p-linea">
                        <td className="py-2.5 pr-3 font-semibold">{f.etiqueta}</td>
                        <td className="py-2.5 pr-3 text-right">{fmtNum(f.kg)} kg</td>
                        <td className="py-2.5 pr-3 text-right">{fmtNum(f.merma_pct, 1)} %</td>
                        <td className="py-2.5 text-right">{fmtNum(f.ordenes)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Seccion>
          )}

          {datos.ordenes.length > 0 && (
            <Seccion titulo="Órdenes del periodo" subtitulo="Kilos transformados en cada orden cerrada.">
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wide text-p-etiqueta">
                      <th className="py-2 pr-3 font-semibold">Orden</th>
                      <th className="py-2 pr-3 font-semibold">Producto</th>
                      <th className="py-2 font-semibold text-right">Kilos</th>
                    </tr>
                  </thead>
                  <tbody>
                    {datos.ordenes.map((o) => (
                      <tr key={o.order_id} className="border-t border-p-linea">
                        <td className="py-2.5 pr-3 font-bold">{o.numero}</td>
                        <td className="py-2.5 pr-3 text-p-texto2">{o.producto ?? '—'}</td>
                        <td className="py-2.5 text-right">{fmtNum(o.kg)} kg</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Seccion>
          )}
        </>
      )}

      <PicosAcumulados />
    </div>
  )
}
