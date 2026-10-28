import type { FichaOrden as Ficha } from '../lib/api'

const PLAZO: Record<Ficha['plazo'], { texto: string; clase: string }> = {
  a_tiempo: { texto: 'A tiempo', clase: 'bg-p-ok-bg text-p-ok border-p-ok-borde' },
  en_riesgo: { texto: 'En riesgo', clase: 'bg-p-aviso-bg text-p-aviso border-p-aviso-borde' },
  retraso: { texto: 'Con retraso', clase: 'bg-p-mal-bg text-p-mal border-p-mal-borde' },
  sin_plazo: { texto: 'Sin fecha de entrega', clase: 'bg-p-fondo text-p-texto2 border-p-borde' },
}

const fmt = (n: number, dec = 0) => n.toLocaleString('es-ES', { maximumFractionDigits: dec })

function fechaEntrega(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('es-ES', { weekday: 'short', day: 'numeric', month: 'short' })
}

/** Tarjeta de la orden, siempre arriba en el panel de operario (maqueta
 *  aprobada por Jorge, 28-10): lo que necesita saber sin buscarlo. */
export function FichaOrden({
  ficha,
  numero,
  acciones,
}: {
  ficha: Ficha | null
  numero: string | null
  acciones?: React.ReactNode
}) {
  const plazo = ficha ? PLAZO[ficha.plazo] : null
  // Las medidas se añaden solo si el nombre del material no las trae ya
  const nombre = ficha?.material_nombre ?? ficha?.material ?? null
  const yaTraeMedidas = Boolean(ficha?.ancho_mm && nombre?.includes(String(Math.round(ficha.ancho_mm))))
  const material = ficha
    ? [
        nombre,
        ficha.ancho_mm && ficha.espesor_mm && !yaTraeMedidas
          ? `${fmt(ficha.ancho_mm, 1)} × ${fmt(ficha.espesor_mm, 2)} mm`
          : null,
      ]
        .filter(Boolean)
        .join(' · ')
    : null
  const pct = ficha && ficha.total > 0 ? Math.min((ficha.hechas / ficha.total) * 100, 100) : 0

  return (
    <section aria-label="Orden en curso" className="bg-p-tarjeta border border-p-borde rounded-2xl px-6 py-4 space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2">
        <h1 className="text-2xl font-extrabold">{ficha?.numero ?? numero ?? 'Sin orden'}</h1>
        {ficha?.cliente && <span className="text-base text-p-texto2">{ficha.cliente}</span>}
        <span className="flex-1" />
        {plazo && (
          <span className={`text-sm font-semibold rounded-full border px-3 py-1 ${plazo.clase}`}>
            {plazo.texto}
            {ficha?.fecha_entrega ? ` · entrega ${fechaEntrega(ficha.fecha_entrega)}` : ''}
          </span>
        )}
        {acciones}
      </div>
      {ficha && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <Dato etiqueta="Modelo" valor={ficha.modelo ?? '—'} detalle={ficha.modelo_nombre} />
          <Dato etiqueta="Material" valor={material || '—'} />
          <Dato etiqueta="Largo de pieza" valor={ficha.largo_mm ? `${fmt(ficha.largo_mm)} mm` : '—'} />
          <Dato etiqueta="Ritmo previsto" valor={ficha.ritmo ? `${fmt(ficha.ritmo)} pzs/h` : '—'} />
          <div className="flex flex-col gap-1.5">
            <span className="text-sm text-p-texto2">
              Hechas <b className="text-lg text-p-texto">{fmt(ficha.hechas)}</b> de {fmt(ficha.total)}
              {ficha.faltan > 0 ? ` · faltan ${fmt(ficha.faltan)}` : ' · completa'}
            </span>
            <div
              className="h-2.5 rounded-full bg-p-linea"
              role="progressbar"
              aria-label="Progreso de la orden"
              aria-valuenow={Math.round(pct)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div className="h-2.5 rounded-full bg-p-ok" style={{ width: `${pct}%` }} />
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

function Dato({ etiqueta, valor, detalle }: { etiqueta: string; valor: string; detalle?: string | null }) {
  return (
    <div className="flex flex-col gap-0.5 min-w-0">
      <span className="text-sm text-p-texto2">{etiqueta}</span>
      <span className="text-lg font-bold leading-snug line-clamp-2" title={detalle ?? valor}>
        {valor}
      </span>
    </div>
  )
}
