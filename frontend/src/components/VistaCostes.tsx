import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { PanelCostes as PanelCostesData, PeriodoPanel } from '../lib/api'
import { GraficoLinea } from '../panel/GraficoLinea'
import type { Tono } from '../panel/tokens'
import { EstadoBanner, KpiCard, Pastilla, Seccion, Selector } from '../panel/ui'

const PERIODOS: { valor: PeriodoPanel; texto: string }[] = [
  { valor: 'semana', texto: 'Semana' },
  { valor: 'mes', texto: 'Mes' },
  { valor: 'trimestre', texto: 'Trimestre' },
]

/** Cómo se nombra el periodo en una frase ("este mes", "el mes anterior"). */
const NOMBRE_PERIODO: Record<PeriodoPanel, { este: string; anterior: string }> = {
  semana: { este: 'esta semana', anterior: 'la semana anterior' },
  mes: { este: 'este mes', anterior: 'el mes anterior' },
  trimestre: { este: 'este trimestre', anterior: 'el trimestre anterior' },
}

/** Color de cada parte del coste en la barra apilada y su leyenda. */
const COLOR_REPARTO: Record<string, string> = {
  material: 'bg-p-texto',
  mano_obra: 'bg-p-plan',
  chatarra: 'bg-p-mal',
}

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
const fmtDiaMes = (iso: string) => fmtFechaVentana(iso).slice(0, 5)

/** Una desviación por encima del 3 % es para mirarla; por debajo de 0, ahorro. */
const tonoDesviacion = (pct: number | null): Tono =>
  pct === null ? 'gris' : pct > 3 ? 'mal' : pct < 0 ? 'ok' : 'gris'

/** Frase de estado del periodo: compara con el anterior, no inventa objetivos. */
function resumen(d: PanelCostesData): { tono: Tono; titular: string; detalle: string } {
  const nombre = NOMBRE_PERIODO[d.periodo]
  if (d.ordenes_completadas === 0 || d.kg_total === 0) {
    return {
      tono: 'gris',
      titular: `Sin órdenes completadas ${nombre.este}`,
      detalle: 'Cuando se cierren órdenes verás aquí cuánto cuesta producir cada kilo.',
    }
  }
  const actual = `${fmtDec(d.coste_kg.valor, 2)} €/kg`
  const anterior = d.coste_kg.periodo_anterior
  let tono: Tono = 'gris'
  let titular = `Producir cuesta ${actual} ${nombre.este}`
  if (anterior > 0) {
    const comparado = `(${fmtDec(anterior, 2)} €/kg)`
    if (d.coste_kg.valor < anterior) {
      tono = 'ok'
      titular += `, menos que ${nombre.anterior} ${comparado}`
    } else if (d.coste_kg.valor > anterior) {
      tono = 'aviso'
      titular += `, más que ${nombre.anterior} ${comparado}`
    } else {
      titular += `, igual que ${nombre.anterior}`
    }
  }
  let detalle = `Material ${fmtDec(d.coste_kg.material, 2)} €/kg y transformación ${fmtDec(
    d.coste_kg.transformacion,
    2,
  )} €/kg.`
  if (anterior <= 0) detalle += ' Sin datos del periodo anterior para comparar.'
  const euros = d.desviacion.euros
  if (euros !== null && euros > 0) detalle += ` Gastamos ${fmtEur(euros)} más de lo estimado.`
  if (euros !== null && euros < 0) detalle += ` Gastamos ${fmtEur(-euros)} menos de lo estimado.`
  return { tono, titular, detalle }
}

