import { useState } from 'react'
import type { DetallePuesto } from '../lib/api'
import { fmtDuracion, fmtNum } from '../panel/formato'
import { CLASES_TONO, type Tono } from '../panel/tokens'

type Columna = 'puesto' | 'piezas' | 'plan' | 'oee' | 'paradas' | 'chatarra'

const COLUMNAS: { clave: Columna; texto: string; derecha: boolean }[] = [
  { clave: 'puesto', texto: 'Puesto', derecha: false },
  { clave: 'piezas', texto: 'Piezas', derecha: true },
  { clave: 'plan', texto: 'Plan', derecha: true },
  { clave: 'oee', texto: 'Eficiencia', derecha: true },
  { clave: 'paradas', texto: 'Paradas', derecha: true },
  { clave: 'chatarra', texto: 'Chatarra', derecha: true },
]

const valor = (p: DetallePuesto, c: Columna): number | string | null =>
  ({
    puesto: p.puesto,
    piezas: p.piezas,
    plan: p.plan,
    oee: p.eficiencia?.oee ?? null,
    paradas: p.paradas_min,
    chatarra: p.chatarra_kg,
  })[c]

const tonoObjetivo = (v: number, obj: number): Tono =>
  v >= obj ? 'ok' : v >= obj - 10 ? 'aviso' : 'mal'

/** Tabla comparativa de puestos: una fila por puesto, ordenable, con enlace a su ficha.
 *  Por defecto, el de menor eficiencia primero; lo que no tiene dato va siempre al final.
 */
export function TablaPuestos({
  puestos,
  objetivoOee,
  onPuesto,
}: {
  puestos: DetallePuesto[]
  objetivoOee: number
  onPuesto?: (codigo: string) => void
}) {
  const [orden, setOrden] = useState<{ col: Columna; asc: boolean }>({ col: 'oee', asc: true })

  const filas = [...puestos].sort((a, b) => {
    const va = valor(a, orden.col)
    const vb = valor(b, orden.col)
    if (va === null && vb === null) return a.puesto.localeCompare(b.puesto)
    if (va === null) return 1
    if (vb === null) return -1
    const c = typeof va === 'string' ? va.localeCompare(String(vb)) : (va as number) - (vb as number)
    return orden.asc ? c : -c
  })

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-xs uppercase tracking-wide text-p-etiqueta">
            {COLUMNAS.map((c) => (
              <th
                key={c.clave}
                scope="col"
                aria-sort={orden.col === c.clave ? (orden.asc ? 'ascending' : 'descending') : 'none'}
                className={`py-2 pr-3 font-semibold ${c.derecha ? 'text-right' : 'text-left'}`}
              >
                <button
                  type="button"
                  onClick={() =>
                    setOrden((o) => ({
                      col: c.clave,
                      asc: o.col === c.clave ? !o.asc : c.clave === 'puesto' || c.clave === 'oee',
                    }))
                  }
                  className="uppercase tracking-wide font-semibold bg-transparent border-0 p-0 min-h-[32px] cursor-pointer text-inherit"
                >
                  {c.texto}
                  {orden.col === c.clave ? (orden.asc ? ' ▲' : ' ▼') : ''}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filas.map((p) => {
            const oee = p.eficiencia?.oee ?? null
            return (
              <tr key={p.puesto} className="border-t border-p-linea">
                <td className="py-2.5 pr-3">
                  <button
                    type="button"
                    onClick={() => onPuesto?.(p.puesto)}
                    aria-label={`Ver la ficha de ${p.puesto}`}
                    className="font-bold underline decoration-dotted underline-offset-4 bg-transparent border-0 p-0 min-h-[32px] cursor-pointer text-inherit"
                  >
                    {p.puesto}
                  </button>
                </td>
                <td className="py-2.5 pr-3 text-right">{fmtNum(p.piezas)}</td>
                <td className="py-2.5 pr-3 text-right text-p-texto2">{p.plan ? fmtNum(p.plan) : '--'}</td>
                <td
                  className={`py-2.5 pr-3 text-right font-bold ${
                    oee === null ? 'text-p-etiqueta' : CLASES_TONO[tonoObjetivo(oee, objetivoOee)].texto
                  }`}
                >
                  {oee === null ? '--' : `${fmtNum(oee)} %`}
                </td>
                <td className="py-2.5 pr-3 text-right">
                  {p.paradas_n ? `${fmtDuracion(p.paradas_min)} (${p.paradas_n})` : '—'}
                </td>
                <td className="py-2.5 text-right">
                  {p.chatarra_kg > 0
                    ? `${fmtNum(p.chatarra_kg, 1)} kg${p.chatarra_pct !== null ? ` · ${fmtNum(p.chatarra_pct, 1)} %` : ''}`
                    : '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
