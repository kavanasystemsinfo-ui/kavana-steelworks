import { describe, expect, it } from 'vitest'
import { turnoActual } from '../lib/tiempo'

describe('turnoActual (horario de planta UTC-5)', () => {
  it('turno A por la mañana de planta', () => {
    expect(turnoActual(new Date('2026-10-26T12:00:00Z'))).toEqual({ fecha: '2026-10-26', turno: 'A' })
  })
  it('turno B por la tarde', () => {
    expect(turnoActual(new Date('2026-10-26T20:00:00Z'))).toEqual({ fecha: '2026-10-26', turno: 'B' })
  })
  it('de madrugada es el turno C de la víspera', () => {
    // 03:00 UTC = 22:00 del 25 en planta
    expect(turnoActual(new Date('2026-10-26T03:00:00Z'))).toEqual({ fecha: '2026-10-25', turno: 'C' })
    // 08:00 UTC = 03:00 del 26 en planta, sigue siendo el C del 25
    expect(turnoActual(new Date('2026-10-26T08:00:00Z'))).toEqual({ fecha: '2026-10-25', turno: 'C' })
  })
})
