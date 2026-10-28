import { useEffect, useState } from 'react'
import { api, type Parada } from '../lib/api'

/** Motivos de parada de planta (Jorge, 28-10). */
export const MOTIVOS: { codigo: string; texto: string }[] = [
  { codigo: 'averia', texto: 'Avería' },
  { codigo: 'ajustes', texto: 'Ajustes' },
  { codigo: 'cambio_modelo', texto: 'Cambio de modelo' },
  { codigo: 'limpieza', texto: 'Limpieza' },
  { codigo: 'mantenimiento', texto: 'Mantenimiento' },
  { codigo: 'otros', texto: 'Otros' },
]

function Motivos({ onElegir, actual }: { onElegir: (codigo: string) => void; actual?: string }) {
  return (
    <div className="grid grid-cols-3 gap-2.5">
      {MOTIVOS.map((m) => (
        <button
          key={m.codigo}
          type="button"
          onClick={() => onElegir(m.codigo)}
          aria-pressed={actual === m.codigo}
          className={`min-h-[56px] rounded-xl border px-2 text-base font-semibold transition-colors ${
            actual === m.codigo
              ? 'border-p-mal bg-p-mal-bg text-p-mal'
              : 'border-p-borde bg-p-tarjeta text-p-texto hover:border-p-mal'
          }`}
        >
          {m.texto}
        </button>
      ))}
    </div>
  )
}

/** Tarjeta «¿Paras la máquina?»: un toque y empieza a contar la parada. */
export function MotivosParada({
  puesto,
  orderId,
  lineId,
  onParada,
  onError,
}: {
  puesto: string
  orderId?: string | null
  lineId?: string | null
  onParada: (p: Parada) => void
  onError: (mensaje: string) => void
}) {
  const parar = async (motivo: string) => {
    try {
      onParada(
        await api.parar({ puesto, motivo, order_id: orderId || null, line_id: lineId || null }),
      )
    } catch (e) {
      onError(e instanceof Error ? e.message : 'No se pudo registrar la parada')
    }
  }
  return (
    <section aria-label="Parar la máquina" className="bg-p-tarjeta border border-p-borde rounded-2xl p-5 space-y-3">
      <h2 className="text-lg font-bold">¿Paras la máquina? Toca el motivo</h2>
      <Motivos onElegir={parar} />
    </section>
  )
}

function reloj(segundos: number): string {
  const h = Math.floor(segundos / 3600)
  const m = Math.floor((segundos % 3600) / 60)
  const s = segundos % 60
  const mmss = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return h > 0 ? `${h}:${mmss}` : mmss
}

/** Pantalla de máquina parada (pantalla 2 de la maqueta): el motivo en grande,
 *  el tiempo corriendo y un botón grande para volver a producir. */
export function PantallaParada({
  parada,
  orden,
  onCambio,
  onFin,
  onError,
}: {
  parada: Parada
  orden: string | null
  onCambio: (p: Parada) => void
  onFin: () => void
  onError: (mensaje: string) => void
}) {
  const [ahora, setAhora] = useState(() => Date.now())
  const [nota, setNota] = useState(parada.nota ?? '')
  const [cambiando, setCambiando] = useState(false)

  useEffect(() => {
    const t = setInterval(() => setAhora(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  const segundos = Math.max(0, Math.floor((ahora - new Date(parada.inicio).getTime()) / 1000))
  const desde = new Date(parada.inicio).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
  const texto = MOTIVOS.find((m) => m.codigo === parada.motivo)?.texto ?? parada.motivo_texto

  const volver = async () => {
    try {
      await api.finParada(parada.id, { nota: nota.trim() || null })
      onFin()
    } catch (e) {
      onError(e instanceof Error ? e.message : 'No se pudo cerrar la parada')
    }
  }
  const cambiar = async (motivo: string) => {
    try {
      onCambio(await api.cambiarParada(parada.id, { motivo }))
      setCambiando(false)
    } catch (e) {
      onError(e instanceof Error ? e.message : 'No se pudo cambiar el motivo')
    }
  }

  return (
    <div className="space-y-4">
      <section
        aria-label="Parada en curso"
        className="rounded-2xl bg-[#8e2b1f] text-white px-10 py-9 space-y-4"
      >
        <p className="text-lg font-semibold text-[#ffe2db]">
          Máquina parada · {parada.puesto}
          {orden ? ` · ${orden}` : ''}
        </p>
        <h1 className="text-6xl font-extrabold leading-none">{texto}</h1>
        <p className="text-8xl font-extrabold leading-none tabular-nums" aria-live="off">
          {reloj(segundos)}
        </p>
        <p className="text-lg text-[#ffe2db]">
          Desde las {desde}. El tiempo cuenta solo; la oficina ve la parada al momento.
        </p>
        <label className="flex flex-col gap-2 max-w-3xl">
          <span className="text-base font-semibold">¿Qué ha pasado? (opcional)</span>
          <input
            value={nota}
            onChange={(e) => setNota(e.target.value)}
            placeholder="Ej.: se ha roto la cuchilla de corte"
            className="min-h-[52px] rounded-xl px-4 text-lg text-p-texto bg-white"
          />
        </label>
      </section>

      {cambiando && (
        <section aria-label="Cambiar motivo" className="bg-p-tarjeta border border-p-borde rounded-2xl p-5 space-y-3">
          <h2 className="text-lg font-bold">Elige el motivo correcto</h2>
          <Motivos onElegir={cambiar} actual={parada.motivo} />
        </section>
      )}

      <div className="flex gap-3">
        <button
          type="button"
          onClick={volver}
          className="flex-1 min-h-[72px] rounded-2xl bg-p-ok text-white text-2xl font-extrabold hover:opacity-90"
        >
          Volver a producir
        </button>
        <button
          type="button"
          onClick={() => setCambiando((c) => !c)}
          className="min-h-[72px] rounded-2xl border border-p-borde bg-p-tarjeta px-7 text-lg font-semibold"
        >
          Cambiar motivo
        </button>
      </div>
    </div>
  )
}
