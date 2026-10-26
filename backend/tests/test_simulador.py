"""Tests del simulador de planta de la demo (services/simulador.py)."""

import random

from sqlalchemy import select

from app.models import ProductionLog, Tenant
from app.services.costes import costes_por_orden
from app.services.seed_demo import seed_demo
from app.services.seed_estanterias import seed_estanterias
from app.services.simulador import simular_tick


def _demo(db):
    seed_demo(db)
    seed_estanterias(db)
    return db.scalar(select(Tenant).where(Tenant.slug == "demo"))


def test_sin_tenant_demo_no_hace_nada(db_session, tenant):
    resultado = simular_tick(db_session, random.Random(1))
    assert resultado["tenant"] is None
    assert resultado["acciones"] == []


def test_tick_produce_con_los_servicios_reales(db_session):
    tenant = _demo(db_session)
    logs_antes = db_session.scalar(
        select(ProductionLog.id).where(ProductionLog.tenant_id == tenant.id).limit(1)
    )
    assert logs_antes is not None  # el histórico de la semilla

    resultado = simular_tick(db_session, random.Random(42))

    assert any(a.startswith("produce") for a in resultado["acciones"]), resultado
    nuevos = db_session.scalars(
        select(ProductionLog).where(
            ProductionLog.tenant_id == tenant.id, ProductionLog.action == "produce"
        )
    ).all()
    assert any(log.metadata_.get("observaciones") == "simulador demo" for log in nuevos)


def test_varios_ticks_mantienen_el_coste_coherente(db_session):
    tenant = _demo(db_session)
    rng = random.Random(7)
    for _ in range(5):
        simular_tick(db_session, rng)

    for fila in costes_por_orden(db_session, tenant.id):
        assert fila["real_total"] >= fila["real_material"]
        assert fila["piezas"] <= fila["objetivo"]
