/** Formatos de cifras del panel de mando (es-ES, como se lee en planta). */

/** Punto de miles también con 4 cifras (1.180): es-ES no lo pone por defecto. */
const AGRUPAR = { useGrouping: 'always' } as unknown as Intl.NumberFormatOptions

export const fmtNum = (n: number | null | undefined, dec = 0) =>
  n === null || n === undefined
    ? '--'
    : n.toLocaleString('es-ES', { ...AGRUPAR, maximumFractionDigits: dec })

/** Minutos como duración legible: "46 min", "1 h 12 min", "3 h". */
export function fmtDuracion(min: number | null | undefined): string {
  if (min === null || min === undefined) return '--'
  const total = Math.round(min)
  if (total < 60) return `${total} min`
  const h = Math.floor(total / 60)
  const m = total % 60
  return m === 0 ? `${h} h` : `${h} h ${m} min`
}

/** "1 puesto", "2 puestos". */
export const plural = (n: number, uno: string, varios: string) =>
  `${fmtNum(n)} ${n === 1 ? uno : varios}`

/** Hora de planta (UTC-5) HH:MM de un ISO. */
export function horaPlanta(iso: string): string {
  const planta = new Date(new Date(iso).getTime() - 5 * 3600 * 1000)
  return planta.toISOString().slice(11, 16)
}

const DIAS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb']
const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

/** Entrega en planta: "Hoy 22:00", "Mañana 10:00" o "mié 28 oct". */
export function fmtEntrega(iso: string, ahora = new Date()): string {
  const dia = (d: Date) => new Date(d.getTime() - 5 * 3600 * 1000).toISOString().slice(0, 10)
  const fecha = new Date(iso)
  const manana = new Date(ahora.getTime() + 24 * 3600 * 1000)
  if (dia(fecha) === dia(ahora)) return `Hoy ${horaPlanta(iso)}`
  if (dia(fecha) === dia(manana)) return `Mañana ${horaPlanta(iso)}`
  const p = new Date(fecha.getTime() - 5 * 3600 * 1000)
  return `${DIAS[p.getUTCDay()]} ${p.getUTCDate()} ${MESES[p.getUTCMonth()]}`
}
