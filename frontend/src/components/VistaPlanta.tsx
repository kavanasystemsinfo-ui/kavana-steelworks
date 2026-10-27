import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { PanelPlanta, PeriodoPlanta } from '../lib/api'
import { fmtDuracion, fmtEntrega, fmtNum, plural } from '../panel/formato'
import { GraficoLinea } from '../panel/GraficoLinea'
import { CLASES_TONO, type Tono } from '../panel/tokens'
import { ESTADO_ORDEN } from '../panel/turno'
import { EstadoBanner, KpiCard, Pastilla, Seccion, Selector } from '../panel/ui'

const PERIODOS: { valor: PeriodoPlanta; texto: string }[] = [
  { valor: 'hoy', texto: 'Hoy' },
  { valor: 'semana', texto: 'Esta semana' },
  { valor: '8semanas', texto: 'Últimas 8 semanas' },
]

const NOMBRE: Record<PeriodoPlanta, { este: string; anterior: string; corto: string }> = {
  hoy: { este: 'hoy', anterior: 'ayer a esta hora', corto: 'ayer' },
  semana: { este: 'esta semana', anterior: 'la semana anterior', corto: 'sem. anterior' },
  '8semanas': { este: 'en 8 semanas', anterior: 'las 8 semanas anteriores', corto: 'periodo anterior' },
}

/** Tono de una eficiencia frente a su objetivo: en objetivo, a menos de 10 puntos, o lejos. */
const tonoObjetivo = (valor: number, objetivo: number): Tono =>
  valor >= objetivo ? 'ok' : valor >= objetivo - 10 ? 'aviso' : 'mal'

const conSigno = (n: number, sufijo: string) => `${n > 0 ? '+' : ''}${fmtNum(n, 1)}${sufijo}`

/** Barra horizontal con la raya del objetivo encima (el color dice si llega). */
function BarraObjetivo({
  pct,
  objetivo,
  tono,
  etiqueta,
}: {
  pct: number
  objetivo?: number
  tono: Tono
  etiqueta: string
}) {
  const ancho = Math.max(0, Math.min(100, pct))
  return (
    <div
      className="relative h-3 rounded-full bg-p-linea"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(ancho)}
      aria-label={etiqueta}
    >
      <div className={`h-full rounded-full ${CLASES_TONO[tono].solido}`} style={{ width: `${ancho}%` }} />
      {objetivo !== undefined && (
        <div
          className="absolute -top-1 -bottom-1 w-[3px] rounded bg-p-texto"
          style={{ left: `calc(${Math.min(objetivo, 100)}% - 1.5px)` }}
          aria-hidden="true"
        />
      )}
    </div>
  )
}

/** Vista Planta del panel de mando: para el jefe de planta o el CTO, cómo
 *  evoluciona la eficiencia, dónde se pierde y qué entregas peligran.
 */
