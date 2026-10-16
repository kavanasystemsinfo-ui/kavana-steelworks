# ADR-019: Desvinculación proporcional de bobina y turnos A/B/C por horario de planta

Estado: Aceptado
Fecha: 2026-10-16
Autor: Jorge Adán (KAVANA Systems)

## Contexto

Fase 1 del ciclo de vida (cierre de ciclo). El operario puede vincular una bobina a
su línea con cobro BULK por adelantado (spec 01 §3.6), pero hasta esta fase:

- No existía forma de desvincularla en el backend: el botón "Desvincular bobina" del
  panel solo limpiaba estado local (el backend seguía con `active_coil_id` y el cargo
  BULK intacto). Cambiar de bobina a mitad de línea era imposible.
- Al vincular, la orden paga la bobina ENTERA. Un reembolso total al desvincular
  devolvería coste de material ya fabricado (la producción en modo auditoría añade
  solo mano de obra), distorsionando costes por línea y la guardia de seguridad de
  kilos teóricos vs. reales.
- `UserShift.total_hours` existía en el modelo y nunca se escribía (ni en el cierre
  implícito de logout ni en el cierre huérfano que hace el login).
- `ProductionLog.shift` (turnos A/B/C) estaba declarado en el enum de acciones y era
  NULL siempre; ningún código definía horarios A/B/C en ninguna parte.
- El cierre de jornada solo ocurría implícitamente en logout, sin resumen de horas.

## Decisión

1. **Reembolso proporcional al no consumido** en `unlink_coil`: se devuelve a la
   línea solo `bobina.cantidad_disponible × coste_por_unidad` (lo que la bobina
   todavía no ha cedido a producción), se limpia `active_coil_id/active_coil_code`,
   se marca la burbuja `CoilLink.estado = "desvinculada"` y se registra una fila
   nueva de kardex inmutable (`tipo="devolucion"`, motivo "Bobina desvinculada de
   la Línea"). El stock físico no se toca. Si la bobina no es la activa → 400.
2. **Re-vincular tras desvincular sí vuelve a cobrar**: la idempotencia de
   `link_coil` ahora exige además `linea.active_coil_id == bobina.id` (antes solo
   miraba el kardex, lo que dejaba la re-vinculación sin cargo y con la bobina
   equivocada como activa).
3. **Cambiar de bobina = orquestación en el cliente** (unlink + link): sin
   endpoint `/switch`. Si la segunda llamada falla, la línea queda libre y el
   operario reintenta.
4. **Turnos A/B/C derivados del `login_time` en horario de planta America/Bogota
   (UTC-05:00 fijo, sin DST)**: A 06:00-13:59, B 14:00-21:59, C 22:00-05:59. Se
   puebla `ProductionLog.shift` en cada evento `produce` y se devuelve `turno` en el
   cierre de jornada. Sin migración: las columnas ya existían.
5. **`POST /api/v1/auth/close-shift`** con el contrato legacy spec 02 §3.11: 404
   sin turno activo, `total_hours` = horas de reloj con tope **>14h → 8.0**,
   `logout_time = now`, `status = completed`. El login huérfano y el logout calculan
   `total_hours` con la misma regla.

## Alternativas evaluadas

| Alternativa | Ventajas | Inconvenientes | Descartada por |
|---|---|---|---|
| Reembolso TOTAL al desvincular | Más simple | Devuelve coste de material ya producido: costes fantasma y guardia de kg descuadrada | Contabilidad honesta por lo fabricado |
| Endpoint `/switch` transaccional | Atomicidad | Dos operaciones ya existentes; el estado intermedio (línea libre) es seguro | YAGNI |
| Turno como campo persistido en `user_shifts` | Consulta directa | Migración + decisión de reasignación sobre turnos abiertos | La spec 02 §3.11 permite la derivación horaria |
| Cierre idempotente (200 repetido) | Reintentos cómodos | El contrato legacy dice 404 y el FE distingue estados sin ambigüedad | Spec 02 §3.11 |

## Consecuencias

- Positivas: el operario corrige un enlace equivocado sin perder lo producido; los
  costes por línea cuadran con el material realmente consumido;
  `ProductionLog.shift` empieza a poblar el dato que la trazabilidad ISO 9001
  espera; `total_hours` real alimenta el OEE de disponibilidad.
- Negativas: cambiar de bobina son dos llamadas (un fallo deja la línea libre); el
  tope >14h → 8.0 puede subestimar turnos legítimamente largos (regla legacy
  asumida); el offset de planta está fijo en -05:00 (un cambio de zona obliga a
  tocar `TZ_PLANTA`).
- Cómo se verifica: `backend/tests/test_unlink_coil.py` (11 tests: reembolso
  proporcional, kardex, burbuja, re-vinculación, endpoints), 
  `backend/tests/test_close_shift.py` (7 tests: 404, tope 8.0, turnos, login
  huérfano) y `test_produccion_registra_turno_abc_en_trazabilidad`.

## Referencias

- Código: `backend/app/services/inventory.py` (`unlink_coil`), 
  `backend/app/services/shifts.py`, `backend/app/services/auth.py` (`close_shift`),
  `backend/app/routers/stock.py`, `backend/app/routers/auth.py`,
  `frontend/src/pages/OperarioPage.tsx`, `frontend/src/lib/api.ts`.
- Spec: `docs/specs/02-ordenes-produccion.md` §3.11 (ciclo de turnos), §2.6 (UserShift).
- ADRs relacionados: ADR-014 (eventos de planta).
