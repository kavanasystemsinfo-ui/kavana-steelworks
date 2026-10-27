import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { EstadoOrdenTurno, EstadoPuestoTurno, PanelTurno } from '../lib/api'
import { fmtDuracion, fmtNum, plural } from './formato'
import type { Tono } from './tokens'

/** Datos de la vista Turno, refrescados cada 30 s (los comparten la vista y el modo TV). */
export function useTurno() {
  const [datos, setDatos] = useState<PanelTurno | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let vivo = true
    const cargar = () =>
      api
        .getTurno()
        .then((d) => {
          if (!vivo) return
          setDatos(d)
          setError('')
        })
        .catch((e) => vivo && setError(e instanceof Error ? e.message : 'Error de conexión'))
    cargar()
    const timer = setInterval(cargar, 30000)
    return () => {
      vivo = false
      clearInterval(timer)
    }
  }, [])

  return { datos, error }
}

/** Cómo va el turno contra el plan a esta hora. */
export function ritmoTurno(d: PanelTurno): { texto: string; tono: Tono } | null {
  if (!d.plan_ahora) return null
  const r = d.piezas / d.plan_ahora
  if (r >= 0.95) return { texto: 'En ritmo', tono: 'ok' }
  if (r >= 0.8) return { texto: 'Por debajo', tono: 'aviso' }
  return { texto: 'Muy por debajo', tono: 'mal' }
}

/** La frase de arriba: cómo va el turno y lo que más pesa ahora. */
export function estadoTurno(d: PanelTurno): { tono: Tono; titular: string; detalle: string } {
  const parados = d.puestos.filter((p) => p.estado === 'parado').length
  const mayor = d.paradas.mayor
  const pesa =
    mayor && mayor.abierta
      ? ` Lo que más pesa ahora: ${mayor.puesto} lleva ${fmtDuracion(mayor.minutos)} parado por ${mayor.motivo}.`
      : mayor
        ? ` La parada más larga del turno: ${mayor.puesto}, ${fmtDuracion(mayor.minutos)} por ${mayor.motivo}.`
        : ''

  if (d.plan_turno === null) {
    return {
      tono: 'gris',
      titular: 'Sin plan del turno',
      detalle:
        `Llevamos ${plural(d.piezas, 'pieza', 'piezas')}. Para tener plan, configura el ritmo ` +
        `nominal (piezas/hora) de los puestos en Administración.${pesa}`,
    }
  }
  if (d.turno.transcurrido_min < 15) {
    return {
      tono: 'gris',
      titular: 'El turno acaba de empezar',
      detalle: `Plan del turno: ${fmtNum(d.plan_turno)} piezas.${pesa}`,
    }
  }
  const ritmo = ritmoTurno(d)!
  const prevision =
    d.prevision_cierre !== null
      ? `Al ritmo actual cerrarás el turno en ${fmtNum(d.prevision_cierre)} de ${fmtNum(d.plan_turno)} piezas (${fmtNum((d.prevision_cierre / d.plan_turno) * 100)} %).`
      : `Plan del turno: ${fmtNum(d.plan_turno)} piezas.`

  let titular: string
  let tono = ritmo.tono
  if (ritmo.tono === 'ok') {
    titular = parados ? `En ritmo, pero con ${plural(parados, 'puesto parado', 'puestos parados')}` : 'En ritmo'
    if (parados) tono = 'aviso'
  } else if (ritmo.tono === 'aviso') {
    titular = 'Por debajo del plan'
  } else {
    titular = 'Muy por debajo del plan'
  }
  if (parados && ritmo.tono !== 'ok') titular += ` · ${plural(parados, 'puesto parado', 'puestos parados')}`
  return { tono, titular, detalle: prevision + pesa }
}

export const ESTADO_PUESTO: Record<EstadoPuestoTurno, { texto: string; tono: Tono }> = {
  en_marcha: { texto: 'En marcha', tono: 'ok' },
  sin_registrar: { texto: 'Sin registrar', tono: 'aviso' },
  parado: { texto: 'Parado', tono: 'mal' },
  preparado: { texto: 'Preparado', tono: 'gris' },
  sin_orden: { texto: 'Sin orden', tono: 'gris' },
}

export const ESTADO_ORDEN: Record<EstadoOrdenTurno, { texto: string; tono: Tono }> = {
  retraso: { texto: 'Retraso', tono: 'mal' },
  en_riesgo: { texto: 'En riesgo', tono: 'aviso' },
  a_tiempo: { texto: 'A tiempo', tono: 'ok' },
  sin_ritmo: { texto: 'Sin ritmo', tono: 'gris' },
  sin_plazo: { texto: 'Sin fecha', tono: 'gris' },
}

export const FACTOR_OEE = {
  disponibilidad: 'las paradas',
  rendimiento: 'la velocidad',
  calidad: 'la chatarra',
} as const

/** Texto corto del tiempo de un puesto: parado "23 min", en marcha "hace 3 min". */
export function tiempoPuesto(estado: EstadoPuestoTurno, minutos: number | null): string | null {
  if (minutos === null) return null
  if (estado === 'parado') return fmtDuracion(minutos)
  return `últ. registro hace ${fmtDuracion(minutos)}`
}
