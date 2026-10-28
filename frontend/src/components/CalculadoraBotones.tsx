import { useEffect, useState } from 'react'
import { api, type Calculadora } from '../lib/api'

export type Unidad = 'palets' | 'filas' | 'paquetes' | 'piezas'

/** Calculadoras de embalaje del puesto (port del legacy, fase 2 del rediseño):
 *  +1 palet, +1 fila, +1 paquete o +1 pieza en lugar de contar piezas. El
 *  operario crea las plantillas en su puesto y las ve cualquiera de él. */
export function CalculadoraBotones({
  puesto,
  onSumar,
}: {
  puesto: string | null
  onSumar: (unidad: Unidad, piezas: number, calculadora: string | null) => void
}) {
  const [lista, setLista] = useState<Calculadora[]>([])
  const [elegida, setElegida] = useState<string>('')
  const [creando, setCreando] = useState(false)

  useEffect(() => {
    if (!puesto) return
    let vivo = true
    api
      .listCalculadoras(puesto)
      .then((l) => {
        if (!vivo || !Array.isArray(l)) return
        setLista(l)
        setElegida((actual) => actual || l[0]?.id || '')
      })
      .catch(() => {})
    return () => {
      vivo = false
    }
  }, [puesto])

  const calc = lista.find((c) => c.id === elegida) ?? null
  const boton =
    'min-h-[84px] rounded-xl border font-[inherit] flex flex-col items-center justify-center gap-0.5 transition-colors disabled:opacity-40'
  const nombre = calc?.nombre ?? null

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-sm text-p-texto2">
          Calculadora
          <select
            value={elegida}
            onChange={(e) => setElegida(e.target.value)}
            className="min-h-[40px] rounded-lg border border-p-borde bg-p-tarjeta px-2 text-sm text-p-texto"
          >
            {lista.length === 0 && <option value="">Sin calculadoras en este puesto</option>}
            {lista.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nombre} · {c.piezas_paquete} × {c.paquetes_fila} × {c.filas_palet} = {c.piezas_palet}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => setCreando(true)}
          disabled={!puesto}
          className="min-h-[40px] rounded-lg px-3 text-sm font-semibold text-p-plan hover:underline disabled:opacity-40"
        >
          Nueva calculadora
        </button>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <button
          type="button"
          disabled={!calc}
          onClick={() => calc && onSumar('palets', calc.piezas_palet, nombre)}
          className={`${boton} border-2 border-kavana-orange bg-[#fff4ee]`}
        >
          <span className="text-2xl font-extrabold">+1 palet</span>
          <span className="text-sm text-p-texto2">{calc ? `${calc.piezas_palet} piezas` : '—'}</span>
        </button>
        <button
          type="button"
          disabled={!calc}
          onClick={() => calc && onSumar('filas', calc.piezas_fila, nombre)}
          className={`${boton} border-p-borde bg-p-tarjeta`}
        >
          <span className="text-2xl font-extrabold">+1 fila</span>
          <span className="text-sm text-p-texto2">{calc ? `${calc.piezas_fila} piezas` : '—'}</span>
        </button>
        <button
          type="button"
          disabled={!calc}
          onClick={() => calc && onSumar('paquetes', calc.piezas_paquete, nombre)}
          className={`${boton} border-p-borde bg-p-tarjeta`}
        >
          <span className="text-2xl font-extrabold">+1 paquete</span>
          <span className="text-sm text-p-texto2">{calc ? `${calc.piezas_paquete} piezas` : '—'}</span>
        </button>
        <button
          type="button"
          onClick={() => onSumar('piezas', 1, nombre)}
          className={`${boton} border-p-borde bg-p-tarjeta`}
        >
          <span className="text-2xl font-extrabold">+1 pieza</span>
          <span className="text-sm text-p-texto2">o escribe la cantidad</span>
        </button>
      </div>

      {creando && puesto && (
        <NuevaCalculadora
          puesto={puesto}
          onCancelar={() => setCreando(false)}
          onGuardada={(c) => {
            setLista((l) => [...l, c])
            setElegida(c.id)
            setCreando(false)
          }}
        />
      )}
    </div>
  )
}

