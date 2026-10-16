import { useEffect, useState } from 'react'
import { api, getTenantId, type MaterialOut } from '../lib/api'

/** Panel de Materias Primas (spec 06): recepción de bobinas.
 *  Flujo mínimo (decisión Jorge): registrar cuando llega, entrada directa.
 *  Fase 0 UX: ancho/espesor se auto-rellenan del material elegido y el
 *  formulario no pide Nº calor ni Grado de acero (datos del proveedor que
 *  la API acepta como opcionales cuando existan).
 */

type FormState = {
  material_id: string
  lote: string
  peso: string
  ancho: string
  espesor: string
  ubicacion: string
}

function dimsDe(m: MaterialOut | undefined): Pick<FormState, 'ancho' | 'espesor'> {
  return {
    ancho: m?.dimension_ancho_mm != null ? String(m.dimension_ancho_mm) : '',
    espesor: m?.dimension_espesor_mm != null ? String(m.dimension_espesor_mm) : '',
  }
}

export function MateriasPrimasPage() {
  const [materials, setMaterials] = useState<MaterialOut[]>([])
  const [status, setStatus] = useState<string>('')
  const [error, setError] = useState('')
  const [form, setForm] = useState<FormState>({
    material_id: '',
    lote: '',
    peso: '',
    ancho: '',
    espesor: '',
    ubicacion: '',
  })

  useEffect(() => {
    api
      .listMaterials()
      .then((m) => {
        setMaterials(m)
        if (m.length > 0) setForm((f) => ({ ...f, material_id: m[0].id, ...dimsDe(m[0]) }))
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'Error al cargar materiales'),
      )
  }, [])

  const handleChange = (field: keyof FormState) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>,
  ) => setForm({ ...form, [field]: e.target.value })

  const handleMaterialChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    setForm((f) => ({ ...f, material_id: id, ...dimsDe(materials.find((m) => m.id === id)) }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setStatus('')
    const tenantId = getTenantId()
    if (!tenantId) {
      setError('Sesión no válida. Inicia sesión de nuevo.')
      return
    }
    try {
      const bobina = await api.receiveCoil({
        tenant_id: tenantId,
        material_id: form.material_id,
        lote: form.lote,
        peso: Number(form.peso),
        width_mm: form.ancho ? Number(form.ancho) : undefined,
        thickness_mm: form.espesor ? Number(form.espesor) : undefined,
        ubicacion: form.ubicacion || undefined,
      })
      setStatus(`Bobina ${bobina.coil_id} registrada (${bobina.estado})`)
      setForm((f) => ({ ...f, lote: '', peso: '', ubicacion: '' }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al registrar')
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <div className="step-guide">
        <p className="label-industrial text-xs text-kavana-text-dim">
          Recepción de material
        </p>
        <p className="text-lg font-bold">Registrar bobina entrante</p>
      </div>

      {error && (
        <p className="text-kavana-danger text-sm border border-kavana-danger/40 rounded-sm p-2">
          {error}
        </p>
      )}
      {status && (
        <p className="text-kavana-ok text-sm border border-kavana-ok/40 rounded-sm p-2">
          {status}
        </p>
      )}

      <form
        onSubmit={handleSubmit}
        className="bg-kavana-surface border border-kavana-border rounded-sm p-6 space-y-4"
      >
        <div className="grid grid-cols-2 gap-4">
          <Field label="Material">
            <select
              value={form.material_id}
              onChange={handleMaterialChange}
              className={inputCls}
              required
            >
              {materials.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.code} - {m.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Lote / etiqueta">
            <input
              value={form.lote}
              onChange={handleChange('lote')}
              className={inputCls}
              required
            />
          </Field>
          <Field label="Peso (kg)">
            <input
              type="number"
              step="0.001"
              value={form.peso}
              onChange={handleChange('peso')}
              className={inputCls}
              required
            />
          </Field>
          <Field label="Ancho (mm)">
            <input
              type="number"
              step="0.001"
              value={form.ancho}
              onChange={handleChange('ancho')}
              className={inputCls}
            />
          </Field>
          <Field label="Espesor (mm)">
            <input
              type="number"
              step="0.001"
              value={form.espesor}
              onChange={handleChange('espesor')}
              className={inputCls}
            />
          </Field>
          <Field label="Ubicación">
            <input
              value={form.ubicacion}
              onChange={handleChange('ubicacion')}
              className={inputCls}
            />
          </Field>
        </div>
        <button
          type="submit"
          className="w-full min-h-[64px] bg-kavana-orange text-black font-bold uppercase tracking-widest rounded-sm hover:opacity-90 transition-opacity"
        >
          📦 Registrar bobina
        </button>
      </form>
    </div>
  )
}

const inputCls =
  'mono-data mt-1 w-full bg-kavana-dark border border-kavana-border rounded-sm px-3 py-2 min-h-[48px] text-kavana-text focus:border-kavana-orange outline-none'

function Field({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <label className="block">
      <span className="label-industrial text-xs text-kavana-text-dim">
        {label}
      </span>
      {children}
    </label>
  )
}
