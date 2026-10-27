import { COLORES } from './tokens'

export interface PuntoSerie {
  etiqueta: string
  /** null = sin dato ese periodo: no se pinta (no es un cero). */
  valor: number | null
}

const W = 640
const H = 240
const IZQ = 64
const DER = 20
const ARR = 20
const ABA = 200

/** Línea de tendencia en SVG, sin librerías: la serie real en negro, el
 *  objetivo (si lo hay) en azul discontinuo y el último dato destacado.
 */
export function GraficoLinea({
  puntos,
  formato,
  objetivo,
  etiquetaObjetivo,
  descripcion,
}: {
  puntos: PuntoSerie[]
  formato: (n: number) => string
  objetivo?: number | null
  etiquetaObjetivo?: string
  descripcion: string
}) {
  const valores = puntos.flatMap((p) => (p.valor === null ? [] : [p.valor]))
  if (objetivo != null) valores.push(objetivo)
  const min = Math.min(...valores)
  const max = Math.max(...valores)
  const margen = max === min ? Math.abs(max) * 0.1 || 1 : (max - min) * 0.15
  const lo = min - margen
  const hi = max + margen

  const x = (i: number) =>
    puntos.length === 1 ? (IZQ + W - DER) / 2 : IZQ + ((W - DER - IZQ) * i) / (puntos.length - 1)
  const y = (v: number) => ABA - ((v - lo) / (hi - lo)) * (ABA - ARR)

  const conDato = puntos.flatMap((p, i) => (p.valor === null ? [] : [{ i, v: p.valor }]))
  const ultimo = conDato[conDato.length - 1]
  const divisiones = [0, 1, 2, 3].map((k) => lo + ((hi - lo) * k) / 3)

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={descripcion}
      className="w-full h-auto block"
    >
      {divisiones.map((v) => (
        <g key={v}>
          <line x1={IZQ - 8} x2={W - DER} y1={y(v)} y2={y(v)} stroke={COLORES.linea} />
          <text
            x={IZQ - 14}
            y={y(v) + 4}
            fontSize="12"
            fill={COLORES.etiqueta}
            textAnchor="end"
          >
            {formato(v)}
          </text>
        </g>
      ))}
      {objetivo != null && (
        <g>
          <line
            x1={IZQ - 8}
            x2={W - DER}
            y1={y(objetivo)}
            y2={y(objetivo)}
            stroke={COLORES.plan}
            strokeWidth="2"
            strokeDasharray="6 5"
          />
          <text x={IZQ} y={y(objetivo) - 8} fontSize="12" fontWeight="600" fill={COLORES.plan}>
            {etiquetaObjetivo ?? `Objetivo ${formato(objetivo)}`}
          </text>
        </g>
      )}
      {conDato.length > 1 && (
        <polyline
          points={conDato.map(({ i, v }) => `${x(i)},${y(v)}`).join(' ')}
          fill="none"
          stroke={COLORES.texto}
          strokeWidth="3"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      )}
      {conDato.map(({ i, v }) => (
        <circle key={i} cx={x(i)} cy={y(v)} r="3.5" fill={COLORES.texto} />
      ))}
      {ultimo && (
        <g>
          <circle
            cx={x(ultimo.i)}
            cy={y(ultimo.v)}
            r="6"
            fill={COLORES.texto}
            stroke={COLORES.tarjeta}
            strokeWidth="2"
          />
          <text
            x={x(ultimo.i) - 12}
            y={y(ultimo.v) - 12}
            fontSize="13"
            fontWeight="700"
            fill={COLORES.texto}
            textAnchor="end"
          >
            {formato(ultimo.v)}
          </text>
        </g>
      )}
      {puntos.map((p, i) => (
        <text
          key={p.etiqueta}
          x={x(i)}
          y={ABA + 22}
          fontSize="12"
          fill={COLORES.etiqueta}
          textAnchor="middle"
        >
          {p.etiqueta}
        </text>
      ))}
    </svg>
  )
}
