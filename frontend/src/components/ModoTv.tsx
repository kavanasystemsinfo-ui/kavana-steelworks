import { useEffect } from 'react'
import type { PanelTurno } from '../lib/api'
import { fmtDuracion, fmtNum, horaPlanta } from '../panel/formato'
import { COLORES_TV, type Tono } from '../panel/tokens'
import { ESTADO_PUESTO, estadoTurno, ritmoTurno } from '../panel/turno'

/** Modo TV: la vista Turno para una pantalla de planta, a varios metros.
 *  Fondo oscuro, cifras enormes y solo lo que se lee de un vistazo: cómo
 *  va el turno, cuatro números y el estado de cada puesto. Esc para salir.
 */
export function ModoTv({ datos, onSalir }: { datos: PanelTurno | null; onSalir: () => void }) {
  useEffect(() => {
    const salir = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onSalir()
    }
    window.addEventListener('keydown', salir)
    return () => window.removeEventListener('keydown', salir)
  }, [onSalir])

  const t = COLORES_TV
  const color = (tono: Tono) => t[tono]

  return (
    <div
      role="dialog"
      aria-label="Modo TV"
      className="fixed inset-0 z-50 overflow-auto font-panel tabular-nums p-6 lg:p-10 flex flex-col gap-6"
      style={{ background: t.fondo, color: t.texto }}
    >
      <div className="flex items-center justify-between gap-4">
        <p className="m-0 text-2xl lg:text-3xl font-extrabold tracking-tight">
          {datos ? `Turno ${datos.turno.codigo}` : 'Turno'}
          <span className="font-medium" style={{ color: t.texto2 }}>
            {' '}
            · {horaPlanta(new Date().toISOString())}
          </span>
        </p>
        <button
          type="button"
          onClick={onSalir}
          className="min-h-[44px] px-4 rounded-lg border text-base font-semibold cursor-pointer"
          style={{ borderColor: t.gris.borde, color: t.texto, background: t.tarjeta }}
        >
          Salir (Esc)
        </button>
      </div>

      {!datos ? (
        <p className="m-0 text-2xl" style={{ color: t.texto2 }}>
          Cargando el turno…
        </p>
      ) : (
        <Contenido datos={datos} color={color} />
      )}
    </div>
  )
}

function Contenido({
  datos: d,
  color,
}: {
  datos: PanelTurno
  color: (tono: Tono) => { bg: string; borde: string; fg: string }
}) {
  const estado = estadoTurno(d)
  const ritmo = ritmoTurno(d)
  const e = color(estado.tono)
  const cifras: { label: string; valor: string; extra: string; tono: Tono }[] = [
    {
      label: 'Piezas buenas',
      valor: fmtNum(d.piezas),
      extra: d.plan_turno !== null ? `de ${fmtNum(d.plan_turno)}` : 'sin plan',
      tono: ritmo?.tono ?? 'gris',
    },
    {
      label: 'Previsión de cierre',
      valor: d.prevision_cierre !== null ? fmtNum(d.prevision_cierre) : '--',
      extra:
        d.prevision_cierre !== null && d.plan_turno
          ? `${fmtNum((d.prevision_cierre / d.plan_turno) * 100)} % del plan`
          : '',
      tono: ritmo?.tono ?? 'gris',
    },
    {
      label: 'Tiempo parado',
      valor: fmtDuracion(d.paradas.minutos),
      extra: d.paradas.numero ? `${fmtNum(d.paradas.numero)} paradas` : 'sin paradas',
      tono: d.paradas.numero === 0 ? 'ok' : d.puestos.some((p) => p.estado === 'parado') ? 'mal' : 'aviso',
    },
    {
      label: 'Eficiencia',
      valor: d.eficiencia ? `${fmtNum(d.eficiencia.oee)} %` : '--',
      extra: `objetivo ${fmtNum(d.objetivos.oee)} %`,
      tono: !d.eficiencia ? 'gris' : d.eficiencia.oee >= d.objetivos.oee ? 'ok' : 'aviso',
    },
  ]

  return (
    <>
      <section
        aria-label="Estado"
        className="rounded-2xl border-2 px-8 py-6"
        style={{ background: e.bg, borderColor: e.borde }}
      >
        <p className="m-0 text-4xl lg:text-5xl font-extrabold tracking-tight" style={{ color: e.fg }}>
          {estado.titular}
        </p>
        <p className="m-0 mt-3 text-xl lg:text-2xl leading-snug">{estado.detalle}</p>
      </section>

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {cifras.map((c) => (
          <div
            key={c.label}
            className="rounded-2xl px-6 py-5"
            style={{ background: COLORES_TV.tarjeta, borderLeft: `8px solid ${color(c.tono).borde}` }}
          >
            <p className="m-0 text-lg font-semibold" style={{ color: COLORES_TV.texto2 }}>
              {c.label}
            </p>
            <p className="m-0 mt-1 text-6xl lg:text-7xl font-extrabold leading-none">{c.valor}</p>
            <p className="m-0 mt-2 text-lg" style={{ color: color(c.tono).fg }}>
              {c.extra}
            </p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
        {d.puestos.map((p) => {
          const est = ESTADO_PUESTO[p.estado]
          const c = color(est.tono)
          return (
            <div
              key={p.code}
              aria-label={`${p.code}: ${est.texto}`}
              className="rounded-xl border-2 px-4 py-3"
              style={{ background: c.bg, borderColor: c.borde }}
            >
              <p className="m-0 text-2xl font-extrabold">{p.code}</p>
              <p className="m-0 mt-1 text-xl font-bold" style={{ color: c.fg }}>
                {est.texto}
                {p.estado === 'parado' && p.minutos !== null ? ` · ${fmtDuracion(p.minutos)}` : ''}
              </p>
              <p className="m-0 mt-1 text-base truncate" style={{ color: COLORES_TV.texto2 }}>
                {p.motivo ?? (p.orden ? `${p.orden.numero} · ${fmtNum(p.orden.piezas)}/${fmtNum(p.orden.objetivo)}` : 'Sin orden')}
              </p>
            </div>
          )
        })}
      </div>
    </>
  )
}
