import { useEffect, useRef, useState } from 'react'

/**
 * Recordatorios de autocontrol NO bloqueantes (spec 04 §3.2.5, decisión
 * 2026-05-18). Puramente de UI: el backend solo expone el estado y aquí se
 * calculan los avisos:
 *
 * - Primer aviso: 15 min desde el inicio del turno (UserShift activo) sin
 *   registrar ningún autocontrol. Se muestra UNA sola vez.
 * - Ciclo periódico: cada 2 h desde el último autocontrol registrado.
 *
 * No bloquean la interfaz ni detienen la línea (un bloqueo rígido afectaría
 * el OEE del turno). El estado local (sessionStorage) sobrevive recargas:
 * firstQualityReminderShown y lastPeriodicQualityReminderTime.
 *
 * Devuelve { notifyCheckRegistered, reminderToast }: llamar a notify tras
 * registrar un autocontrol con éxito para reiniciar el temporizador
 * periódico; reminderToast es el mensaje a renderizar (null si no hay aviso).
 */

export const REMINDER_FIRST_MIN = 15
export const REMINDER_PERIODIC_MIN = 120
const CHECK_INTERVAL_MS = 30_000
const TOAST_MS = 8_000

const KEY_SHOWN = 'kavana_first_qc_reminder_shown'
const KEY_LAST_PERIODIC = 'kavana_last_periodic_qc_reminder'

function initialLastPeriodic(): number | null {
  const raw = sessionStorage.getItem(KEY_LAST_PERIODIC)
  return raw ? Number(raw) : null
}

export interface QualityReminders {
  notifyCheckRegistered: () => void
  reminderToast: string | null
}

export function useQualityReminders(): QualityReminders {
  const [reminderToast, setReminderToast] = useState<string | null>(null)
  const shownRef = useRef(sessionStorage.getItem(KEY_SHOWN) === '1')
  const lastPeriodicRef = useRef<number | null>(initialLastPeriodic())
  const stateRef = useRef<{ shift_started_at: string | null; last_check_at: string | null } | null>(null)

  const showToast = (msg: string) => {
    setReminderToast(msg)
    window.setTimeout(() => setReminderToast(null), TOAST_MS)
  }

  const check = () => {
    const state = stateRef.current
    if (!state) return // estado aún no cargado (o fetch falló)
    const { shift_started_at, last_check_at } = state
    const now = Date.now()

    // 1) Primer aviso: 15 min desde el turno sin controles (una vez)
    if (!shownRef.current && last_check_at === null && shift_started_at) {
      const inicio = new Date(shift_started_at).getTime()
      if (now - inicio >= REMINDER_FIRST_MIN * 60_000) {
        shownRef.current = true
        sessionStorage.setItem(KEY_SHOWN, '1')
        showToast('⏰ Recuerda registrar el autocontrol de calidad del turno')
        return
      }
    }

    // 2) Ciclo periódico: 2 h desde el último control registrado
    if (last_check_at) {
      const ultimo = new Date(last_check_at).getTime()
      const ultimoPeriodico = lastPeriodicRef.current
      if (now - ultimo >= REMINDER_PERIODIC_MIN * 60_000) {
        if (ultimoPeriodico === null || now - ultimoPeriodico >= REMINDER_PERIODIC_MIN * 60_000) {
          lastPeriodicRef.current = now
          sessionStorage.setItem(KEY_LAST_PERIODIC, String(now))
          showToast('⏰ Toca un nuevo autocontrol de calidad (cada 2 h)')
        }
      }
    }
  }

  // Carga el estado del backend una vez (el operario está autenticado).
  // Al cargar, comprueba de inmediato (no espera el primer tick del timer).
  useEffect(() => {
    let alive = true
    fetch('/api/v1/quality/reminder-state')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error('reminder-state'))))
      .then((data) => {
        if (!alive || !data) return
        stateRef.current = data
        check()
      })
      .catch(() => {}) // silencioso: best-effort
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Comprobación periódica (30 s) del estado
  useEffect(() => {
    const id = window.setInterval(check, CHECK_INTERVAL_MS)
    return () => window.clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Resetea el ciclo tras un autocontrol registrado con éxito
  const notifyCheckRegistered = () => {
    shownRef.current = true
    sessionStorage.setItem(KEY_SHOWN, '1')
    lastPeriodicRef.current = Date.now()
    sessionStorage.setItem(KEY_LAST_PERIODIC, String(lastPeriodicRef.current))
    stateRef.current = {
      shift_started_at: stateRef.current?.shift_started_at ?? null,
      last_check_at: new Date().toISOString(),
    }
    setReminderToast(null)
  }

  return { notifyCheckRegistered, reminderToast }
}
