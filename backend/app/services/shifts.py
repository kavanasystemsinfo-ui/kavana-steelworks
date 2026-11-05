"""Turnos A/B/C y calendario de planta (Fase 1, ciclo de vida).

La planta trabaja 24 h en 3 turnos: A 06:00-14:00, B 14:00-22:00, C 22:00-06:00.
La semana de producción empieza el domingo a las 22:00 (turno C) y termina el
viernes a las 22:00 (fin del turno B). De viernes 22:00 a domingo 22:00 la
planta está parada. Zona horaria: la de planta (TZ_PLANTA).
"""

from datetime import UTC, datetime, time, timedelta, timezone

TZ_PLANTA = timezone(timedelta(hours=-5))  # America/Bogota, sin DST

TURNOS = {
    "A": (6, 14),
    "B": (14, 22),
    "C": (22, 6),
}


def turno_desde(ts: datetime) -> str:
    """Turno A/B/C del instante dado según el horario de planta.

    A 06:00-13:59, B 14:00-21:59, C 22:00-05:59.
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


def en_horario_laboral(ahora: datetime | None = None) -> bool:
    """True si la planta está en horario de producción (dom 22:00 - vie 22:00).

    La semana de producción va del domingo 22:00 al viernes 22:00 en TZ_PLANTA.
    Fuera de esa ventana (vie 22:00 - dom 22:00) la planta está parada.
    """
    from app.services.shifts import TZ_PLANTA

    local = (ahora or datetime.now(UTC)).astimezone(TZ_PLANTA)
    # weekday: 0=lunes ... 6=domingo
    wd = local.weekday()
    hora = local.hour
    minuto = local.minute

    if wd == 6:  # domingo
        # Producción empieza a las 22:00
        return hora >= 22
    if wd == 4:  # viernes
        # Producción termina a las 22:00
        return hora < 22
    if wd == 5:  # sábado
        return False
    # lunes a jueves: siempre en producción
    return True


def ventana_turno(fecha: datetime, turno: str) -> tuple[datetime, datetime]:
    """Inicio y fin (aware, horario de planta) del turno A/B/C de esa fecha.

    Para el turno C: empieza a las 22:00 de la fecha y termina a las 06:00
    del día siguiente. La fecha se refiere al día en que empieza el turno.
    """
    if turno not in TURNOS:
        raise ValueError("turno debe ser A, B o C")
    h_inicio, h_fin = TURNOS[turno]

    # fecha es un date o datetime; normalizar a date en TZ_PLANTA
    if isinstance(fecha, datetime):
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=UTC)
        fecha_local = fecha.astimezone(TZ_PLANTA).date()
    else:
        fecha_local = fecha

    inicio = datetime.combine(fecha_local, time(hour=h_inicio), tzinfo=TZ_PLANTA)

    if turno == "C":
        fin = inicio + timedelta(hours=8)  # 22:00 a 06:00 = 8h
    else:
        fin = inicio + timedelta(hours=8)  # 06-14 y 14-22 = 8h

    return inicio, fin


def semana_produccion(fecha: datetime) -> tuple[datetime, datetime]:
    """Inicio (dom 22:00) y fin (vie 22:00) de la semana de producción.

    Devuelve tupla (inicio, fin) ambas aware en TZ_PLANTA.
    """
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=UTC)
    local = fecha.astimezone(TZ_PLANTA)
    wd = local.weekday()  # 0=lunes ... 6=domingo
    hora = local.hour

    # Encontrar el domingo 22:00 que inicia la semana
    if wd == 6 and hora >= 22:
        # Domingo después de las 22:00: esta semana empezó hoy a las 22:00
        inicio_semana = datetime.combine(local.date(), time(22, 0), tzinfo=TZ_PLANTA)
    elif wd == 6 and hora < 22:
        # Domingo antes de las 22:00: la semana empezó el domingo anterior
        inicio_semana = datetime.combine(
            local.date() - timedelta(days=7), time(22, 0), tzinfo=TZ_PLANTA
        )
    else:
        # Lunes a sábado: restar días hasta el domingo anterior
        dias_al_domingo = (wd + 1) % 7  # lunes=1, martes=2, ..., sábado=6, domingo=0
        if wd == 0:  # lunes
            dias_al_domingo = 1
        elif wd == 6:  # domingo (antes de 22:00 ya manejado arriba)
            dias_al_domingo = 0
        domingo = local.date() - timedelta(days=dias_al_domingo)
        inicio_semana = datetime.combine(domingo, time(22, 0), tzinfo=TZ_PLANTA)

    fin_semana = inicio_semana + timedelta(days=5)  # viernes 22:00
    return inicio_semana, fin_semana


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