import { useEffect, useState } from 'react'
import { api, type MaterialOut } from '../lib/api'

type BobinaAlta = Awaited<ReturnType<typeof api.altaManualBobina>>

/** Modo manual del operario (como el legacy): una bobina que Materias Primas
 *  aún no ha registrado se da de alta con los datos de la etiqueta del
 *  proveedor. El peso de la etiqueta es el que carga la línea al vincular. */
export function AltaManualBobina({
  puesto,
  materialId: materialOrden = null,
  onAlta,
}: {
  puesto: string | null
  /** Material de la línea: el formulario lo trae elegido (como el legacy). */
  materialId?: string | null
  onAlta: (bobina: BobinaAlta) => void
}) {
  const [abierto, setAbierto] = useState(false)
  const [materiales, setMateriales] = useState<MaterialOut[]>([])
  const [materialId, setMaterialId] = useState('')
  const [peso, setPeso] = useState('')
  const [lote, setLote] = useState('')
  const [ancho, setAncho] = useState('')
  const [espesor, setEspesor] = useState('')
  const [error, setError] = useState('')

  const elegir = (id: string, lista: MaterialOut[] = materiales) => {
    setMaterialId(id)
    const m = lista.find((x) => x.id === id)
    if (m?.dimension_ancho_mm) setAncho(String(m.dimension_ancho_mm))
    if (m?.dimension_espesor_mm) setEspesor(String(m.dimension_espesor_mm))
  }

  useEffect(() => {
    if (!abierto || materiales.length) return
    api
      .listMaterials()
      .then((lista) => {
        setMateriales(lista)
        if (materialOrden && lista.some((m) => m.id === materialOrden)) elegir(materialOrden, lista)
      })
      .catch(() => setError('No se pudieron cargar los materiales'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [abierto, materiales.length, materialOrden])

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      const bobina = await api.altaManualBobina({
        material_id: materialId,
        peso_kg: Number(peso),
        lote: lote.trim(),
        width_mm: ancho ? Number(ancho) : undefined,
        thickness_mm: espesor ? Number(espesor) : undefined,
        puesto: puesto ?? undefined,
      })
      setAbierto(false)
      onAlta(bobina)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al registrar la bobina')
    }
  }

  const campo =
    'mono-data mt-1 w-full bg-kavana-dark border border-kavana-border rounded-xl px-3 min-h-[52px] focus:border-kavana-orange outline-none'

  if (!abierto) {
    return (
      <button
        type="button"
        onClick={() => setAbierto(true)}
        className="w-full min-h-[52px] border border-kavana-border text-kavana-text-dim font-bold rounded-xl hover:border-kavana-orange hover:text-kavana-orange transition-colors"
      >
        Registrar bobina a mano
      </button>
    )
  }

  return (
    <form onSubmit={enviar} className="bg-kavana-surface border border-kavana-border rounded-xl p-6 space-y-3">
      <p className="label-industrial text-xs text-kavana-text-dim">
        Modo manual: copia los datos de la etiqueta del proveedor
      </p>
      <label className="block text-sm">
        Material
        <select value={materialId} onChange={(e) => elegir(e.target.value)} className={campo} required>
          <option value="">Elige el material</option>
          {materiales.map((m) => (
            <option key={m.id} value={m.id}>
              {m.code} · {m.name}
            </option>
          ))}
        </select>
      </label>
      <div className="grid grid-cols-2 gap-2">
        <label className="block text-sm">
          Peso de la etiqueta (kg)
          <input type="number" inputMode="decimal" min="0" step="any" value={peso} onChange={(e) => setPeso(e.target.value)} className={campo} required />
        </label>
        <label className="block text-sm">
          Lote / colada
          <input value={lote} onChange={(e) => setLote(e.target.value)} className={campo} required />
        </label>
        <label className="block text-sm">
          Ancho (mm)
          <input type="number" inputMode="decimal" min="0" step="any" value={ancho} onChange={(e) => setAncho(e.target.value)} className={campo} />
        </label>
        <label className="block text-sm">
          Espesor (mm)
          <input type="number" inputMode="decimal" min="0" step="any" value={espesor} onChange={(e) => setEspesor(e.target.value)} className={campo} />
        </label>
      </div>
      {error && <p className="text-sm text-kavana-danger">{error}</p>}
      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => setAbierto(false)}
          className="min-h-[52px] border border-kavana-border text-kavana-text-dim font-bold rounded-xl"
        >
          Cancelar
        </button>
        <button
          type="submit"
          disabled={!materialId || !peso || !lote.trim()}
          className="min-h-[52px] bg-kavana-orange text-black font-bold rounded-xl disabled:opacity-40"
        >
          Registrar
        </button>
      </div>
    </form>
  )
}
