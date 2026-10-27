import type { PanelTurno } from '../lib/api'
import { fmtDuracion, fmtEntrega, fmtNum, plural } from '../panel/formato'
import { GraficoTurno, LeyendaTurno } from '../panel/GraficoTurno'
import type { Tono } from '../panel/tokens'
import { CLASES_TONO } from '../panel/tokens'
import {
  ESTADO_ORDEN,
  ESTADO_PUESTO,
  FACTOR_OEE,
  estadoTurno,
  ritmoTurno,
  tiempoPuesto,
} from '../panel/turno'
import { BarraProgreso, EstadoBanner, KpiCard, Pastilla, Seccion } from '../panel/ui'

export type DestinoTurno = 'incidencias' | 'ordenes' | 'puestos'

const URGENCIA: Record<PanelTurno['pendientes'][number]['urgencia'], { texto: string; tono: Tono }> = {
  urgente: { texto: 'Urgente', tono: 'mal' },
  hoy: { texto: 'Hoy', tono: 'aviso' },
  revisar: { texto: 'Revisar', tono: 'gris' },
}

// El stock lo repone Materias Primas desde su panel: aquí no lleva botón
const ACCION: Record<
  PanelTurno['pendientes'][number]['accion'],
  { texto: string; destino: DestinoTurno } | null
> = {
  incidencia: { texto: 'Ver incidencia', destino: 'incidencias' },
  stock: null,
  orden: { texto: 'Ver orden', destino: 'ordenes' },
  puesto: { texto: 'Ver puesto', destino: 'puestos' },
}

const HORA_INICIO = { A: 6, B: 14, C: 22 } as const

/** Vista Turno del panel de mando: lo que necesita el jefe de turno para
 *  saber si llega al plan y qué tiene que resolver ahora mismo.
 */