function Contador({
  id,
  etiqueta,
  valor,
  onCambio,
}: {
  id: string
  etiqueta: string
  valor: number
  onCambio: (v: number) => void
}) {
  const btn = 'w-14 min-h-[60px] rounded-xl border border-p-borde bg-p-tarjeta text-2xl font-bold'
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-sm font-semibold">
        {etiqueta}
      </label>
      <div className="flex gap-2">
        <button type="button" aria-label={`Menos ${etiqueta.toLowerCase()}`} className={btn} onClick={() => onCambio(Math.max(1, valor - 1))}>
          −
        </button>
        <input
          id={id}
          type="number"
          min={1}
          value={valor}
          onChange={(e) => onCambio(Math.max(1, Number(e.target.value) || 1))}
          className="w-full min-w-0 min-h-[60px] rounded-xl border border-p-borde text-center text-2xl font-extrabold"
        />
        <button type="button" aria-label={`Más ${etiqueta.toLowerCase()}`} className={btn} onClick={() => onCambio(valor + 1)}>
          +
        </button>
      </div>
    </div>
  )
}

/** Crear calculadora (pantalla 3 de la maqueta), en una ventana sobre el panel. */
function NuevaCalculadora({
  puesto,
  onCancelar,
  onGuardada,
}: {
  puesto: string
  onCancelar: () => void
  onGuardada: (c: Calculadora) => void
}) {
  const [nombre, setNombre] = useState('')
  const [pp, setPp] = useState(5)
  const [pf, setPf] = useState(2)
  const [fp, setFp] = useState(4)
  const [error, setError] = useState('')
  const total = pp * pf * fp

  const guardar = async () => {
    setError('')
    try {
      onGuardada(
        await api.crearCalculadora({
          puesto,
          nombre: nombre.trim(),
          piezas_paquete: pp,
          paquetes_fila: pf,
          filas_palet: fp,
        }),
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar')
    }
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4">
      <div role="dialog" aria-modal="true" aria-label="Nueva calculadora" className="w-full max-w-3xl rounded-2xl bg-p-tarjeta p-6 space-y-5 text-p-texto">
        <h2 className="text-2xl font-extrabold">Nueva calculadora · {puesto}</h2>
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-semibold">Nombre</span>
          <input
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="Ej.: Palet estándar K-100"
            className="min-h-[52px] rounded-xl border border-p-borde px-4 text-lg"
          />
        </label>
        <div className="grid grid-cols-3 gap-4">
          <Contador id="calc-pp" etiqueta="Piezas por paquete" valor={pp} onCambio={setPp} />
          <Contador id="calc-pf" etiqueta="Paquetes por fila" valor={pf} onCambio={setPf} />
          <Contador id="calc-fp" etiqueta="Filas por palet" valor={fp} onCambio={setFp} />
        </div>
        <div className="rounded-xl bg-p-fondo px-5 py-4">
          <p className="text-sm text-p-texto2">Un palet son</p>
          <p className="text-4xl font-extrabold">
            {total.toLocaleString('es-ES')} <span className="text-xl font-semibold text-p-texto2">piezas</span>
          </p>
          <p className="text-sm text-p-texto2">
            {pp} × {pf} × {fp} · una fila = {pp * pf} · un paquete = {pp}
          </p>
        </div>
        {error && <p role="alert" className="text-sm text-p-mal">{error}</p>}
        <div className="flex gap-3">
          <button type="button" onClick={onCancelar} className="min-h-[56px] rounded-xl border border-p-borde px-6 font-semibold">
            Cancelar
          </button>
          <button
            type="button"
            onClick={guardar}
            disabled={!nombre.trim()}
            className="flex-1 min-h-[56px] rounded-xl bg-kavana-orange text-white text-lg font-extrabold disabled:opacity-40"
          >
            Guardar y usar
          </button>
        </div>
      </div>
    </div>
  )
}
