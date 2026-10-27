import { COLORES } from './tokens'
import { fmtNum } from './formato'

const W = 760
const H = 300
const IZQ = 56
const DER = 24
const ARR = 24
const ABA = 264

/** ¿Llego al plan del turno? Piezas acumuladas (negro), plan lineal (azul
 *  discontinuo) y previsión de cierre al ritmo de la última hora (gris
 *  punteado), con la raya de "ahora". Sin librerías, en SVG.
 */
export function GraficoTurno({
  serie,
  duracionMin,
  horaInicio,
  transcurridoMin,
  planTurno,
  prevision,
}: {
  serie: { minuto: number; piezas: number }[]
  duracionMin: number
  /** Hora de planta en que empieza el turno (6, 14 o 22). */
  horaInicio: number
  transcurridoMin: number
  planTurno: number | null
  prevision: number | null
}) {
  const actual = serie.length ? serie[serie.length - 1].piezas : 0
  const tope = Math.max(planTurno ?? 0, prevision ?? 0, actual, 10) * 1.08
  const x = (min: number) => IZQ + ((W - DER - IZQ) * min) / duracionMin
  const y = (v: number) => ABA - (v / tope) * (ABA - ARR)
  const divisiones = [0, 1, 2, 3, 4].map((k) => (tope / 1.08) * (k / 4))
  const horas = Array.from({ length: duracionMin / 60 + 1 }, (_, i) => i)
  const ahoraX = x(transcurridoMin)

  const descripcion =
    `Piezas buenas acumuladas: ${fmtNum(actual)}` +
    (planTurno != null ? `, plan del turno ${fmtNum(planTurno)}` : ', sin plan') +
    (prevision != null ? `, previsión de cierre ${fmtNum(prevision)}` : '')

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={descripcion} className="w-full h-auto block">
      {divisiones.map((v) => (
        <g key={v}>
          <line x1={IZQ} x2={W - DER} y1={y(v)} y2={y(v)} stroke={COLORES.linea} />
          <text x={IZQ - 10} y={y(v) + 4} fontSize="12" fill={COLORES.etiqueta} textAnchor="end">
            {fmtNum(Math.round(v))}
          </text>
        </g>
      ))}
      {horas.map((h) => (
        <text
          key={h}
          x={x(h * 60)}
          y={ABA + 22}
          fontSize="12"
          fill={COLORES.etiqueta}
          textAnchor="middle"
        >
          {String((horaInicio + h) % 24).padStart(2, '0')}:00
        </text>
      ))}
      {planTurno != null && (
        <line
          x1={x(0)}
          y1={y(0)}
          x2={x(duracionMin)}
          y2={y(planTurno)}
          stroke={COLORES.plan}
          strokeWidth="2"
          strokeDasharray="7 5"
        />
      )}
      {prevision != null && (
        <g>
          <line
            x1={ahoraX}
            y1={y(actual)}
            x2={x(duracionMin)}
            y2={y(prevision)}
            stroke={COLORES.prevision}
            strokeWidth="2"
            strokeDasharray="2 4"
          />
          <circle
            cx={x(duracionMin)}
            cy={y(prevision)}
            r="5"
            fill={COLORES.tarjeta}
            stroke={COLORES.prevision}
            strokeWidth="2"
          />
          <text
            x={x(duracionMin) - 10}
            y={y(prevision) - 12}
            fontSize="12"
            fill={COLORES.texto2}
            textAnchor="end"
          >
            Cierre previsto {fmtNum(prevision)}
          </text>
        </g>
      )}
      <line
        x1={ahoraX}
        x2={ahoraX}
        y1={ARR}
        y2={ABA}
        stroke={COLORES.etiqueta}
        strokeDasharray="3 3"
      />
      <polyline
        points={serie.map((p) => `${x(p.minuto)},${y(p.piezas)}`).join(' ')}
        fill="none"
        stroke={COLORES.texto}
        strokeWidth="3"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={ahoraX} cy={y(actual)} r="6" fill={COLORES.texto} stroke={COLORES.tarjeta} strokeWidth="2" />
      <g transform={`translate(${Math.min(ahoraX + 12, W - DER - 132)}, ${Math.max(y(actual) - 38, ARR)})`}>
        <rect width="132" height="28" rx="6" fill={COLORES.texto} />
        <text x="66" y="19" fontSize="13" fontWeight="700" fill="#FFFFFF" textAnchor="middle">
          Ahora · {fmtNum(actual)} pzs
        </text>
      </g>
    </svg>
  )
}

/** Leyenda del gráfico del turno (texto, nunca solo color). */
export function LeyendaTurno() {
  return (
    <div className="flex flex-wrap gap-4 text-[13px] text-p-texto2" aria-hidden="true">
      <span className="inline-flex items-center gap-2">
        <span className="w-5 h-[3px] bg-p-texto rounded" /> Real
      </span>
      <span className="inline-flex items-center gap-2">
        <span className="w-5 border-t-2 border-dashed border-p-plan" /> Plan
      </span>
      <span className="inline-flex items-center gap-2">
        <span className="w-5 border-t-2 border-dotted border-[#8A93A0]" /> Previsión
      </span>
    </div>
  )
}
