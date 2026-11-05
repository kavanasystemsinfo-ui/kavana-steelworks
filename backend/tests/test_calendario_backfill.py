"""Calendario de planta (3 turnos, dom 22:00 a vie 22:00, hora de Madrid) y relleno
del hueco del simulador con horas pasadas."""

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models import OrderLine, ProductionLog
from app.services import simulador
from app.services.seed_demo import buscar_tenant_demo, seed_demo
from app.services.seed_estanterias import seed_estanterias
from app.services.shifts import (
    TZ_PLANTA,
    en_horario_laboral,
    semana_produccion,
    turno_desde,
    ventana_turno,
)
from app.services.simulador import rellenar_hueco, simular_tick

MADRID = ZoneInfo("Europe/Madrid")


def madrid(anio, mes, dia, hora, minuto=0) -> datetime:
    return datetime(anio, mes, dia, hora, minuto, tzinfo=MADRID)


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


def test_la_zona_de_planta_es_madrid():
    assert TZ_PLANTA.key == "Europe/Madrid"


class TestCalendario:
    @pytest.mark.parametrize(
        ("momento", "esperado"),
        [
            (madrid(2026, 11, 1, 21, 59), False),  # domingo antes de las 22:00
            (madrid(2026, 11, 1, 22, 0), True),  # domingo 22:00: empieza el turno C
            (madrid(2026, 11, 2, 3, 0), True),  # lunes de madrugada
            (madrid(2026, 11, 4, 12, 0), True),  # miércoles
            (madrid(2026, 11, 6, 21, 59), True),  # viernes 21:59: aún turno B
            (madrid(2026, 11, 6, 22, 0), False),  # viernes 22:00: planta parada
            (madrid(2026, 11, 7, 12, 0), False),  # sábado
            (madrid(2026, 11, 8, 12, 0), False),  # domingo de día
        ],
    )
    def test_horario_de_produccion(self, momento, esperado):
        assert en_horario_laboral(momento) is esperado

    def test_el_horario_se_mide_en_hora_de_madrid_aunque_llegue_en_utc(self):
        # 21:59 y 22:00 en Madrid (invierno, UTC+1) expresados en UTC
        assert en_horario_laboral(datetime(2026, 11, 1, 20, 59, tzinfo=UTC)) is False
        assert en_horario_laboral(datetime(2026, 11, 1, 21, 0, tzinfo=UTC)) is True

    @pytest.mark.parametrize(
        ("hora", "minuto", "turno"),
        [(5, 59, "C"), (6, 0, "A"), (13, 59, "A"), (14, 0, "B"), (21, 59, "B"), (22, 0, "C")],
    )
    def test_limites_de_turno(self, hora, minuto, turno):
        assert turno_desde(madrid(2026, 11, 4, hora, minuto)) == turno

    def test_ventana_de_cada_turno(self):
        dia = madrid(2026, 11, 4, 0).date()
        assert ventana_turno(dia, "A") == (madrid(2026, 11, 4, 6), madrid(2026, 11, 4, 14))
        assert ventana_turno(dia, "B") == (madrid(2026, 11, 4, 14), madrid(2026, 11, 4, 22))
        assert ventana_turno(dia, "C") == (madrid(2026, 11, 4, 22), madrid(2026, 11, 5, 6))

    def test_el_turno_c_dura_9_horas_al_acabar_el_horario_de_verano(self):
        # El 25-10-2026 se retrasa el reloj: la noche del sábado 24 al domingo 25 dura 9 h
        inicio, fin = ventana_turno(madrid(2026, 10, 24, 0).date(), "C")
        assert fin.astimezone(UTC) - inicio.astimezone(UTC) == timedelta(hours=9)
        assert fin == madrid(2026, 10, 25, 6)

    def test_el_turno_c_dura_7_horas_al_empezar_el_horario_de_verano(self):
        # El 29-03-2026 se adelanta el reloj: la noche del sábado 28 al domingo 29 dura 7 h
        inicio, fin = ventana_turno(madrid(2026, 3, 28, 0).date(), "C")
        assert fin.astimezone(UTC) - inicio.astimezone(UTC) == timedelta(hours=7)
        assert fin == madrid(2026, 3, 29, 6)

    def test_ventana_de_turno_rechaza_turnos_desconocidos(self):
        with pytest.raises(ValueError):
            ventana_turno(madrid(2026, 11, 4, 0).date(), "D")

    @pytest.mark.parametrize(
        "momento",
        [madrid(2026, 11, 4, 12), madrid(2026, 11, 1, 22), madrid(2026, 11, 6, 21, 59)],
    )
    def test_semana_de_produccion(self, momento):
        inicio, fin = semana_produccion(momento)
        assert inicio == madrid(2026, 11, 1, 22)  # domingo 22:00
        assert fin == madrid(2026, 11, 6, 22)  # viernes 22:00

    def test_el_domingo_de_dia_cae_en_la_semana_que_acaba_de_terminar(self):
        inicio, fin = semana_produccion(madrid(2026, 11, 8, 12))
        assert inicio == madrid(2026, 11, 1, 22)
        assert fin == madrid(2026, 11, 6, 22)


@pytest.fixture(autouse=True)
def _sin_marca_de_relleno(monkeypatch):
    monkeypatch.setattr(simulador, "_ultimo_relleno", None)


# Miércoles 16-01-2030 a las 12:00 en planta: muy posterior a cualquier dato de la semilla
AHORA = madrid(2030, 1, 16, 12)