/** Vista Costes del panel de mando: cuánto cuesta producir, si mejora, en qué
 *  se va el dinero y qué órdenes se desvían. Todo lo que se ve viene del
 *  endpoint: el cliente formatea y compara, no recalcula €/kg ni porcentajes.
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

  const conTendencia = datos ? datos.tendencia.some((t) => t.valor > 0) : false
  const est = datos ? resumen(datos) : null
  const anterior = datos?.coste_kg.periodo_anterior ?? 0
  const tendenciaKg: { texto: string; tono: Tono } | undefined =
    datos && anterior > 0 && datos.kg_total > 0
      ? datos.coste_kg.valor < anterior
        ? { texto: 'Baja', tono: 'ok' }
        : datos.coste_kg.valor > anterior
          ? { texto: 'Sube', tono: 'aviso' }
          : { texto: 'Igual', tono: 'gris' }
      : undefined

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="m-0 text-2xl font-bold tracking-tight">Cuánto cuesta producir</h1>
          {datos && (
            <p className="m-0 mt-1 text-sm text-p-texto2">
              Del {fmtFechaVentana(datos.desde)} al {fmtFechaVentana(datos.hasta)} · horario de planta
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Selector etiqueta="Periodo" opciones={PERIODOS} valor={periodo} onCambio={setPeriodo} />
          <button
            type="button"
            onClick={descargar}
            disabled={!datos}
            className="inline-flex items-center gap-2 min-h-[44px] px-4 rounded-lg border border-p-borde bg-p-tarjeta text-sm font-medium cursor-pointer hover:border-p-texto2 disabled:opacity-40 disabled:cursor-default"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M12 3v12M7 10l5 5 5-5M4 21h16" />
            </svg>
            Exportar informe
          </button>
        </div>
      </div>

      {error && (
        <p className="m-0 text-sm text-p-mal bg-p-mal-bg border border-p-mal-borde rounded-lg p-3">
          {error}
        </p>
      )}
      {!error && datos === null && (
        <p className="m-0 text-sm text-p-texto2">Cargando costes del periodo...</p>
      )}

      {datos && est && (
        <>
          <EstadoBanner tono={est.tono} titular={est.titular} detalle={est.detalle} />

          <div className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-4">
            <KpiCard
              label="Coste por kilo"
              valor={fmtDec(datos.coste_kg.valor, 2)}
              unidad="€/kg"
              estado={tendenciaKg}
              contexto={
                <>
                  <p className="m-0">
                    Material {fmtDec(datos.coste_kg.material, 2)} €/kg · Transformación{' '}
                    {fmtDec(datos.coste_kg.transformacion, 2)} €/kg
                  </p>
                  <p className="m-0">
                    Periodo anterior {fmtDec(datos.coste_kg.periodo_anterior, 2)} €/kg
                  </p>
                  <p className="m-0">
                    {datos.coste_kg.objetivo === null
                      ? 'Sin objetivo de €/kg configurado'
                      : `Objetivo ${fmtDec(datos.coste_kg.objetivo, 2)} €/kg`}
                  </p>
                </>
              }
            />
            <KpiCard
              label="Coste producido"
              valor={fmtEur(datos.coste_total)}
              contexto={
                <>
                  <p className="m-0">
                    {fmtNum(datos.kg_total, 1)} kg valorados · {datos.ordenes_completadas} órdenes
                    completadas
                  </p>
                  {datos.lineas_metros_excluidas > 0 && (
                    <p className="m-0">
                      {datos.lineas_metros_excluidas} líneas en metros fuera del €/kg
                    </p>
                  )}
                </>
              }
            />
            {datos.desviacion.ordenes_con_estimado === 0 ? (
              <KpiCard
                label="Desviación vs estimado"
                valor="--"
                contexto="Sin órdenes con estimado: no hay desviación que comparar."
              />
            ) : (
              <KpiCard
                label="Desviación vs estimado"
                valor={
                  datos.desviacion.euros === null ? '--' : conSigno(datos.desviacion.euros, ' €')
                }
                estado={{
                  texto:
                    tonoDesviacion(datos.desviacion.pct) === 'mal'
                      ? 'Por encima'
                      : tonoDesviacion(datos.desviacion.pct) === 'ok'
                        ? 'Por debajo'
                        : 'En línea',
                  tono: tonoDesviacion(datos.desviacion.pct),
                }}
                contexto={`${
                  datos.desviacion.pct === null ? '--' : conSigno(datos.desviacion.pct, ' %')
                } · ${datos.desviacion.ordenes_con_estimado} órdenes con estimado`}
              />
            )}
            <KpiCard
              label="Chatarra"
              valor={fmtEur(datos.chatarra.euros)}
              contexto={`${fmtPct(datos.chatarra.pct_material)} del material cargado`}
            />
          </div>

          <div className="flex flex-wrap gap-6 items-stretch">
            <Seccion
              titulo="Coste por kilo, semana a semana"
              subtitulo="Más bajo es mejor. Las semanas sin órdenes cerradas no tienen punto."
              className="flex-[999_1_600px]"
            >
              {conTendencia ? (
                <GraficoLinea
                  puntos={datos.tendencia.map((t) => ({
                    etiqueta: fmtDiaMes(t.semana),
                    valor: t.valor > 0 ? t.valor : null,
                  }))}
                  formato={(n) => `${fmtDec(n, 2)} €`}
                  objetivo={datos.coste_kg.objetivo}
                  descripcion={`Coste por kilo de las 8 últimas semanas: ${datos.tendencia
                    .map((t) => `${fmtDiaMes(t.semana)} ${t.valor > 0 ? `${fmtDec(t.valor, 2)} €` : 'sin dato'}`)
                    .join('; ')}`}
                />
              ) : (
                <p className="m-0 text-sm text-p-texto2">
                  Sin coste registrado en las últimas 8 semanas.
                </p>
              )}
            </Seccion>

            <Seccion
              titulo="¿En qué se va el dinero?"
              subtitulo={`${fmtEur(datos.coste_total)} producidos ${NOMBRE_PERIODO[datos.periodo].este}.`}
              className="flex-[1_1_380px]"
            >
              {datos.reparto.every((r) => r.euros === 0) ? (
                <p className="m-0 text-sm text-p-texto2">Sin coste que repartir en el periodo.</p>
              ) : (
                <>
                  <div
                    className="flex h-7 rounded-md overflow-hidden"
                    role="img"
                    aria-label={datos.reparto.map((r) => `${r.etiqueta} ${fmtPct(r.pct)}`).join(', ')}
                  >
                    {datos.reparto
                      .filter((r) => r.pct > 0)
                      .map((r) => (
                        <div
                          key={r.clave}
                          className={COLOR_REPARTO[r.clave] ?? 'bg-p-etiqueta'}
                          style={{ width: `${r.pct}%` }}
                        />
                      ))}
                  </div>
                  <ul className="m-0 p-0 list-none flex flex-col gap-2.5">
                    {datos.reparto.map((r) => (
                      <li key={r.clave} className="flex items-center gap-3 text-[15px]">
                        <span
                          className={`flex-none w-3 h-3 rounded-[3px] ${COLOR_REPARTO[r.clave] ?? 'bg-p-etiqueta'}`}
                          aria-hidden="true"
                        />
                        <span className="flex-1 font-medium">{r.etiqueta}</span>
                        <span className="font-bold">
                          {fmtEur(r.euros)} · {fmtPct(r.pct)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
              <div className="border-t border-p-linea pt-3.5">
                <p className="m-0 text-[15px] font-semibold">Coste de paradas</p>
                {datos.coste_paradas.total === 0 ? (
                  <p className="m-0 mt-1 text-[13px] text-p-texto2">
                    Sin paradas valoradas en el periodo.
                  </p>
                ) : (
                  <>
                    <p className="m-0 mt-1 text-2xl font-extrabold">
                      {fmtEur(datos.coste_paradas.total)}
                      <span className="text-sm font-medium text-p-etiqueta">
                        {` · ${fmtDec(datos.coste_paradas.horas, 1)} h`}
                      </span>
                    </p>
                    <ul className="m-0 mt-2 p-0 list-none flex flex-col gap-1 text-[13px] text-p-texto2">
                      {datos.coste_paradas.por_tipo.map((t) => (
                        <li key={t.tipo} className="flex justify-between gap-3">
                          <span>{t.etiqueta}</span>
                          <span className="font-semibold text-p-texto">{fmtEur(t.euros)}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            </Seccion>
          </div>

          <Seccion
            titulo="¿Cuánto cuesta cada material?"
            subtitulo="Coste por kilo de cada familia de material: lo que cuesta el material y lo que añade la transformación."
          >
            {datos.por_familia.length === 0 ? (
              <p className="m-0 text-sm text-p-texto2">
                Sin kilos valorados por familia en el periodo.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] border-collapse text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wider text-p-etiqueta">
                      <th className="px-3 py-2.5 font-semibold border-b border-p-borde">Familia</th>
                      <th className="px-3 py-2.5 font-semibold border-b border-p-borde text-right">Kilos</th>
                      <th className="px-3 py-2.5 font-semibold border-b border-p-borde text-right">
                        Material €/kg
                      </th>
                      <th className="px-3 py-2.5 font-semibold border-b border-p-borde text-right">
                        Transformación €/kg
                      </th>
                      <th className="px-3 py-2.5 font-semibold border-b border-p-borde text-right">Merma</th>
                      <th className="px-3 py-2.5 font-semibold border-b border-p-borde text-right">Órdenes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {datos.por_familia.map((f) => (
                      <tr key={f.familia}>
                        <td className="px-3 py-3 border-b border-p-linea font-semibold">{f.etiqueta}</td>
                        <td className="px-3 py-3 border-b border-p-linea text-right">{fmtNum(f.kg, 1)}</td>
                        <td className="px-3 py-3 border-b border-p-linea text-right">{fmtDec(f.material, 2)}</td>
                        <td className="px-3 py-3 border-b border-p-linea text-right">
                          {fmtDec(f.transformacion, 2)}
                        </td>
                        <td className="px-3 py-3 border-b border-p-linea text-right">{fmtPct(f.merma_pct)}</td>
                        <td className="px-3 py-3 border-b border-p-linea text-right">{f.ordenes}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Seccion>

          <Seccion
            titulo="¿Qué órdenes se han desviado?"
            subtitulo="Órdenes cerradas en el periodo, de mayor a menor desviación frente a su coste estimado."
          >
            {datos.ordenes.length === 0 ? (
              <p className="m-0 text-sm text-p-texto2">Sin órdenes completadas en el periodo.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[860px] border-collapse text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wider text-p-etiqueta">
                      <th className="px-3 py-2.5 font-semibold border-b border-p-borde">Orden</th>
                      <th className="px-3 py-2.5 font-semibold border-b border-p-borde">Producto</th>
                      <th className="px-3 py-2.5 font-semibold border-b border-p-borde text-right">Kilos</th>
                      <th className="px-3 py-2.5 font-semibold border-b border-p-borde text-right">Estimado</th>
                      <th className="px-3 py-2.5 font-semibold border-b border-p-borde text-right">Real</th>
                      <th className="px-3 py-2.5 font-semibold border-b border-p-borde text-right">
                        Desviación
                      </th>
                      <th className="px-3 py-2.5 font-semibold border-b border-p-borde">Causa principal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {datos.ordenes.map((o) => (
                      <tr key={o.order_id}>
                        <td className="px-3 py-3 border-b border-p-linea font-bold">{o.numero}</td>
                        <td className="px-3 py-3 border-b border-p-linea">{o.producto ?? '--'}</td>
                        <td className="px-3 py-3 border-b border-p-linea text-right text-p-texto2">
                          {fmtNum(o.kg, 1)}
                        </td>
                        <td className="px-3 py-3 border-b border-p-linea text-right text-p-texto2">
                          {fmtEur(o.estimado)}
                        </td>
                        <td className="px-3 py-3 border-b border-p-linea text-right font-semibold">
                          {fmtEur(o.real)}
                        </td>
                        <td className="px-3 py-3 border-b border-p-linea text-right">
                          <Pastilla tono={tonoDesviacion(o.desv_pct)}>
                            {o.desv_euros === null ? '--' : conSigno(o.desv_euros, ' €')}
                            {o.desv_pct !== null && ` · ${conSigno(o.desv_pct, ' %')}`}
                          </Pastilla>
                        </td>
                        <td className="px-3 py-3 border-b border-p-linea text-p-texto2">{o.causa}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Seccion>

          <p className="m-0 text-xs text-p-etiqueta">
            Coste de producción (material, mano de obra y chatarra). La facturación y la contabilidad
            se llevan en el ERP.
          </p>
        </>
      )}
    </div>
  )
}
