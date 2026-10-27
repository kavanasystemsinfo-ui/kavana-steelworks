/** "hace 5 min" a partir de un ISO; la hora sola si es de otro día. */
export function haceCuanto(iso: string, ahora = new Date()): string {
  const fecha = new Date(iso)
  const min = Math.floor((ahora.getTime() - fecha.getTime()) / 60000)
  if (min < 1) return 'ahora'
  if (min < 60) return `hace ${min} min`
  if (min < 24 * 60) return `hace ${Math.floor(min / 60)} h`
  return fecha.toLocaleString('es-ES')
}

/** Desfase del horario de planta respecto a UTC (espejo de backend shifts.TZ_PLANTA). */
const OFFSET_PLANTA_H = -5

/** Fecha (YYYY-MM-DD) y turno A/B/C en curso en horario de planta.
 *  A 06-14, B 14-22, C 22-06; de 00 a 06 el turno C es el de la víspera.
 */
export function turnoActual(ahora = new Date()): { fecha: string; turno: 'A' | 'B' | 'C' } {
  const planta = new Date(ahora.getTime() + OFFSET_PLANTA_H * 3600 * 1000)
  const hora = planta.getUTCHours()
  if (hora < 6) planta.setUTCDate(planta.getUTCDate() - 1)
  const fecha = planta.toISOString().slice(0, 10)
  const turno = hora >= 6 && hora < 14 ? 'A' : hora >= 14 && hora < 22 ? 'B' : 'C'
  return { fecha, turno }
}
