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


def test_horario_laboral_de_planta():
    from datetime import UTC, datetime

    from app.services.simulador import en_horario_laboral

    # Planta en UTC-5. Lunes 26-10-2026 12:00 UTC = 07:00 en planta
    assert en_horario_laboral(datetime(2026, 10, 26, 12, 0, tzinfo=UTC))
    # Lunes 04:00 UTC = domingo 23:00 en planta
    assert not en_horario_laboral(datetime(2026, 10, 26, 4, 0, tzinfo=UTC))
    # Martes 03:30 UTC = lunes 22:30 en planta: turno C, fuera
    assert not en_horario_laboral(datetime(2026, 10, 27, 3, 30, tzinfo=UTC))
    # Sábado 31-10 a mediodía
    assert not en_horario_laboral(datetime(2026, 10, 31, 17, 0, tzinfo=UTC))


def test_la_demo_no_se_agota_en_muchos_ticks(db_session):
    """150 ticks (~12 h a 5 min): sin errores, con órdenes y bobinas repuestas
    y sin ninguna bobina activa en dos líneas a la vez."""
    from collections import Counter

    from app.models import Order, OrderLine, StockItem

    tenant = _demo(db_session)
    rng = random.Random(11)
    acciones = []
    for _ in range(150):
        acciones += simular_tick(db_session, rng)["acciones"]

    # Una orden puede terminar en el último tick: la repone el tick siguiente
    from app.services.simulador import _reponer_ordenes

    _reponer_ordenes(db_session, tenant.id, rng)
    activas = db_session.scalars(
        select(Order).where(Order.tenant_id == tenant.id, Order.estado == "active")
    ).all()
    assert len(activas) >= 2
    assert any(a.startswith("lanza ") for a in acciones), "no repuso órdenes"
    assert any(a.startswith("recibe SIM-") for a in acciones), "no repuso bobinas"
    assert any(a.startswith(("fin de bobina", "desvincula")) for a in acciones)

    activas_por_bobina = Counter(
        db_session.scalars(
            select(OrderLine.active_coil_id).where(OrderLine.active_coil_id.is_not(None))
        ).all()
    )
    assert all(n == 1 for n in activas_por_bobina.values())

    recibidas = db_session.scalars(
        select(StockItem).where(StockItem.coil_id.like("SIM-%"))
    ).all()
    assert recibidas and all(b.tenant_id == tenant.id for b in recibidas)

    for fila in costes_por_orden(db_session, tenant.id):
        assert fila["real_total"] >= fila["real_material"]
        assert fila["piezas"] <= fila["objetivo"]


def test_el_backend_arranca_y_para_el_bucle_del_simulador(monkeypatch):
    """Con STEELWORKS_SIMULADOR_MINUTOS > 0 la app arranca el bucle y lo
    cancela al apagarse, sin romper el arranque."""
    from fastapi.testclient import TestClient

    import app.main as main

    monkeypatch.setattr(main.settings, "simulador_minutos", 5)
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200


def _siguiente_turno():
    """Primer tick del turno siguiente (06:00 o 14:00 en planta)."""
    from datetime import UTC, datetime, timedelta

    from app.services.shifts import TZ_PLANTA

    local = datetime.now(UTC).astimezone(TZ_PLANTA)
    if local.hour < 6:
        return local.replace(hour=6, minute=1)
    if local.hour < 14:
        return local.replace(hour=14, minute=1)
    return (local + timedelta(days=1)).replace(hour=6, minute=1)


def _balance(db, tenant, desde):
    logs = db.scalars(
        select(ProductionLog).where(
            ProductionLog.tenant_id == tenant.id, ProductionLog.timestamp >= desde
        )
    ).all()
    material = sum(
        float(log.metadata_.get("consumedAmount") or 0)
        for log in logs
        if log.action == "produce" and log.metadata_.get("consumedMaterial") == "kg"
    )
    chatarra = sum(float(log.quantity or 0) for log in logs if log.action == "scrap")
    return material, chatarra


def test_la_chatarra_del_simulador_es_realista(db_session):
    """Balance de masa: el simulador desperdicia un 2-6 % por bobina, que solo
    aparece al medir. Sin restos de cientos de kilos tirados al cambiar de
    bobina (antes, 5,8 %) ni una planta perfecta (0,2 %)."""
    from datetime import UTC, datetime

    tenant = _demo(db_session)
    inicio = datetime.now(UTC)
    rng = random.Random(11)
    for _ in range(150):
        simular_tick(db_session, rng)
    simular_tick(db_session, rng, ahora=_siguiente_turno())  # cierre de turno: se mide

    material, chatarra = _balance(db_session, tenant, inicio)
    assert material > 0
    assert 0.01 < chatarra / (material + chatarra) < 0.07


def test_el_cambio_de_turno_mide_la_bobina_y_la_deja_montada(db_session):
    from app.models import OrderLine, StockItem

    _demo(db_session)
    rng = random.Random(5)
    for _ in range(3):
        simular_tick(db_session, rng)

    acciones = simular_tick(db_session, rng, ahora=_siguiente_turno())["acciones"]

    medidas = [a.split()[4] for a in acciones if a.startswith("cierre de turno")]
    assert medidas, acciones
    sigue = {
        si.coil_id
        for si in db_session.scalars(
            select(StockItem).where(
                StockItem.id.in_(
                    select(OrderLine.active_coil_id).where(OrderLine.active_coil_id.is_not(None))
                )
            )
        )
    }
    for codigo in medidas:  # el relevo encuentra la bobina cargada (salvo que se acabe)
        acabada = any(
            codigo in a and a.startswith(("fin de bobina", "desvincula")) for a in acciones
        )
        assert codigo in sigue or acabada, (codigo, acciones)