export function VistaPlanta() {
  const [periodo, setPeriodo] = useState<PeriodoPlanta>('semana')
  const [datos, setDatos] = useState<PanelPlanta | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let vivo = true
    setError('')
    api
      .getPlanta(periodo)
      .then((d) => vivo && setDatos(d))
      .catch((e) => vivo && setError(e instanceof Error ? e.message : 'Error de conexión'))
    return () => {
      vivo = false
    }
  }, [periodo])

  const cabecera = (
    <div className="flex flex-wrap items-center justify-between gap-4">
      <h1 className="m-0 text-[26px] font-bold tracking-tight">Cómo va la planta</h1>
      <Selector opciones={PERIODOS} valor={periodo} onCambio={setPeriodo} etiqueta="Periodo" />
    </div>
  )

  if (!datos || datos.periodo !== periodo) {
    return (
      <>
        {cabecera}
        <p className="m-0 text-sm text-p-texto2">
          {error ? `No se pudo cargar la planta: ${error}` : 'Cargando…'}
        </p>
      </>
    )
  }

  const d = datos
  const n = NOMBRE[periodo]
  const obj = d.objetivos
  const ef = d.eficiencia
  const ant = d.anterior.eficiencia
  const delta = ef && ant !== null ? ef.oee - ant : null
  const causa = d.paradas.por_causa[0]
  const freno = d.puestos[0]

  // Frase de estado: cómo está la eficiencia, hacia dónde va y qué la frena
  let banner: { tono: Tono; titular: string; detalle: string }
  if (!ef) {
    banner = {
      tono: 'gris',
      titular: `Sin producción medida ${n.este}`,
      detalle:
        'La eficiencia necesita horas trabajadas registradas y el ritmo nominal de los puestos.',
    }
  } else {
    const tendencia =
      delta === null ? '' : delta > 0.5 ? ', mejorando' : delta < -0.5 ? ', empeorando' : ', estable'
    const frente =
      ef.oee >= obj.oee
        ? 'en objetivo'
        : `${fmtNum(obj.oee - ef.oee)} ${obj.oee - ef.oee >= 1.5 ? 'puntos' : 'punto'} por debajo del objetivo`
    const partes = []
    if (causa) {
      partes.push(
        `La mayor pérdida son las paradas por ${causa.causa}: ${fmtDuracion(causa.minutos)}, el ${fmtNum(causa.pct)} % del tiempo parado.`,
      )
    }
    if (freno && d.puestos.length > 1) {
      partes.push(`El cuello de botella es ${freno.puesto} (${fmtNum(freno.oee)} %).`)
    }
    banner = {
      tono: tonoObjetivo(ef.oee, obj.oee),
      titular: `Eficiencia ${fmtNum(ef.oee)} %${tendencia}${ef.oee >= obj.oee ? ', ' : ', pero '}${frente}`,
      detalle: partes.join(' ') || 'Sin paradas registradas en el periodo.',
    }
  }

  const factores = ef
    ? [
        {
          clave: 'disponibilidad',
          titulo: 'Tiempo en marcha',
          sub: 'disponibilidad',
          valor: ef.disponibilidad,
          objetivo: obj.disponibilidad,
          nota:
            d.paradas.minutos > 0
              ? `Se pierden ${fmtDuracion(d.paradas.minutos)} por paradas.`
              : 'Sin paradas registradas.',
        },
        {
          clave: 'rendimiento',
          titulo: 'Velocidad',
          sub: 'rendimiento',
          valor: ef.rendimiento,
          objetivo: obj.rendimiento,
          nota:
            ef.rendimiento < 100
              ? `Las máquinas van un ${fmtNum(100 - ef.rendimiento)} % más lentas que su ritmo nominal.`
              : 'Las máquinas van a su ritmo nominal.',
        },
        {
          clave: 'calidad',
          titulo: 'Piezas buenas',
          sub: 'calidad',
          valor: ef.calidad,
          objetivo: obj.calidad,
          nota: `${fmtNum(100 - ef.calidad, 1)} % de chatarra sobre el material.`,
        },
      ]
    : []
  const peorFactor = factores.length
    ? factores.reduce((a, b) => (b.valor - b.objetivo < a.valor - a.objetivo ? b : a))
    : null

  const tendencia = d.tendencia.map((t) => ({ etiqueta: t.semana, valor: t.oee }))
  const conDatos = tendencia.filter((t) => t.valor !== null)
  const maxParada = Math.max(1, ...d.paradas.por_causa.map((c) => c.minutos))
  const enPeligro = d.ordenes.filter((o) => o.estado !== 'a_tiempo').length

  return (
    <>
      {cabecera}
      {error && <p className="m-0 text-sm text-p-mal">Sin conexión: se muestran los últimos datos. {error}</p>}
      <EstadoBanner tono={banner.tono} titular={banner.titular} detalle={banner.detalle} />

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard
          label="Eficiencia (OEE)"
          valor={ef ? `${fmtNum(ef.oee)} %` : '--'}
          unidad={`objetivo ${fmtNum(obj.oee)} %`}
          estado={
            delta !== null
              ? { texto: `${conSigno(delta, ' pts')} vs ${n.corto}`, tono: delta >= 0 ? 'ok' : 'mal' }
              : { texto: `Sin datos de ${n.corto}`, tono: 'gris' }
          }
          contexto={ant !== null ? `${n.anterior[0].toUpperCase()}${n.anterior.slice(1)}: ${fmtNum(ant)} %.` : 'Sin periodo anterior para comparar.'}
        />
        <KpiCard
          label="Piezas buenas"
          valor={fmtNum(d.piezas)}
          unidad={d.plan ? `de ${fmtNum(d.plan)}` : undefined}
          estado={
            d.plan
              ? { texto: `${fmtNum((d.piezas / d.plan) * 100)} % del plan`, tono: tonoObjetivo((d.piezas / d.plan) * 100, 95) }
              : { texto: 'Sin plan', tono: 'gris' }
          }
          contexto={
            d.plan
              ? `Plan: lo que harían los puestos a su ritmo nominal sin paradas. ${n.anterior[0].toUpperCase()}${n.anterior.slice(1)}: ${fmtNum(d.anterior.piezas)}.`
              : 'Sin horas registradas en puestos con ritmo nominal.'
          }
        />
        <KpiCard
          label="Entregas a tiempo"
          valor={fmtNum(d.entregas.a_tiempo)}
          unidad={`de ${fmtNum(d.entregas.total)}`}
          estado={
            d.entregas.total
              ? {
                  texto: `${fmtNum((d.entregas.a_tiempo / d.entregas.total) * 100)} %`,
                  tono: d.entregas.a_tiempo === d.entregas.total ? 'ok' : 'aviso',
                }
              : { texto: 'Sin entregas', tono: 'gris' }
          }
          contexto={
            d.entregas.tarde.length
              ? `Tarde: ${d.entregas.tarde.join(', ')}.`
              : d.entregas.total
                ? 'Todas las órdenes terminadas llegaron a su fecha.'
                : `Ninguna orden con fecha terminó ${n.este}.`
          }
        />
        <KpiCard
          label="Tiempo parado"
          valor={fmtDuracion(d.paradas.minutos)}
          estado={{
            texto: `${conSigno(Math.round((d.paradas.minutos - d.anterior.paradas_min) / 6) / 10, ' h')} vs ${n.corto}`,
            tono: d.paradas.minutos <= d.anterior.paradas_min ? 'ok' : 'mal',
          }}
          contexto={
            d.paradas.numero
              ? `${plural(d.paradas.numero, 'parada', 'paradas')}. Media: ${fmtDuracion(d.paradas.media_min)} por parada.`
              : 'Ninguna incidencia ha parado un puesto.'
          }
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        <Seccion
          titulo={ef ? `¿De dónde sale el ${fmtNum(ef.oee)} %?` : '¿De dónde sale la eficiencia?'}
          subtitulo="Eficiencia = tiempo en marcha × velocidad × piezas buenas. La barra más corta frente a su objetivo es la que más resta."
        >
          {factores.length === 0 ? (
            <p className="m-0 text-sm text-p-texto2">Sin producción medida en el periodo.</p>
          ) : (
            <div className="flex flex-col gap-5">
              {factores.map((f) => (
                <div key={f.clave} className="flex flex-col gap-1.5">
                  <div className="flex items-baseline justify-between gap-3">
                    <p className="m-0 text-sm font-semibold">
                      {f.titulo} <span className="font-normal text-p-etiqueta">{f.sub}</span>
                      {peorFactor?.clave === f.clave && (
                        <span className="ml-2">
                          <Pastilla tono="aviso">Lo que más resta</Pastilla>
                        </span>
                      )}
                    </p>
                    <span className="text-2xl font-extrabold">{fmtNum(f.valor)} %</span>
                  </div>
                  <BarraObjetivo
                    pct={f.valor}
                    objetivo={f.objetivo}
                    tono={tonoObjetivo(f.valor, f.objetivo)}
                    etiqueta={`${f.titulo}: ${fmtNum(f.valor)} %, objetivo ${fmtNum(f.objetivo)} %`}
                  />
                  <p className="m-0 text-[13px] text-p-texto2">{f.nota}</p>
                </div>
              ))}
              <p className="m-0 text-xs text-p-etiqueta">La raya negra marca el objetivo de cada factor.</p>
            </div>
          )}
        </Seccion>

        <Seccion
          titulo={`Tendencia: ${tendencia.length} semanas`}
          subtitulo={
            conDatos.length >= 2
              ? `De ${fmtNum(conDatos[0].valor)} % a ${fmtNum(conDatos[conDatos.length - 1].valor)} % de eficiencia.`
              : 'Eficiencia semanal. Las semanas sin producción medida quedan en blanco.'
          }
        >
          {conDatos.length === 0 ? (
            <p className="m-0 text-sm text-p-texto2">Aún no hay semanas con producción medida.</p>
          ) : (
            <GraficoLinea
              puntos={tendencia}
              formato={(v) => `${fmtNum(v)} %`}
              objetivo={obj.oee}
              etiquetaObjetivo={`Objetivo ${fmtNum(obj.oee)} %`}
              descripcion={`Eficiencia semanal de las últimas ${tendencia.length} semanas`}
            />
          )}
        </Seccion>

        <Seccion
          titulo="¿Por qué paramos?"
          subtitulo={
            d.paradas.minutos
              ? `${fmtDuracion(d.paradas.minutos)} parados ${n.este}, por causa.`
              : `Sin paradas registradas ${n.este}.`
          }
        >
          {d.paradas.por_causa.length > 0 && (
            <div className="flex flex-col gap-3">
              {d.paradas.por_causa.map((c, i) => (
                <div key={c.causa} className="grid grid-cols-[140px_1fr_auto] items-center gap-3 text-sm">
                  <span className="first-letter:uppercase">{c.causa}</span>
                  <div className="h-3 rounded bg-p-linea">
                    <div
                      className={`h-full rounded ${i === 0 ? 'bg-p-mal' : 'bg-p-aviso'}`}
                      style={{ width: `${(c.minutos / maxParada) * 100}%` }}
                    />
                  </div>
                  <span className="font-bold whitespace-nowrap">
                    {fmtDuracion(c.minutos)}{' '}
                    <span className="font-normal text-p-etiqueta">{fmtNum(c.pct)} %</span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </Seccion>

        <Seccion
          titulo="¿Qué puesto frena la planta?"
          subtitulo={`Eficiencia de cada puesto ${n.este}. La raya negra es el objetivo (${fmtNum(obj.oee)} %).`}
        >
          {d.puestos.length === 0 ? (
            <p className="m-0 text-sm text-p-texto2">Sin puestos con producción medida y ritmo nominal.</p>
          ) : (
            <div className="flex flex-col gap-2.5">
              {d.puestos.map((p) => {
                const tono = tonoObjetivo(p.oee, obj.oee)
                return (
                  <div key={p.puesto} className="grid grid-cols-[80px_1fr_52px] items-center gap-3 text-sm">
                    <span className="font-semibold">{p.puesto}</span>
                    <BarraObjetivo
                      pct={p.oee}
                      objetivo={obj.oee}
                      tono={tono}
                      etiqueta={`${p.puesto}: ${fmtNum(p.oee)} %`}
                    />
                    <span className={`text-right font-bold ${CLASES_TONO[tono].texto}`}>{fmtNum(p.oee)} %</span>
                  </div>
                )
              })}
            </div>
          )}
        </Seccion>
      </div>

      <Seccion
        titulo="¿Qué entregas están en peligro?"
        subtitulo="Horas de trabajo que le faltan a cada orden frente a las horas que quedan hasta su entrega."
        accion={
          <span className="text-[13px] text-p-etiqueta">
            {enPeligro
              ? `${plural(enPeligro, 'orden en peligro', 'órdenes en peligro')} de ${fmtNum(d.ordenes.length)}`
              : 'Todas a tiempo'}
          </span>
        }
      >
        {d.ordenes.length === 0 ? (
          <p className="m-0 text-sm text-p-texto2">No hay órdenes activas con fecha de entrega y ritmo.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-p-etiqueta">
                  <th className="py-2 pr-3 font-semibold">Orden</th>
                  <th className="py-2 pr-3 font-semibold">Producto</th>
                  <th className="py-2 pr-3 font-semibold">Entrega</th>
                  <th className="py-2 pr-3 font-semibold min-w-[220px]">Le faltan / quedan</th>
                  <th className="py-2 font-semibold">Estado</th>
                </tr>
              </thead>
              <tbody>
                {d.ordenes.map((o) => {
                  const e = ESTADO_ORDEN[o.estado]
                  const faltan = o.horas_faltan ?? 0
                  const quedan = Math.max(o.horas_quedan ?? 0, 0)
                  return (
                    <tr key={o.numero} className="border-t border-p-linea">
                      <td className="py-2.5 pr-3 font-bold">{o.numero}</td>
                      <td className="py-2.5 pr-3 text-p-texto2">{o.producto ?? '—'}</td>
                      <td className="py-2.5 pr-3 text-p-texto2 whitespace-nowrap">
                        {o.entrega ? fmtEntrega(o.entrega) : 'Sin fecha'}
                      </td>
                      <td className="py-2.5 pr-3">
                        <div className="flex items-center gap-3">
                          <div className="flex-1 h-2 rounded-full bg-p-linea">
                            <div
                              className={`h-full rounded-full ${CLASES_TONO[e.tono].solido}`}
                              style={{ width: `${quedan > 0 ? Math.min((faltan / quedan) * 100, 100) : 100}%` }}
                            />
                          </div>
                          <span className="text-xs text-p-etiqueta whitespace-nowrap">
                            {fmtDuracion(faltan * 60)} / {fmtDuracion(quedan * 60)}
                          </span>
                        </div>
                      </td>
                      <td className="py-2.5">
                        <Pastilla tono={e.tono}>{e.texto}</Pastilla>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Seccion>
    </>
  )
}
