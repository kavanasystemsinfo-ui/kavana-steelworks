import { useMemo, useState } from 'react'
import type { CategoriaTraza, FichaTrazabilidad } from '../lib/api'

const ETIQUETAS: Record<CategoriaTraza, string> = {
  produccion: 'Producción',
  calidad: 'Calidad',
  bobina: 'Bobinas',
  parada: 'Paradas',
  incidencia: 'Incidencias',
  estado: 'Estados',
}

const ESTADOS_LINEA: Record<string, string> = {
  pending: 'pendiente',
  in_progress: 'en curso',
  stopped: 'parada',
  completed: 'completada',
}

const fmt = (n: number, dec = 1) => n.toLocaleString('es-ES', { maximumFractionDigits: dec })

const fecha = (iso: string) =>
  new Date(iso).toLocaleString('es-ES', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })

function Dato({ etiqueta, valor, nota }: { etiqueta: string; valor: string; nota?: string }) {
  return (
    <article
      aria-label={etiqueta}
      className="bg-p-fondo border border-p-borde rounded-[10px] px-3 py-2"
    >
      <p className="m-0 text-[11px] uppercase tracking-wide text-p-texto2">{etiqueta}</p>
      <p className="m-0 text-lg font-bold text-p-texto">{valor}</p>
      {nota && <p className="m-0 text-xs text-p-texto2">{nota}</p>}
    </article>
  )
}

/** Ficha de trazabilidad de una orden (T-045): resumen arriba y debajo una línea
 *  de tiempo unificada, de más reciente a más antiguo, con filtros por categoría. */
