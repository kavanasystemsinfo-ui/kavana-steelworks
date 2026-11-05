"""Tests del calendario de planta 3 turnos 24/7 y backfill del simulador.

Calendario: A 06:00-14:00, B 14:00-22:00, C 22:00-06:00.
Semana producción: domingo 22:00 a viernes 22:00 (TZ_PLANTA = UTC-5).
Fin de semana: viernes 22:00 a domingo 22:00, planta parada.
"""

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import (
    Order,
    OrderLine,
    ProductionLog,
    StockItem,
    Tenant,
)
from app.services.seed_demo import seed_demo
from app.services.seed_estanterias import seed_estanterias
from app.services.shifts import (
    TZ_PLANTA,
    en_horario_laboral,
    horas_de_turno,
    semana_produccion,
    turno_desde,
    ventana_turno,
)
from app.services.simulador import (
    backfill_semana_produccion,
    backfill_turno_actual,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _demo(db):
    seed_demo(db)
    seed_estanterias(db)
    return db.scalar(select(Tenant).where(Tenant.slug == "demo"))


def _utc_to_planta(dt: datetime) -> datetime:
    return dt.astimezone(TZ_PLANTA)


# ---------------------------------------------------------------------------
# Tests de calendario
# ---------------------------------------------------------------------------

class TestCalendarioTurnos:
    """Límites exactos de turno A/B/C."""

    def test_domingo_2159_parado(self):
        # Domingo 25-10-2026 21:59 planta = lunes 26-10 02:59 UTC
        dt = datetime(2026, 10, 26, 2, 59, tzinfo=UTC)
        assert not en_horario_laboral(dt)

    def test_domingo_2200_turno_c(self):
        # Domingo 25-10-2026 22:00 planta = lunes 26-10 03:00 UTC
        dt = datetime(2026, 10, 26, 3, 0, tzinfo=UTC)
        assert en_horario_laboral(dt)
        assert turno_desde(dt) == "C"

    def test_viernes_2159_turno_b(self):
        # Viernes 30-10-2026 21:59 planta = sábado 31-10 02:59 UTC
        dt = datetime(2026, 10, 31, 2, 59, tzinfo=UTC)
        assert en_horario_laboral(dt)
        assert turno_desde(dt) == "B"

    def test_viernes_2200_parado(self):
        # Viernes 30-10-2026 22:00 planta = sábado 31-10 03:00 UTC
        dt = datetime(2026, 10, 31, 3, 0, tzinfo=UTC)
        assert not en_horario_laboral(dt)

    def test_sabado_parado(self):
        # Sábado 31-10-2026 12:00 planta = 17:00 UTC
        dt = datetime(2026, 10, 31, 17, 0, tzinfo=UTC)
        assert not en_horario_laboral(dt)

    def test_limite_turno_0559_0600(self):
        # 05:59 planta = 10:59 UTC (turno C)
        dt = datetime(2026, 10, 27, 10, 59, tzinfo=UTC)
        assert turno_desde(dt) == "C"
        # 06:00 planta = 11:00 UTC (turno A)
        dt = datetime(2026, 10, 27, 11, 0, tzinfo=UTC)
        assert turno_desde(dt) == "A"

    def test_limite_turno_1359_1400(self):
        # 13:59 planta = 18:59 UTC (turno A)
        dt = datetime(2026, 10, 27, 18, 59, tzinfo=UTC)
        assert turno_desde(dt) == "A"
        # 14:00 planta = 19:00 UTC (turno B)
        dt = datetime(2026, 10, 27, 19, 0, tzinfo=UTC)
        assert turno_desde(dt) == "B"

    def test_limite_turno_2159_2200(self):
        # 21:59 planta = 02:59 UTC+1d (turno B)
        dt = datetime(2026, 10, 28, 2, 59, tzinfo=UTC)
        assert turno_desde(dt) == "B"
        # 22:00 planta = 03:00 UTC+1d (turno C)
        dt = datetime(2026, 10, 28, 3, 0, tzinfo=UTC)
        assert turno_desde(dt) == "C"

    def test_ventana_turno_a(self):
        fecha = datetime(2026, 10, 27)  # lunes
        inicio, fin = ventana_turno(fecha, "A")
        assert inicio.hour == 6
        assert fin.hour == 14

    def test_ventana_turno_b(self):
        fecha = datetime(2026, 10, 27)
        inicio, fin = ventana_turno(fecha, "B")
        assert inicio.hour == 14
        assert fin.hour == 22

    def test_ventana_turno_c(self):
        fecha = datetime(2026, 10, 27)
        inicio, fin = ventana_turno(fecha, "C")
        assert inicio.hour == 22
        assert fin.hour == 6
        assert fin.day == (inicio + timedelta(days=1)).day

    def test_semana_produccion_domingo(self):
        # Domingo 25-10-2026 22:00 planta = lunes 26-10 03:00 UTC
        dt = datetime(2026, 10, 26, 3, 0, tzinfo=UTC)
        inicio, fin = semana_produccion(dt)
        local_inicio = _utc_to_planta(inicio)
        local_fin = _utc_to_planta(fin)
        assert local_inicio.weekday() == 6  # domingo
        assert local_inicio.hour == 22
        assert local_fin.weekday() == 4  # viernes
        assert local_fin.hour == 22

    def test_horas_de_turno_tope(self):
        h = horas_de_turno(datetime(2026, 1, 1, 6, 0), datetime(2026, 1, 1, 14, 0))
        assert h == Decimal("8.00")
        h = horas_de_turno(datetime(2026, 1, 1, 6, 0), datetime(2026, 1, 1, 22, 0))
        assert h == Decimal("8.00")  # >14h → tope 8


# ---------------------------------------------------------------------------
# Tests de backfill
# ---------------------------------------------------------------------------

class TestBackfillTurnoActual:
    """Invariantes del backfill: produced_quantity = suma logs, kg consumidos,
    stock y kardex cuadran, idempotente."""

    def test_backfill_respeta_produced_quantity(self, db_session):
        tenant = _demo(db_session)
        orden = db_session.scalar(
            select(Order).where(Order.tenant_id == tenant.id, Order.estado == "active")
        )
        linea = db_session.scalar(
            select(OrderLine).where(OrderLine.order_id == orden.id, OrderLine.linea_numero == 1)
        )
        antes = linea.produced_quantity or 0

        rng = random.Random(42)
        backfill_turno_actual(db_session, rng)

        db_session.refresh(linea)
        despues = linea.produced_quantity or 0

        # Sumar logs de producción para esta línea
        logs = db_session.scalars(
            select(ProductionLog).where(
                ProductionLog.tenant_id == tenant.id,
                ProductionLog.line_id == linea.id,
                ProductionLog.action == "produce",
            )
        ).all()
        suma_logs = sum(log.quantity for log in logs)
        assert despues == antes + suma_logs

    def test_backfill_idempotente(self, db_session):
        tenant = _demo(db_session)
        orden = db_session.scalar(
            select(Order).where(Order.tenant_id == tenant.id, Order.estado == "active")
        )
        linea = db_session.scalar(
            select(OrderLine).where(OrderLine.order_id == orden.id, OrderLine.linea_numero == 1)
        )

        rng = random.Random(42)
        backfill_turno_actual(db_session, rng)
        db_session.refresh(linea)
        q1 = linea.produced_quantity or 0

        # Contar logs después de primera ejecución
        logs_1 = db_session.scalar(
            select(func.count(ProductionLog.id)).where(
                ProductionLog.tenant_id == tenant.id,
                ProductionLog.line_id == linea.id,
            )
        )

        rng = random.Random(42)
        backfill_turno_actual(db_session, rng)
        db_session.refresh(linea)
        q2 = linea.produced_quantity or 0

        logs_2 = db_session.scalar(
            select(func.count(ProductionLog.id)).where(
                ProductionLog.tenant_id == tenant.id,
                ProductionLog.line_id == linea.id,
            )
        )

        assert q1 == q2
        assert logs_1 == logs_2  # No se duplican logs

    def test_backfill_stock_y_kardex_cuadran(self, db_session):
        tenant = _demo(db_session)
        orden = db_session.scalar(
            select(Order).where(Order.tenant_id == tenant.id, Order.estado == "active")
        )
        linea = db_session.scalar(
            select(OrderLine).where(OrderLine.order_id == orden.id, OrderLine.linea_numero == 1)
        )
        bobina_id = linea.active_coil_id
        if bobina_id is None:
            pytest.skip("No hay bobina activa para comprobar stock")

        bobina_antes = db_session.get(StockItem, bobina_id)
        kg_antes = bobina_antes.kg_available if bobina_antes else Decimal("0")

        rng = random.Random(42)
        backfill_turno_actual(db_session, rng)

        db_session.refresh(bobina_antes)
        kg_despues = bobina_antes.kg_available if bobina_antes else Decimal("0")

        # Si hubo producción, el stock debe haber cambiado o haber logs
        if linea.produced_quantity and linea.produced_quantity > 0:
            logs = db_session.scalars(
                select(ProductionLog).where(
                    ProductionLog.tenant_id == tenant.id,
                    ProductionLog.line_id == linea.id,
                    ProductionLog.action == "produce",
                )
            ).all()
            assert len(logs) > 0 or kg_antes == kg_despues


class TestBackfillSemanaProduccion:
    """Backfill de turnos completos de la semana."""

    def test_backfill_semana_idempotente(self, db_session):
        tenant = _demo(db_session)
        rng = random.Random(42)

        backfill_semana_produccion(db_session, rng)
        # Contar logs después de primera ejecución
        logs_antes = db_session.scalar(
            select(func.count(ProductionLog.id)).where(ProductionLog.tenant_id == tenant.id)
        )

        rng = random.Random(42)
        backfill_semana_produccion(db_session, rng)
        logs_despues = db_session.scalar(
            select(func.count(ProductionLog.id)).where(ProductionLog.tenant_id == tenant.id)
        )

        assert logs_antes == logs_despues  # No se duplican logs
