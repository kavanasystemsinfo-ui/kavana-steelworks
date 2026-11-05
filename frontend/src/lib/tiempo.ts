/** "hace 5 min" a partir de un ISO; la hora sola si es de otro día. */
export function haceCuanto(iso: string, ahora = new Date()): string {
  const fecha = new Date(iso)
  const min = Math.floor((ahora.getTime() - fecha.getTime()) / 60000)
  if (min < 1) return 'ahora'
  if (min < 60) return `hace ${min} min`
  if (min < 24 * 60) return `hace ${Math.floor(min / 60)} h`
  return fecha.toLocaleString('es-ES')
}

/** Zona horaria de la planta (espejo de backend shifts.TZ_PLANTA): hora de Madrid, con
 *  cambio de hora de verano. */
export const TZ_PLANTA = 'Europe/Madrid'

const FORMATO_PLANTA = new Intl.DateTimeFormat('en-CA', {
  timeZone: TZ_PLANTA,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  hourCycle: 'h23',
})

/** Fecha (YYYY-MM-DD) y hora (0-23) de un instante en horario de planta. */
export function fechaYHoraPlanta(instante: Date): { fecha: string; hora: number } {
  const partes: Record<string, string> = {}
  for (const p of FORMATO_PLANTA.formatToParts(instante)) partes[p.type] = p.value
  return { fecha: `${partes.year}-${partes.month}-${partes.day}`, hora: Number(partes.hour) }
}

/** Fecha (YYYY-MM-DD) y turno A/B/C en curso en horario de planta.
 *  A 06-14, B 14-22, C 22-06; de 00 a 06 el turno C es el de la víspera.
 */
export function turnoActual(ahora = new Date()): { fecha: string; turno: 'A' | 'B' | 'C' } {
  const { fecha: hoy, hora } = fechaYHoraPlanta(ahora)
  let fecha = hoy
  if (hora < 6) {
    const ayer = new Date(`${hoy}T12:00:00Z`)
    ayer.setUTCDate(ayer.getUTCDate() - 1)
    fecha = ayer.toISOString().slice(0, 10)
  }
  const turno = hora >= 6 && hora < 14 ? 'A' : hora >= 14 && hora < 22 ? 'B' : 'C'
  return { fecha, turno }
}
