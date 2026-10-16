"""Turnos A/B/C y duración de turno (Fase 1, ciclo de vida).

Derivación horaria del timestamp en horario de planta (spec 02 §3.11: "la
reconstrucción puede implementar A-B-C como derivación horaria del
timestamp"). El legacy declaraba morning/afternoon/night y nunca lo poblaba
en runtime; aquí se puebla ProductionLog.shift y se devuelve en el cierre
de jornada.
"""

from datetime import UTC, datetime, timedelta, timezone

TZ_PLANTA = timezone(timedelta(hours=-5))  # America/Bogota, sin DST


def turno_desde(ts: datetime) -> str:
    """Turno A/B/C del instante dado según el horario de planta.

    A 06:00-13:59 (mañana), B 14:00-21:59 (tarde), C 22:00-05:59 (noche).
    Un timestamp naive se trata como UTC.
    """
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    hora = ts.astimezone(TZ_PLANTA).hour
    if 6 <= hora < 14:
        return "A"
    if 14 <= hora < 22:
        return "B"
    return "C"


def horas_de_turno(login_time: datetime, logout_time: datetime) -> float:
    """Horas de reloj del turno con el tope legacy: >14h cierra a 8.0.

    El tope evita que un turno olvidado (semana de actividad) distorsione
    los KPIs de disponibilidad (spec 02 §3.11, spec 03 OEE).
    """
    if login_time.tzinfo is None:
        login_time = login_time.replace(tzinfo=UTC)
    if logout_time.tzinfo is None:
        logout_time = logout_time.replace(tzinfo=UTC)
    horas = (logout_time - login_time).total_seconds() / 3600
    if horas > 14:
        return 8.0
    if horas < 0:
        return 0.0
    return round(horas, 2)