def _demo(db):
    seed_demo(db)
    seed_estanterias(db)
    return buscar_tenant_demo(db)


def _logs(db, tenant):
    return db.scalars(
        select(ProductionLog)
        .where(ProductionLog.tenant_id == tenant.id, ProductionLog.action == "produce")
        .order_by(ProductionLog.timestamp)
    ).all()


def _piezas_por_linea(db):
    return {ln.id: ln.produced_quantity or Decimal("0") for ln in db.scalars(select(OrderLine))}


def _suma_de_logs_por_linea(db, tenant):
    suma: dict = {}
    for log in _logs(db, tenant):
        suma[log.line_id] = suma.get(log.line_id, Decimal("0")) + log.quantity
    return suma


class TestRelleno:
    def test_los_registros_llevan_horas_pasadas_dentro_del_hueco(self, db_session):
        tenant = _demo(db_session)
        antes = {log.id for log in _logs(db_session, tenant)}

        res = rellenar_hueco(db_session, AHORA, random.Random(3))

        assert res["pasos"] > 0
        nuevos = [_aware(log.timestamp) for log in _logs(db_session, tenant) if log.id not in antes]
        assert nuevos, "el relleno no registró producción"
        assert min(nuevos) >= semana_produccion(AHORA)[0]
        assert max(nuevos) <= AHORA
        # Repartido a lo largo de varias horas, no todo en el mismo instante
        horas = {t.astimezone(MADRID).replace(minute=0, second=0, microsecond=0) for t in nuevos}
        assert len(horas) >= 6

    def test_cada_registro_lleva_el_turno_de_su_hora(self, db_session):
        tenant = _demo(db_session)
        antes = {log.id for log in _logs(db_session, tenant)}
        rellenar_hueco(db_session, AHORA, random.Random(3))
        nuevos = [log for log in _logs(db_session, tenant) if log.id not in antes]
        assert nuevos
        for log in nuevos:
            assert log.shift == turno_desde(_aware(log.timestamp))
        assert {log.shift for log in nuevos} >= {"A", "B", "C"}

    def test_las_piezas_de_cada_linea_cuadran_con_sus_registros(self, db_session):
        tenant = _demo(db_session)
        piezas_antes = _piezas_por_linea(db_session)
        logs_antes = _suma_de_logs_por_linea(db_session, tenant)

        rellenar_hueco(db_session, AHORA, random.Random(5))
        db_session.expire_all()

        piezas_despues = _piezas_por_linea(db_session)
        logs_despues = _suma_de_logs_por_linea(db_session, tenant)
        hubo_produccion = False
        for linea_id, piezas in piezas_despues.items():
            delta_piezas = piezas - piezas_antes.get(linea_id, Decimal("0"))
            delta_logs = logs_despues.get(linea_id, Decimal("0")) - logs_antes.get(
                linea_id, Decimal("0")
            )
            assert delta_piezas == delta_logs, linea_id
            hubo_produccion = hubo_produccion or delta_piezas > 0
        assert hubo_produccion

    def test_es_idempotente(self, db_session):
        tenant = _demo(db_session)
        rellenar_hueco(db_session, AHORA, random.Random(3))
        total = len(_logs(db_session, tenant))

        # Aunque se pierda la marca en memoria (reinicio), no hay otro tramo completo que añadir
        simulador._ultimo_relleno = None
        segundo = rellenar_hueco(db_session, AHORA, random.Random(4))

        assert segundo["pasos"] == 0
        assert len(_logs(db_session, tenant)) == total

    def test_de_viernes_a_domingo_no_se_simula_nada(self, db_session):
        tenant = _demo(db_session)
        sabado = madrid(2030, 1, 19, 12)
        rellenar_hueco(db_session, sabado, random.Random(3))
        cierre = madrid(2030, 1, 18, 22)  # viernes 22:00
        posteriores = [
            log
            for log in _logs(db_session, tenant)
            if cierre < _aware(log.timestamp) <= sabado
        ]
        assert posteriores == []

    def test_sin_tenant_demo_no_hace_nada(self, db_session, tenant):
        res = rellenar_hueco(db_session, AHORA)
        assert res["tenant"] is None
        assert res["pasos"] == 0


class TestHoraDelRegistro:
    def test_sin_instante_el_registro_lleva_la_hora_actual(self, db_session):
        tenant = _demo(db_session)
        antes = {log.id for log in _logs(db_session, tenant)}
        simular_tick(db_session, random.Random(42))
        ahora = datetime.now(UTC)
        nuevos = [log for log in _logs(db_session, tenant) if log.id not in antes]
        assert nuevos
        assert all(abs((_aware(log.timestamp) - ahora).total_seconds()) < 120 for log in nuevos)

    def test_con_instante_el_registro_cae_dentro_del_tramo(self, db_session):
        tenant = _demo(db_session)
        antes = {log.id for log in _logs(db_session, tenant)}
        tramo_fin = madrid(2030, 1, 15, 3, 30)  # martes, turno C
        simular_tick(db_session, random.Random(42), minutos_tick=15, ahora=tramo_fin)
        nuevos = [log for log in _logs(db_session, tenant) if log.id not in antes]
        assert nuevos
        for log in nuevos:
            assert tramo_fin - timedelta(minutes=15) <= _aware(log.timestamp) <= tramo_fin
            assert log.shift == "C"
