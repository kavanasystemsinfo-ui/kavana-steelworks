import { act, render } from '@testing-library/react'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { useQualityReminders, REMINDER_FIRST_MIN } from '../lib/useQualityReminders'

let notifyCheckRegistered: () => void = () => {}

function HookProbe() {
  const { notifyCheckRegistered: notify, reminderToast } = useQualityReminders()
  notifyCheckRegistered = notify
  return (
    <div>
      <div data-testid="probe" />
      {reminderToast && <div role="status">{reminderToast}</div>}
    </div>
  )
}

async function flush() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0)
  })
}

describe('useQualityReminders (spec 04 §3.2.5: no bloqueantes)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    sessionStorage.clear()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  function stubReminderState(shift: string | null, last: string | null) {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ shift_started_at: shift, last_check_at: last }),
    }))
  }

  it('no muestra nada si el turno acaba de empezar (no han pasado 15 min)', async () => {
    stubReminderState(new Date().toISOString(), null)
    render(<HookProbe />)
    await flush()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(REMINDER_FIRST_MIN * 60_000 - 1000)
    })
    expect(document.body.textContent).not.toContain('autocontrol')
  })

  it('primer recordatorio a los 15 min sin controles (una sola vez)', async () => {
    const hace10min = new Date(Date.now() - 10 * 60_000).toISOString()
    stubReminderState(hace10min, null)
    render(<HookProbe />)
    await flush()
    // +5 min desde el fetch → 15 min desde el inicio del turno
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5 * 60_000)
    })
    expect(document.body.textContent).toContain('autocontrol')
    // esperar a que el toast se oculte (8s) y pasar un tick más del timer:
    // el primer aviso NO debe reaparecer
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9_000)
    })
    expect(document.body.textContent).not.toContain('autocontrol')
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000)
    })
    expect(document.body.textContent).not.toContain('autocontrol')
  })

  it('recordatorio periódico cada 2 h desde el último control', async () => {
    const turno = new Date(Date.now() - 3 * 60 * 60_000).toISOString()
    const ultimoCheck = new Date(Date.now() - 2 * 60 * 60_000 + 5 * 60_000).toISOString()
    stubReminderState(turno, ultimoCheck)
    render(<HookProbe />)
    await flush()
    // faltan 5 min para las 2 h desde el último check → aún no
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4 * 60_000)
    })
    expect(document.body.textContent).not.toContain('autocontrol')
    // cruza las 2 h → recordatorio (dentro de la ventana de 8s del toast)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(61_000)
    })
    expect(document.body.textContent).toContain('autocontrol')
  })

  it('al registrar un autocontrol se reinicia el ciclo (no avisa hasta 2 h después)', async () => {
    const turno = new Date(Date.now() - 3 * 60 * 60_000).toISOString()
    const ultimoCheck = new Date(Date.now() - 2 * 60 * 60_000 - 30 * 60_000).toISOString()
    stubReminderState(turno, ultimoCheck)
    render(<HookProbe />)
    await flush()
    // Ya pasaron 2h30 desde el último check → habría avisado en el check inicial
    expect(document.body.textContent).toContain('autocontrol')
    // El operario registra un autocontrol → se resetea el temporizador
    act(() => { notifyCheckRegistered() })
    // El toast viejo caduca; sin aviso nuevo hasta 2 h después del check
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9_000)
    })
    expect(document.body.textContent).not.toContain('autocontrol')
    // 1h59 después del check registrado → NO debe avisar
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2 * 60 * 60_000 - 60_000)
    })
    expect(document.body.textContent).not.toContain('Toca un nuevo autocontrol')
  })
})
