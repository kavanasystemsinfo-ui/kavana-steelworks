import type { ReactNode } from 'react'
import { CLASES_TONO, type Tono } from './tokens'

/** Bloque del panel. El título es la pregunta que responde ("¿Llego al plan?"):
 *  quien lo mira sabe para qué sirve sin que nadie se lo explique.
 */
export function Seccion({
  titulo,
  subtitulo,
  accion,
  className = '',
  id,
  children,
}: {
  titulo: string
  subtitulo?: ReactNode
  accion?: ReactNode
  className?: string
  id?: string
  children: ReactNode
}) {
  return (
    <section
      id={id}
      aria-label={titulo}
      className={`bg-p-tarjeta border border-p-borde rounded-[14px] p-5 sm:px-6 flex flex-col gap-4 min-w-0 ${className}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-5 gap-y-2">
        <div className="min-w-0">
          <h2 className="m-0 text-lg font-bold text-p-texto">{titulo}</h2>
          {subtitulo && <p className="m-0 mt-1 text-sm text-p-texto2">{subtitulo}</p>}
        </div>
        {accion}
      </div>
      {children}
    </section>
  )
}

/** Etiqueta de estado: texto en el color del tono sobre su fondo. */
export function Pastilla({ tono, children }: { tono: Tono; children: ReactNode }) {
  const c = CLASES_TONO[tono]
  return (
    <span
      className={`inline-block whitespace-nowrap text-xs font-bold px-2.5 py-1 rounded-full ${c.texto} ${c.fondo}`}
    >
      {children}
    </span>
  )
}

/** Barra de avance 0-100 (se recorta a ese rango). */
export function BarraProgreso({
  pct,
  tono = 'gris',
  alto = 'h-1.5',
  etiqueta,
}: {
  pct: number
  tono?: Tono
  alto?: string
  etiqueta?: string
}) {
  const ancho = Math.max(0, Math.min(100, pct))
  return (
    <div
      className={`${alto} rounded-full bg-p-linea overflow-hidden`}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(ancho)}
      aria-label={etiqueta}
    >
      <div className={`h-full rounded-full ${CLASES_TONO[tono].solido}`} style={{ width: `${ancho}%` }} />
    </div>
  )
}

/** Indicador clave: cifra grande y siempre con su referencia (objetivo,
 *  periodo anterior...). Un número sin contexto obliga a explicarlo.
 */
export function KpiCard({
  label,
  valor,
  unidad,
  estado,
  barra,
  contexto,
}: {
  label: string
  valor: string
  unidad?: string
  estado?: { texto: string; tono: Tono }
  barra?: { pct: number; tono: Tono }
  contexto?: ReactNode
}) {
  return (
    <article className="bg-p-tarjeta border border-p-borde rounded-[14px] p-5 flex flex-col gap-2.5 min-w-0">
      <div className="flex items-center justify-between gap-2">
        <h3 className="m-0 text-sm font-semibold text-p-texto2">{label}</h3>
        {estado && <Pastilla tono={estado.tono}>{estado.texto}</Pastilla>}
      </div>
      <p className="m-0 flex flex-wrap items-baseline gap-2">
        <span className="text-[40px] leading-none font-extrabold tracking-tight text-p-texto">
          {valor}
        </span>
        {unidad && <span className="text-base font-medium text-p-etiqueta">{unidad}</span>}
      </p>
      {barra && <BarraProgreso pct={barra.pct} tono={barra.tono} />}
      {contexto && <div className="text-[13px] leading-snug text-p-texto2">{contexto}</div>}
    </article>
  )
}

const ICONO_TONO: Record<Tono, ReactNode> = {
  ok: <path d="M5 12l5 5 9-10" />,
  aviso: (
    <>
      <path d="M12 3 2 21h20L12 3z" />
      <path d="M12 10v4M12 17.5v.5" />
    </>
  ),
  mal: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v6M12 16.5v.5" />
    </>
  ),
  gris: <path d="M5 12h14" />,
}

/** Frase de estado en lenguaje de planta, arriba del todo de cada vista. */
export function EstadoBanner({
  tono,
  titular,
  detalle,
  progreso,
}: {
  tono: Tono
  titular: string
  detalle?: ReactNode
  progreso?: { pct: number; texto: string }
}) {
  const c = CLASES_TONO[tono]
  return (
    <section
      aria-label="Estado"
      className={`${c.fondo} border ${c.borde} rounded-[14px] px-6 py-5 flex flex-wrap items-center gap-x-7 gap-y-4`}
    >
      <span
        className={`flex-none flex items-center justify-center w-[52px] h-[52px] rounded-full text-white ${c.solido}`}
      >
        <svg
          width="26"
          height="26"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          {ICONO_TONO[tono]}
        </svg>
      </span>
      <div className="flex-[999_1_420px] min-w-0">
        <p className="m-0 text-2xl sm:text-[26px] font-bold tracking-tight text-p-texto">{titular}</p>
        {detalle && <p className="m-0 mt-1.5 text-base leading-relaxed text-p-texto2">{detalle}</p>}
      </div>
      {progreso && (
        <div className="flex-[1_1_220px] min-w-[200px]">
          <p className="m-0 mb-1.5 text-[13px] font-semibold text-p-texto2">{progreso.texto}</p>
          <BarraProgreso pct={progreso.pct} tono={tono} alto="h-2" />
        </div>
      )}
    </section>
  )
}

/** Selector de periodo (o cualquier opción excluyente) con aria-pressed. */
export function Selector<T extends string>({
  opciones,
  valor,
  onCambio,
  etiqueta,
}: {
  opciones: { valor: T; texto: string }[]
  valor: T
  onCambio: (v: T) => void
  etiqueta: string
}) {
  return (
    <div
      role="group"
      aria-label={etiqueta}
      className="inline-flex gap-1 p-1 bg-p-tarjeta border border-p-borde rounded-[10px]"
    >
      {opciones.map((o) => (
        <button
          key={o.valor}
          type="button"
          aria-pressed={valor === o.valor}
          onClick={() => onCambio(o.valor)}
          className={`min-h-[40px] px-4 rounded-[7px] text-sm cursor-pointer ${
            valor === o.valor
              ? 'bg-p-texto text-white font-semibold'
              : 'bg-transparent text-p-texto2 font-medium hover:text-p-texto'
          }`}
        >
          {o.texto}
        </button>
      ))}
    </div>
  )
}
