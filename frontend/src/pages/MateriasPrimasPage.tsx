import { useState } from 'react'

/** Panel de Materias Primas (spec 06): recepción de bobinas.
 *  Flujo mínimo (decisión Jorge): registrar cuando llega, entrada directa.
 */
export function MateriasPrimasPage() {
  const [form, setForm] = useState({
    lote: '',
    peso: '',
    ancho: '',
    espesor: '',
    ubicacion: '',
    heat_number: '',
    grado: '',
  })

  const handleChange = (field: keyof typeof form) => (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => setForm({ ...form, [field]: e.target.value })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    // TODO(Fase 3): POST /api/v1/stock-items (receive_coil)
    console.log('recepción:', form)
  }

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <div className="step-guide">
        <p className="label-industrial text-xs text-kavana-text-dim">
          Recepción de material
        </p>
        <p className="text-lg font-bold">Registrar bobina entrante</p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="bg-kavana-surface border border-kavana-border rounded-sm p-6 space-y-4"
      >
        <div className="grid grid-cols-2 gap-4">
          <Field label="Lote / etiqueta" mono>
            <input
              value={form.lote}
              onChange={handleChange('lote')}
              className={inputCls}
              required
            />
          </Field>
          <Field label="Peso (kg)" mono>
            <input
              type="number"
              step="0.001"
              value={form.peso}
              onChange={handleChange('peso')}
              className={inputCls}
              required
            />
          </Field>
          <Field label="Ancho (mm)" mono>
            <input
              type="number"
              step="0.001"
              value={form.ancho}
              onChange={handleChange('ancho')}
              className={inputCls}
            />
          </Field>
          <Field label="Espesor (mm)" mono>
            <input
              type="number"
              step="0.001"
              value={form.espesor}
              onChange={handleChange('espesor')}
              className={inputCls}
            />
          </Field>
          <Field label="Ubicación" mono>
            <input
              value={form.ubicacion}
              onChange={handleChange('ubicacion')}
              className={inputCls}
            />
          </Field>
          <Field label="Nº calor (heat)" mono>
            <input
              value={form.heat_number}
              onChange={handleChange('heat_number')}
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
  mono,
  children,
}: {
  label: string
  mono?: boolean
  children: React.ReactNode
}) {
  return (
    <label className="block">
      <span className="label-industrial text-xs text-kavana-text-dim">
        {label}
      </span>
      <div className={mono ? 'mono-data' : undefined}>{children}</div>
    </label>
  )
}
