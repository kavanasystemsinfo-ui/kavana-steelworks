import { describe, expect, it } from 'vitest'
import { fmtDuracion, fmtEntrega, horaPlanta } from '../panel/formato'

describe('fmtDuracion', () => {
  it('minutos y horas como siempre', () => {
    expect(fmtDuracion(46)).toBe('46 min')
    expect(fmtDuracion(72)).toBe('1 h 12 min')
    expect(fmtDuracion(180)).toBe('3 h')
  })
  it('las duraciones de un día o más se dicen en días, nunca en cientos de horas', () => {
    expect(fmtDuracion(1956 * 60 + 37)).toBe('81 d 12 h')
    expect(fmtDuracion(24 * 60)).toBe('1 d')
    expect(fmtDuracion(3 * 24 * 60 + 4 * 60 + 20)).toBe('3 d 4 h')
  })
  it('sin dato', () => {
    expect(fmtDuracion(null)).toBe('--')
  })
})

describe('hora de planta (Madrid)', () => {
  it('invierno UTC+1 y verano UTC+2', () => {
    expect(horaPlanta('2026-11-05T04:21:00Z')).toBe('05:21')
    expect(horaPlanta('2026-07-15T04:21:00Z')).toBe('06:21')
  })
  it('la entrega usa el día y la hora de Madrid', () => {
    const ahora = new Date('2026-11-05T09:00:00Z')
    expect(fmtEntrega('2026-11-05T21:00:00Z', ahora)).toBe('Hoy 22:00')
    expect(fmtEntrega('2026-11-06T09:00:00Z', ahora)).toBe('Mañana 10:00')
    expect(fmtEntrega('2026-11-10T09:00:00Z', ahora)).toBe('mar 10 nov')
  })
})
