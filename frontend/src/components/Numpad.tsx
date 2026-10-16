/** Numpad táctil para la tablet del operario (Fase Usabilidad).
 *  KAVANA_DESIGN 4.1: botones mínimos de 64px, operables con guantes.
 *  El campo activo (piezas/horas) lo decide el padre con onFocus.
 */

export interface NumpadProps {
  value: string
  onChange: (value: string) => void
  /** Incremento de las teclas + / − (1 por defecto; 0.5 para horas). */
  step?: number
  /** false (por defecto) deshabilita la tecla punto. */
  allowDecimals?: boolean
  /** Techo inferior para − y + iniciales. */
  min?: number
}

const claveCls =
  'min-h-[64px] mono-data bg-kavana-surface border border-kavana-border rounded-sm ' +
  'text-xl font-bold text-kavana-text transition-colors ' +
  'hover:border-kavana-orange hover:text-kavana-orange active:bg-kavana-orange active:text-black ' +
  'disabled:opacity-30 disabled:hover:border-kavana-border disabled:hover:text-kavana-text ' +
  'disabled:active:bg-kavana-surface disabled:active:text-kavana-text'

const accionCls = claveCls + ' text-kavana-orange'

const redondear = (n: number) => Math.round(n * 100) / 100

export function Numpad({
  value,
  onChange,
  step = 1,
  allowDecimals = false,
  min = 0,
}: NumpadProps) {
  const parseado = parseFloat(value)
  const actual = Number.isNaN(parseado) ? 0 : parseado

  const pulsarDigito = (d: string) => {
    if (value.replace('.', '').length >= 7) return
    onChange(value === '0' ? d : value + d)
  }

  const pulsarPunto = () => {
    if (!allowDecimals || value.includes('.')) return
    onChange(value === '' ? '0.' : value + '.')
  }

  const borrar = () => onChange(value.slice(0, -1))
  const limpiar = () => onChange('')
  const aumentar = () => onChange(String(redondear(actual + step)))
  const reducir = () => onChange(String(redondear(Math.max(min, actual - step))))

  return (
    <div className="grid grid-cols-4 gap-2" role="group" aria-label="Teclado numérico">
      {['7', '8', '9'].map((d) => (
        <button key={d} type="button" className={claveCls} onClick={() => pulsarDigito(d)}>
          {d}
        </button>
      ))}
      <button type="button" aria-label="Borrar" className={accionCls} onClick={borrar}>
        ⌫
      </button>

      {['4', '5', '6'].map((d) => (
        <button key={d} type="button" className={claveCls} onClick={() => pulsarDigito(d)}>
          {d}
        </button>
      ))}
      <button type="button" aria-label="Limpiar" className={accionCls} onClick={limpiar}>
        C
      </button>

      {['1', '2', '3'].map((d) => (
        <button key={d} type="button" className={claveCls} onClick={() => pulsarDigito(d)}>
          {d}
        </button>
      ))}
      <button
        type="button"
        aria-label={`Aumentar ${step}`}
        className={accionCls}
        onClick={aumentar}
      >
        +
      </button>

      <button type="button" className={claveCls} onClick={() => pulsarDigito('0')}>
        0
      </button>
      <button
        type="button"
        className={claveCls}
        disabled={!allowDecimals}
        onClick={pulsarPunto}
      >
        .
      </button>
      <button
        type="button"
        aria-label={`Reducir ${step}`}
        className={accionCls}
        onClick={reducir}
      >
        −
      </button>
      <div aria-hidden="true" />
    </div>
  )
}
