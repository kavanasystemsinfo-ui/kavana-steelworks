/** Formatos de cifras del panel de mando (es-ES, como se lee en planta). */

import { fechaYHoraPlanta, TZ_PLANTA } from '../lib/tiempo'

/** Punto de miles también con 4 cifras (1.180): es-ES no lo pone por defecto. */
const AGRUPAR = { useGrouping: 'always' } as unknown as Intl.NumberFormatOptions

export const fmtNum = (n: number | null | undefined, dec = 0) =>
  n === null || n === undefined
    ? '--'
    : n.toLocaleString('es-ES', { ...AGRUPAR, maximumFractionDigits: dec })

/** Minutos como duración legible: "46 min", "1 h 12 min", "3 h", "3 d 4 h". */
export function fmtDuracion(min: number | null | undefined): string {
  if (min === null || min === undefined) return '--'
  const total = Math.round(min)
  if (total < 60) return `${total} min`
  if (total >= 24 * 60) {
    const d = Math.floor(total / (24 * 60))
    const h = Math.floor((total % (24 * 60)) / 60)
    return h === 0 ? `${d} d` : `${d} d ${h} h`
  }
  const h = Math.floor(total / 60)
  const m = total % 60
  return m === 0 ? `${h} h` : `${h} h ${m} min`
}

/** "1 puesto", "2 puestos". */
export const plural = (n: number, uno: string, varios: string) =>
  `${fmtNum(n)} ${n === 1 ? uno : varios}`

const FORMATO_HORA = new Intl.DateTimeFormat('es-ES', {
  timeZone: TZ_PLANTA,
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

/** Hora de planta (Madrid) HH:MM de un ISO o de una fecha. */
export function horaPlanta(instante: string | Date): string {
  return FORMATO_HORA.format(typeof instante === 'string' ? new Date(instante) : instante)
}

const DIAS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb']
const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

/** Entrega en planta: "Hoy 22:00", "Mañana 10:00" o "mié 28 oct". */
export function fmtEntrega(iso: string, ahora = new Date()): string {
  const fecha = new Date(iso)
  const manana = new Date(ahora.getTime() + 24 * 3600 * 1000)
  const diaEntrega = fechaYHoraPlanta(fecha).fecha
  if (diaEntrega === fechaYHoraPlanta(ahora).fecha) return `Hoy ${horaPlanta(iso)}`
  if (diaEntrega === fechaYHoraPlanta(manana).fecha) return `Mañana ${horaPlanta(iso)}`
  const p = new Date(`${diaEntrega}T12:00:00Z`)
  return `${DIAS[p.getUTCDay()]} ${p.getUTCDate()} ${MESES[p.getUTCMonth()]}`
}
