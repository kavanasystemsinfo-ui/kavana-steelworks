import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { FichaPuesto as Ficha, PeriodoPlanta, SesionPuesto } from '../lib/api'
import { fechaYHoraPlanta } from '../lib/tiempo'
import { fmtDuracion, fmtNum, horaPlanta } from '../panel/formato'
import type { Tono } from '../panel/tokens'
import { BarraProgreso, EstadoBanner, KpiCard, Pastilla, Seccion, Selector } from '../panel/ui'

const PERIODOS: { valor: PeriodoPlanta; texto: string }[] = [
  { valor: 'hoy', texto: 'Hoy' },
  { valor: 'semana', texto: 'Esta semana' },
  { valor: '8semanas', texto: 'Últimas 8 semanas' },
]

const NOMBRE_PERIODO: Record<PeriodoPlanta, string> = {
  hoy: 'hoy',
  semana: 'esta semana',
  '8semanas': 'en 8 semanas',
}

type EstadoAhora = NonNullable<Ficha['ahora']>['estado']

const ESTADO: Record<EstadoAhora, { texto: string; tono: Tono }> = {
  en_curso: { texto: 'En marcha', tono: 'ok' },
  parado: { texto: 'Parado', tono: 'mal' },
  incidencia: { texto: 'Con incidencia', tono: 'mal' },
  pendiente: { texto: 'Preparado', tono: 'gris' },
  libre: { texto: 'Sin orden', tono: 'gris' },
}

const DIAS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb']

/** "mié 28 · 10:32": día de planta y hora, para sesiones de varios días. */
function diaYHora(iso: string): string {
  const { fecha } = fechaYHoraPlanta(new Date(iso))
  const d = new Date(`${fecha}T12:00:00Z`)
  return `${DIAS[d.getUTCDay()]} ${d.getUTCDate()} · ${horaPlanta(iso)}`
}