export function VistaTurno({
  datos,
  error,
  onIr,
}: {
  datos: PanelTurno | null
  error: string
  onIr: (destino: DestinoTurno) => void
}) {
  if (!datos) {
    return (
      <p className="m-0 text-sm text-p-texto2">
        {error ? `No se pudo cargar el turno: ${error}` : 'Cargando el turno…'}
      </p>
    )
  }
  const d = datos
  const estado = estadoTurno(d)
  const ritmo = ritmoTurno(d)
  const restante = d.turno.duracion_min - d.turno.transcurrido_min
  const pctTurno = (d.turno.transcurrido_min / d.turno.duracion_min) * 100

  const ef = d.eficiencia
  const objOee = d.objetivos.oee
  const tonoOee: Tono = !ef ? 'gris' : ef.oee >= objOee ? 'ok' : ef.oee >= objOee - 10 ? 'aviso' : 'mal'

  const chatarraPct = d.chatarra.pct
  const tonoChatarra: Tono =
    chatarraPct === null ? 'gris' : chatarraPct <= d.objetivos.chatarra_max_pct ? 'ok' : 'mal'

  const abiertas = d.puestos.filter((p) => p.estado === 'parado').length
  const tonoParadas: Tono = d.paradas.numero === 0 ? 'ok' : abiertas > 0 ? 'mal' : 'aviso'

  const recuento = (['en_marcha', 'sin_registrar', 'parado', 'preparado', 'sin_orden'] as const)
    .map((e) => ({ e, n: d.puestos.filter((p) => p.estado === e).length }))
    .filter((r) => r.n > 0)

  return (
    <>
      {error && (
        <p className="m-0 text-sm text-p-mal">Sin conexión: se muestran los últimos datos. {error}</p>
      )}
      <EstadoBanner
        tono={estado.tono}
        titular={estado.titular}
        detalle={estado.detalle}
        progreso={{
          pct: pctTurno,
          texto: `Turno transcurrido ${fmtNum(pctTurno)} % · quedan ${fmtDuracion(restante)}`,
        }}
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard
          label="Piezas buenas"
          valor={fmtNum(d.piezas)}
          unidad={d.plan_turno !== null ? `de ${fmtNum(d.plan_turno)}` : undefined}
          estado={ritmo ?? { texto: 'Sin plan', tono: 'gris' }}
          barra={
            d.plan_turno ? { pct: (d.piezas / d.plan_turno) * 100, tono: ritmo?.tono ?? 'gris' } : undefined
          }
          contexto={
            d.plan_ahora !== null
              ? `Plan a esta hora: ${fmtNum(d.plan_ahora)}.` +
                (d.prevision_cierre !== null && d.plan_turno
                  ? ` Previsión de cierre: ${fmtNum(d.prevision_cierre)} (${fmtNum((d.prevision_cierre / d.plan_turno) * 100)} %).`
                  : '')
              : 'Sin ritmo nominal en los puestos con orden: no hay plan.'
          }
        />
        <KpiCard
          label="Eficiencia del turno"
          valor={ef ? `${fmtNum(ef.oee)} %` : '--'}
          unidad={`objetivo ${fmtNum(objOee)} %`}
          estado={
            ef
              ? { texto: tonoOee === 'ok' ? 'En objetivo' : 'Por debajo', tono: tonoOee }
              : { texto: 'Sin datos', tono: 'gris' }
          }
          barra={ef ? { pct: ef.oee, tono: tonoOee } : undefined}
          contexto={
            ef
              ? `En marcha ${fmtNum(ef.disponibilidad)} % · velocidad ${fmtNum(ef.rendimiento)} % · calidad ${fmtNum(ef.calidad)} %. Lo que más resta: ${FACTOR_OEE[ef.mas_resta]}.`
              : 'Se calcula cuando hay plan del turno.'
          }
        />
        <KpiCard
          label="Tiempo parado"
          valor={fmtDuracion(d.paradas.minutos)}
          estado={{
            texto: d.paradas.numero === 0 ? 'Sin paradas' : plural(d.paradas.numero, 'parada', 'paradas'),
            tono: tonoParadas,
          }}
          contexto={
            d.paradas.mayor
              ? `La mayor: ${d.paradas.mayor.puesto}, ${d.paradas.mayor.motivo}, ${fmtDuracion(d.paradas.mayor.minutos)}${d.paradas.mayor.abierta ? ' y sigue abierta' : ''}.`
              : 'Ninguna incidencia ha parado un puesto en este turno.'
          }
        />
        <KpiCard
          label="Chatarra"
          valor={chatarraPct !== null ? `${fmtNum(chatarraPct, 1)} %` : '--'}
          unidad={`${fmtNum(d.chatarra.kg, 1)} kg`}
          estado={
            chatarraPct === null
              ? { texto: 'Sin consumo', tono: 'gris' }
              : { texto: tonoChatarra === 'ok' ? 'Correcto' : 'Por encima', tono: tonoChatarra }
          }
          contexto={`Objetivo: por debajo del ${fmtNum(d.objetivos.chatarra_max_pct, 1)} % del material.`}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)] gap-6 items-start">
        <Seccion
          titulo="¿Llego al plan del turno?"
          subtitulo="Piezas buenas acumuladas frente al plan, con la previsión de cierre."
          accion={<LeyendaTurno />}
        >
          <GraficoTurno
            serie={d.serie}
            duracionMin={d.turno.duracion_min}
            horaInicio={HORA_INICIO[d.turno.codigo]}
            transcurridoMin={d.turno.transcurrido_min}
            planTurno={d.plan_turno}
            prevision={d.prevision_cierre}
          />
        </Seccion>

        <Seccion
          titulo="Pendiente de actuar"
          accion={
            <span className="text-[13px] text-p-etiqueta">
              {d.pendientes.length === 0
                ? 'Nada pendiente'
                : `${plural(d.pendientes.length, 'aviso', 'avisos')} · por urgencia`}
            </span>
          }
        >
          {d.pendientes.length === 0 ? (
            <p className="m-0 text-sm text-p-texto2">
              Sin incidencias abiertas, stock por encima del mínimo y órdenes a tiempo.
            </p>
          ) : (
            <ul className="m-0 p-0 list-none flex flex-col gap-2.5">
              {d.pendientes.map((p) => {
                const u = URGENCIA[p.urgencia]
                const a = ACCION[p.accion]
                return (
                  <li
                    key={`${p.accion}-${p.ref}`}
                    className={`flex items-start gap-3 rounded-[10px] border p-3 ${CLASES_TONO[u.tono].fondo} ${CLASES_TONO[u.tono].borde}`}
                  >
                    <span
                      className={`flex-none text-[11px] font-bold uppercase tracking-wide text-white px-2 py-0.5 rounded ${CLASES_TONO[u.tono].solido}`}
                    >
                      {u.texto}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="m-0 text-sm font-bold text-p-texto">{p.titulo}</p>
                      <p className="m-0 mt-0.5 text-[13px] leading-snug text-p-texto2">
                        {p.detalle}
                        {p.minutos !== null && p.accion === 'incidencia' && ` Abierta hace ${fmtDuracion(p.minutos)}.`}
                      </p>
                    </div>
                    {a && <button
                      type="button"
                      onClick={() => onIr(a.destino)}
                      className="flex-none min-h-[36px] px-3 rounded-lg border border-p-borde bg-p-tarjeta text-[13px] font-semibold text-p-texto cursor-pointer hover:border-p-texto2"
                    >
                      {a.texto}
                    </button>}
                  </li>
                )
              })}
            </ul>
          )}
        </Seccion>
      </div>

      <Seccion
        id="puestos-turno"
        titulo="Puestos ahora"
        subtitulo="Ordenados por el flujo de la planta."
        accion={
          <span className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] font-semibold">
            {recuento.map(({ e, n }) => (
              <span key={e} className={CLASES_TONO[ESTADO_PUESTO[e].tono].texto}>
                {fmtNum(n)} {ESTADO_PUESTO[e].texto.toLowerCase()}
              </span>
            ))}
          </span>
        }
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {d.puestos.map((p) => {
            const e = ESTADO_PUESTO[p.estado]
            const c = CLASES_TONO[e.tono]
            const destacado = e.tono === 'mal' || e.tono === 'aviso'
            const tiempo = tiempoPuesto(p.estado, p.minutos)
            return (
              <article
                key={p.code}
                aria-label={`${p.code}: ${e.texto}`}
                className={`rounded-[10px] border p-3.5 flex flex-col gap-1.5 ${
                  destacado ? `${c.fondo} ${c.borde}` : 'bg-p-tarjeta border-p-borde'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <h3 className="m-0 text-base font-bold text-p-texto">{p.code}</h3>
                  <Pastilla tono={e.tono}>{e.texto}</Pastilla>
                </div>
                <div className="flex items-baseline justify-between gap-2 text-[13px]">
                  <span className="text-p-texto2 truncate">{p.motivo ?? p.grupo ?? p.name}</span>
                  {tiempo && <span className={`flex-none font-semibold ${c.texto}`}>{tiempo}</span>}
                </div>
                {p.orden ? (
                  <>
                    <p className="m-0 text-[13px] font-semibold text-p-texto truncate">
                      {p.orden.numero}
                      {p.orden.producto ? ` · ${p.orden.producto}` : ''}
                    </p>
                    <div className="flex items-center gap-2">
                      <div className="flex-1">
                        <BarraProgreso
                          pct={p.orden.objetivo ? (p.orden.piezas / p.orden.objetivo) * 100 : 0}
                          tono={e.tono === 'gris' ? 'gris' : e.tono}
                          etiqueta={`Avance de ${p.orden.numero} en ${p.code}`}
                        />
                      </div>
                      <span className="text-xs text-p-etiqueta">
                        {fmtNum(p.orden.piezas)} / {fmtNum(p.orden.objetivo)}
                      </span>
                    </div>
                  </>
                ) : (
                  <p className="m-0 text-[13px] text-p-etiqueta">Sin orden asignada</p>
                )}
              </article>
            )
          })}
        </div>
      </Seccion>

      <Seccion
        id="ordenes-turno"
        titulo="Órdenes en curso"
        subtitulo="Primero las que van tarde: horas de trabajo que faltan frente a las que quedan hasta la entrega."
      >
        {d.ordenes.length === 0 ? (
          <p className="m-0 text-sm text-p-texto2">No hay órdenes activas.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-p-etiqueta">
                  <th className="py-2 pr-3 font-semibold">Orden</th>
                  <th className="py-2 pr-3 font-semibold">Producto</th>
                  <th className="py-2 pr-3 font-semibold">Puesto</th>
                  <th className="py-2 pr-3 font-semibold min-w-[180px]">Avance</th>
                  <th className="py-2 pr-3 font-semibold">Entrega</th>
                  <th className="py-2 font-semibold">Estado</th>
                </tr>
              </thead>
              <tbody>
                {d.ordenes.map((o) => {
                  const e = ESTADO_ORDEN[o.estado]
                  return (
                    <tr key={o.numero} className="border-t border-p-linea">
                      <td className="py-2.5 pr-3 font-bold">{o.numero}</td>
                      <td className="py-2.5 pr-3 text-p-texto2">{o.producto ?? '—'}</td>
                      <td className="py-2.5 pr-3 text-p-texto2">{o.puesto ?? '—'}</td>
                      <td className="py-2.5 pr-3">
                        <div className="flex items-center gap-3">
                          <div className="flex-1">
                            <BarraProgreso
                              pct={o.objetivo ? (o.piezas / o.objetivo) * 100 : 0}
                              tono={e.tono}
                              etiqueta={`Avance de ${o.numero}`}
                            />
                          </div>
                          <span className="text-xs text-p-etiqueta whitespace-nowrap">
                            {fmtNum(o.piezas)} / {fmtNum(o.objetivo)}
                          </span>
                        </div>
                      </td>
                      <td className="py-2.5 pr-3 text-p-texto2 whitespace-nowrap">
                        {o.entrega ? fmtEntrega(o.entrega) : 'Sin fecha'}
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

      <p className="m-0 text-xs text-p-etiqueta">
        Se actualiza cada 30 s. El plan sale del ritmo nominal de cada puesto con orden asignada.
      </p>
    </>
  )
}
