import { describe, expect, it } from 'vitest'
import { turnoActual } from '../lib/tiempo'

describe('turnoActual (horario de planta: Madrid)', () => {
  it('turno A por la mañana de planta', () => {
    // 12:00 UTC = 13:00 en Madrid (invierno)
    expect(turnoActual(new Date('2026-10-26T12:00:00Z'))).toEqual({ fecha: '2026-10-26', turno: 'A' })
  })
  it('turno B por la tarde', () => {
    expect(turnoActual(new Date('2026-10-26T20:00:00Z'))).toEqual({ fecha: '2026-10-26', turno: 'B' })
  })
  it('el turno C empieza a las 22:00 y de madrugada es el de la víspera', () => {
    // 21:00 UTC = 22:00 del 26 en Madrid
    expect(turnoActual(new Date('2026-10-26T21:00:00Z'))).toEqual({ fecha: '2026-10-26', turno: 'C' })
    // 03:00 UTC = 04:00 del 26 en Madrid: sigue siendo el C del 25
    expect(turnoActual(new Date('2026-10-26T03:00:00Z'))).toEqual({ fecha: '2026-10-25', turno: 'C' })
  })
  it('respeta el horario de verano (UTC+2)', () => {
    // 04:00 UTC = 06:00 en Madrid en julio: ya es el turno A
    expect(turnoActual(new Date('2026-07-15T04:00:00Z'))).toEqual({ fecha: '2026-07-15', turno: 'A' })
    // 03:59 UTC = 05:59: todavía el C de la víspera
    expect(turnoActual(new Date('2026-07-15T03:59:00Z'))).toEqual({ fecha: '2026-07-14', turno: 'C' })
  })
})