function Sesion({
  s,
  abierta,
  onAlternar,
}: {
  s: SesionPuesto
  abierta: boolean
  onAlternar: () => void
}) {
  return (
    <li className="border border-p-borde rounded-[10px] overflow-hidden">
      <button
        type="button"
        aria-expanded={abierta}
        onClick={onAlternar}
        className="w-full text-left bg-p-tarjeta px-4 py-3 cursor-pointer grid grid-cols-1 sm:grid-cols-[1.4fr_1fr_1fr_1fr] gap-x-4 gap-y-1 items-center hover:bg-p-linea"
      >
        <span className="min-w-0">
          <span className="block font-bold text-p-texto truncate">{s.operario}</span>
          <span className="block text-[13px] text-p-texto2">
            {diaYHora(s.inicio)} – {horaPlanta(s.fin)} · {fmtDuracion(s.minutos)}
          </span>
        </span>
        <span className="text-sm">
          <span className="block text-p-etiqueta text-xs">Orden</span>
          {s.orden} · línea {s.linea}
        </span>
        <span className="text-sm">
          <span className="block text-p-etiqueta text-xs">Hizo</span>
          <strong>{fmtNum(s.piezas)}</strong> piezas
          {s.chatarra_kg > 0 && (
            <span className="text-p-aviso"> · {fmtNum(s.chatarra_kg, 1)} kg de chatarra</span>
          )}
        </span>
        <span className="text-sm">
          <span className="block text-p-etiqueta text-xs">Bobinas</span>
          {s.bobinas.length ? s.bobinas.join(', ') : 'Sin bobina registrada'}
        </span>
      </button>
      {abierta && (
        <div className="overflow-x-auto border-t border-p-linea bg-p-fondo px-4 py-2">
          <table
            className="w-full text-sm border-collapse"
            aria-label={`Registros de la sesión de ${s.operario}`}
          >
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-p-etiqueta">
                <th className="py-1.5 pr-3 font-semibold">Hora</th>
                <th className="py-1.5 pr-3 font-semibold">Qué</th>
                <th className="py-1.5 pr-3 font-semibold text-right">Cantidad</th>
                <th className="py-1.5 font-semibold">Bobina</th>
              </tr>
            </thead>
            <tbody>
              {s.eventos.map((e, i) => (
                <tr key={`${e.hora}-${i}`} className="border-t border-p-linea">
                  <td className="py-1.5 pr-3 whitespace-nowrap">{horaPlanta(e.hora)}</td>
                  <td className="py-1.5 pr-3">
                    {e.texto}
                    {e.nota && <span className="text-p-etiqueta"> · {e.nota}</span>}
                  </td>
                  <td className="py-1.5 pr-3 text-right">
                    {e.accion === 'scrap'
                      ? `${fmtNum(e.cantidad, 1)} kg`
                      : e.accion === 'produce'
                        ? `${fmtNum(e.cantidad)} piezas`
                        : '—'}
                  </td>
                  <td className="py-1.5">{e.bobina ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </li>
  )
}

/** Ficha de un puesto: cómo va, por qué y, sobre todo, qué ha hecho cada
 *  operario en él (sesiones con hora, cantidad y bobina). Sin euros.
 */
export function FichaPuesto({ codigo, onVolver }: { codigo: string; onVolver: () => void }) {
  const [periodo, setPeriodo] = useState<PeriodoPlanta>('hoy')
  const [ficha, setFicha] = useState<Ficha | null>(null)
  const [error, setError] = useState('')
  const [abiertas, setAbiertas] = useState<Set<number>>(new Set())

  useEffect(() => {
    let vivo = true
    setError('')
    setAbiertas(new Set())
    api
      .getFichaPuesto(codigo, periodo)
      .then((f) => vivo && setFicha(f))
      .catch((e) => vivo && setError(e instanceof Error ? e.message : 'Error de conexión'))
    return () => {
      vivo = false
    }
  }, [codigo, periodo])

  const cabecera = (
    <>
      <button
        type="button"
        onClick={onVolver}
        className="self-start min-h-[40px] px-3 rounded-[8px] border border-p-borde bg-p-tarjeta text-sm font-semibold cursor-pointer hover:bg-p-linea"
      >
        ← Volver a la planta
      </button>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="m-0 text-[26px] font-bold tracking-tight">
          Puesto {codigo}
          {ficha && ficha.puesto.name !== codigo && (
            <span className="ml-2 text-lg font-medium text-p-texto2">{ficha.puesto.name}</span>
          )}
        </h1>
        <Selector opciones={PERIODOS} valor={periodo} onCambio={setPeriodo} etiqueta="Periodo" />
      </div>
    </>
  )

  if (!ficha || ficha.periodo !== periodo || ficha.puesto.code !== codigo) {
    return (
      <>
        {cabecera}
        <p className="m-0 text-sm text-p-texto2">
          {error ? `No se pudo cargar la ficha: ${error}` : 'Cargando…'}
        </p>
      </>
    )
  }

  const f = ficha
  const ahora = f.ahora
  const est = ahora ? ESTADO[ahora.estado] : ESTADO.libre
  const ef = f.eficiencia
  const maxParada = Math.max(1, ...f.paradas.por_causa.map((c) => c.minutos))
  const cuando = NOMBRE_PERIODO[periodo]

  const detalle = [
    ahora?.orden
      ? `Orden ${ahora.orden.numero}: ${fmtNum(ahora.orden.piezas)} de ${fmtNum(ahora.orden.objetivo)} piezas${
          ahora.orden.bobina ? `, bobina ${ahora.orden.bobina}` : ''
        }.`
      : 'No tiene ninguna orden asignada ahora.',
    ahora?.ultima_actividad
      ? `Último registro: ${ahora.ultima_actividad.operario ?? 'sin operario'}, ${diaYHora(ahora.ultima_actividad.timestamp)}.`
      : 'Todavía no hay registros.',
    ahora?.incidencias_abiertas.length
      ? `Incidencia abierta: ${ahora.incidencias_abiertas[0].descripcion}.`
      : '',
  ]
    .filter(Boolean)
    .join(' ')

  const pctPlan = f.plan ? f.piezas / f.plan : null

  return (
    <>
      {cabecera}
      {error && (
        <p className="m-0 text-sm text-p-mal">Sin conexión: se muestran los últimos datos. {error}</p>
      )}
      <EstadoBanner tono={est.tono} titular={`${codigo} · ${est.texto}`} detalle={detalle} />

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard
          label="Piezas buenas"
          valor={fmtNum(f.piezas)}
          unidad={f.plan ? `de ${fmtNum(f.plan)}` : undefined}
          estado={
            pctPlan !== null
              ? {
                  texto: `${fmtNum(pctPlan * 100)} % del plan`,
                  tono: pctPlan >= 0.95 ? 'ok' : pctPlan >= 0.85 ? 'aviso' : 'mal',
                }
              : { texto: 'Sin plan', tono: 'gris' }
          }
          contexto={
            f.plan
              ? 'Plan: lo que haría el puesto a su ritmo nominal sin paradas.'
              : 'Sin ritmo nominal o sin horas registradas.'
          }
        />
        <KpiCard
          label="Eficiencia (OEE)"
          valor={ef ? `${fmtNum(ef.oee)} %` : '--'}
          contexto={
            ef
              ? `En marcha ${fmtNum(ef.disponibilidad)} % · velocidad ${fmtNum(ef.rendimiento)} % · piezas buenas ${fmtNum(ef.calidad)} %.`
              : 'Sin producción medida en el periodo.'
          }
        />
        <KpiCard
          label="Tiempo parado"
          valor={fmtDuracion(f.paradas.minutos)}
          contexto={
            f.paradas.numero
              ? `${fmtNum(f.paradas.numero)} ${f.paradas.numero === 1 ? 'parada' : 'paradas'} ${cuando}.`
              : `Sin paradas ${cuando}.`
          }
        />
        <KpiCard
          label="Chatarra"
          valor={fmtNum(f.material.chatarra_kg, 1)}
          unidad="kg"
          contexto={
            f.material.chatarra_pct !== null
              ? `${fmtNum(f.material.chatarra_pct, 1)} % de los ${fmtNum(f.material.kg_consumidos + f.material.chatarra_kg)} kg de material.`
              : 'Sin material registrado.'
          }
        />
      </div>

      <Seccion
        titulo="¿Por qué para este puesto?"
        subtitulo={
          f.paradas.minutos
            ? `${fmtDuracion(f.paradas.minutos)} parados ${cuando}, por causa.`
            : `Sin paradas registradas ${cuando}.`
        }
      >
        {f.paradas.por_causa.length > 0 && (
          <div className="flex flex-col gap-3">
            {f.paradas.por_causa.map((c, i) => (
              <div key={c.causa} className="grid grid-cols-[140px_1fr_auto] items-center gap-3 text-sm">
                <span className="first-letter:uppercase">{c.causa}</span>
                <BarraProgreso
                  pct={(c.minutos / maxParada) * 100}
                  tono={i === 0 ? 'mal' : 'aviso'}
                  alto="h-3"
                  etiqueta={`${c.causa}: ${fmtDuracion(c.minutos)}`}
                />
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
        titulo="¿Quién ha trabajado en el puesto y qué ha hecho?"
        subtitulo="Una sesión es el trabajo seguido de un operario en una línea. Pulsa una para ver cada registro con su hora y su bobina."
        accion={
          <Pastilla tono="gris">
            {f.sesiones.length} {f.sesiones.length === 1 ? 'sesión' : 'sesiones'}
          </Pastilla>
        }
      >
        {f.sesiones.length === 0 ? (
          <p className="m-0 text-sm text-p-texto2">Nadie ha registrado trabajo en este puesto {cuando}.</p>
        ) : (
          <ul className="m-0 p-0 list-none flex flex-col gap-2.5">
            {f.sesiones.map((s, i) => (
              <Sesion
                key={`${s.inicio}-${i}`}
                s={s}
                abierta={abiertas.has(i)}
                onAlternar={() =>
                  setAbiertas((prev) => {
                    const sig = new Set(prev)
                    if (sig.has(i)) sig.delete(i)
                    else sig.add(i)
                    return sig
                  })
                }
              />
            ))}
          </ul>
        )}
      </Seccion>
    </>
  )
}