export function FichaTrazabilidadVista({ ficha }: { ficha: FichaTrazabilidad }) {
  const { resumen, linea_tiempo } = ficha
  const [filtro, setFiltro] = useState<CategoriaTraza | 'todo'>('todo')

  const cuentas = useMemo(() => {
    const c: Partial<Record<CategoriaTraza, number>> = {}
    for (const e of linea_tiempo) c[e.categoria] = (c[e.categoria] ?? 0) + 1
    return c
  }, [linea_tiempo])

  const visibles = filtro === 'todo' ? linea_tiempo : linea_tiempo.filter((e) => e.categoria === filtro)

  return (
    <div className="space-y-4">
      <section aria-label="Resumen de la orden" className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        <Dato
          etiqueta={resumen.lineas.length > 1 ? 'Piezas terminadas' : 'Piezas'}
          valor={`${fmt(resumen.piezas_producidas, 0)} de ${fmt(resumen.piezas_objetivo, 0)}`}
          nota={resumen.lineas.length > 1 ? 'las de la última línea' : undefined}
        />
        <Dato etiqueta="Merma" valor={`${fmt(resumen.merma_kg)} kg`} />
        <Dato etiqueta="Material usado" valor={`${fmt(resumen.kg_consumidos)} kg`} />
        <Dato
          etiqueta="Paradas"
          valor={`${fmt(resumen.paradas_minutos, 0)} min`}
          nota={resumen.paradas_abiertas > 0 ? `${resumen.paradas_abiertas} sigue abierta` : undefined}
        />
        <Dato etiqueta="Incidencias" valor={String(resumen.incidencias)} />
        <Dato
          etiqueta="Ritmo medio"
          valor={resumen.eficiencia_media_uds_h != null ? `${fmt(resumen.eficiencia_media_uds_h)} uds/h` : 'Sin datos'}
        />
      </section>

      {resumen.lineas.length > 1 && (
        <section aria-label="Líneas de la orden">
          <h3 className="m-0 mb-1 text-sm font-semibold text-p-texto">Líneas</h3>
          <ul className="m-0 p-0 list-none space-y-1">
            {resumen.lineas.map((l) => (
              <li key={l.numero} className="flex justify-between gap-2 text-sm">
                <span>
                  Línea {l.numero}
                  {l.puesto ? ` · ${l.puesto}` : ''}
                  <span className="ml-2 text-xs text-p-texto2">{ESTADOS_LINEA[l.estado] ?? l.estado}</span>
                </span>
                <span className="mono-data">
                  {fmt(l.producidas, 0)} de {fmt(l.total, 0)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {resumen.kg_por_bobina.length > 0 && (
        <section aria-label="Bobinas de la orden">
          <h3 className="m-0 mb-1 text-sm font-semibold text-p-texto">Bobinas</h3>
          <ul className="m-0 p-0 list-none space-y-1">
            {resumen.kg_por_bobina.map((b) => (
              <li
                key={b.stock_item_id ?? b.lote ?? 'sin-bobina'}
                className="flex flex-wrap items-center justify-between gap-2 text-sm"
              >
                <span>
                  {b.coil_id ?? 'Sin código'}
                  {b.lote ? ` · lote ${b.lote}` : ''}
                  {b.origen === 'alta_manual' && (
                    <span className="ml-2 text-xs border border-p-aviso-borde text-p-aviso rounded px-1.5 py-0.5">
                      {b.pendiente_verificacion ? 'Alta manual · sin verificar' : 'Alta manual · verificada'}
                    </span>
                  )}
                </span>
                <span className="mono-data">{fmt(b.kg)} kg</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {resumen.personas.length > 0 && (
        <section aria-label="Personas que intervinieron">
          <h3 className="m-0 mb-1 text-sm font-semibold text-p-texto">Personas</h3>
          <ul className="m-0 p-0 list-none space-y-1">
            {resumen.personas.map((p) => (
              <li key={p.id} className="flex justify-between gap-2 text-sm">
                <span>{p.nombre}</span>
                <span className="text-p-texto2">
                  {p.eventos} eventos{p.piezas > 0 ? ` · ${fmt(p.piezas, 0)} piezas` : ''}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-label="Línea de tiempo">
        <div className="flex flex-wrap items-center gap-2 mb-2" role="group" aria-label="Filtrar por categoría">
          <button
            type="button"
            aria-pressed={filtro === 'todo'}
            onClick={() => setFiltro('todo')}
            className={`min-h-[36px] px-3 rounded-full border text-xs ${
              filtro === 'todo' ? 'bg-p-texto text-white border-p-texto' : 'border-p-borde text-p-texto2'
            }`}
          >
            Todo ({linea_tiempo.length})
          </button>
          {ficha.categorias
            .filter((c) => (cuentas[c] ?? 0) > 0)
            .map((c) => (
              <button
                key={c}
                type="button"
                aria-pressed={filtro === c}
                onClick={() => setFiltro(c)}
                className={`min-h-[36px] px-3 rounded-full border text-xs ${
                  filtro === c ? 'bg-p-texto text-white border-p-texto' : 'border-p-borde text-p-texto2'
                }`}
              >
                {ETIQUETAS[c]} ({cuentas[c]})
              </button>
            ))}
        </div>

        {visibles.length === 0 ? (
          <p className="text-kavana-text-dim text-sm">Sin eventos de trazabilidad para esta orden.</p>
        ) : (
          <ol className="m-0 p-0 list-none space-y-2">
            {visibles.map((e) => (
              <li
                key={e.id}
                className="flex items-start justify-between gap-3 border-t border-kavana-border pt-2 text-sm"
              >
                <div>
                  <p className="m-0 font-semibold">{e.titulo}</p>
                  <p className="m-0 text-kavana-text-dim text-xs">
                    {fecha(e.timestamp)}
                    {e.quien ? ` · ${e.quien}` : ''}
                    <span className="ml-2 uppercase tracking-wide">{ETIQUETAS[e.categoria]}</span>
                  </p>
                  {e.detalle && <p className="m-0 text-kavana-text-dim text-xs">{e.detalle}</p>}
                </div>
                {e.cantidad != null && e.cantidad > 0 && (
                  <p className="m-0 mono-data whitespace-nowrap">
                    {fmt(e.cantidad)} {e.unidad ?? ''}
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  )
}
