import { describe, expect, it } from 'vitest'
import type { PanelTurno } from '../lib/api'
import { estadoTurno, ritmoTurno } from '../panel/turno'

function turno(extra: Partial<PanelTurno> = {}): PanelTurno {
  return {
    planta_parada: false,
    proximo_arranque: null,
    turno: { codigo: 'B', inicio: '', fin: '', transcurrido_min: 240, duracion_min: 480 },
    piezas: 400,
    plan_turno: 1000,
    plan_ahora: 500,
    prevision_cierre: 800,
    serie: [],
    eficiencia: null,
    paradas: { minutos: 0, numero: 0, mayor: null },
    chatarra: { kg: 0, pct: null },
    objetivos: { oee: 75, chatarra_max_pct: 3 },
    puestos: [{ code: 'CORTE-1', name: 'Corte', grupo: 'Corte', estado: 'en_marcha', motivo: null, minutos: 3, ritmo_nominal: 60, orden: null }],
    ordenes: [],
    pendientes: [],
    ...extra,
  } as unknown as PanelTurno
}

describe('estado del turno', () => {
  it('en fin de semana la planta está parada: gris, sin alarma y con el cierre del último turno', () => {
    const d = turno({ planta_parada: true, piezas: 950, plan_turno: 1000 })
    const e = estadoTurno(d)
    expect(e.tono).toBe('gris')
    expect(e.titular).toBe('Planta parada hasta el domingo a las 22:00')
    expect(e.detalle).toContain('950 de 1.000 piezas')
    expect(ritmoTurno(d)).toBeNull()
  })

  it('sin ninguna orden en curso no es una alarma roja sino "sin producción asignada"', () => {
    const d = turno({
      piezas: 0,
      puestos: [{ code: 'CORTE-1', name: 'Corte', grupo: 'Corte', estado: 'sin_orden', motivo: null, minutos: null, ritmo_nominal: 60, orden: null }] as PanelTurno['puestos'],
    })
    const e = estadoTurno(d)
    expect(e.tono).toBe('gris')
    expect(e.titular).toBe('Sin producción asignada')
  })

  it('en producción y por debajo del plan sigue siendo un aviso', () => {
    const e = estadoTurno(turno({ piezas: 100 }))
    expect(e.tono).toBe('mal')
    expect(e.titular).toContain('Muy por debajo')
  })
})
