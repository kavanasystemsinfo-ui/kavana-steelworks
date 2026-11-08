import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { PicoMaterial } from '../lib/api'
import { fmtNum, plural } from '../panel/formato'
import { Seccion } from '../panel/ui'

const dias = (n: number | null) =>
  n === null ? 'sin fecha' : n === 0 ? 'de hoy' : `${plural(n, 'día', 'días')}`

/** Picos acumulados por material (T-046): qué restos hay, cuánto pesan y desde
 *  cuándo, para que el supervisor decida cuándo gastarlos. Si no hay picos o el
 *  servidor no responde, no enseña nada. */
export function PicosAcumulados() {
  const [grupos, setGrupos] = useState<PicoMaterial[] | null>(null)

  useEffect(() => {
    let vigente = true
    api
      .getPicosPorMaterial()
      .then((g) => {
        if (vigente) setGrupos(Array.isArray(g) ? g : [])
      })
      .catch(() => {
        if (vigente) setGrupos([])
      })
    return () => {
      vigente = false
    }
  }, [])

  if (!grupos || grupos.length === 0) return null

  return (
    <Seccion
      titulo="Picos acumulados"
      subtitulo="Restos de bobina que quedan por material. Los operarios los ven primero al elegir bobina."
    >
      <ul className="m-0 p-0 list-none flex flex-col gap-3">
        {grupos.map((g) => (
          <li key={g.material_id} className="border border-p-borde rounded-[10px] p-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="m-0 font-semibold text-p-texto">
                {g.material_code}
                {g.material_name ? <span className="font-normal text-p-texto2"> · {g.material_name}</span> : null}
              </p>
              <p className="m-0 text-sm text-p-texto2">
                {plural(g.picos, 'pico', 'picos')} · {fmtNum(g.kg_total)} kg
                {g.mas_antiguo_dias !== null ? ` · el más antiguo, ${dias(g.mas_antiguo_dias)}` : ''}
              </p>
            </div>
            <ul className="m-0 mt-2 p-0 list-none text-sm text-p-texto2 space-y-0.5">
              {g.items.map((i) => (
                <li key={i.id} className="flex justify-between gap-2">
                  <span>
                    {i.coil_id ?? i.lote} · en {i.ubicacion ?? 'sin ubicación'}
                  </span>
                  <span>
                    {fmtNum(i.peso_kg)} kg · {dias(i.antiguedad_dias)}
                  </span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </Seccion>
  )
}
