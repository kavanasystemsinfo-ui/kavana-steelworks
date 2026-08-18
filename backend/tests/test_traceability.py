"""Tests del servicio de trazabilidad ISO 9001 (spec 04 §2.1, §3.1).

Contrato exacto de la spec:
- log_event crea un ProductionLog inmutable (acción del enum, timestamp,
  metadata JSONB) y es best-effort: si el guardado falla, traga el error
  (DLQ en sistemas reales) y NO rompe el flujo de planta.
- get_order_trace devuelve la serie temporal completa ordenada por
  timestamp asc con operario poblado.
- get_last_active_session_start: un start/resume sin pause/finish/stopped
  posterior es sesión activa; si hay stop posterior, devuelve None.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import Order, OrderLine, ProductionLog, User
from app.services import traceability


def make_order(db, tenant, numero="OP-TRAZ"):
    o = Order(tenant_id=tenant.id, numero=numero, estado="active")
    db.add(o)
    db.commit()
    db.refresh(o)
    linea = OrderLine(order_id=o.id, linea_numero=1, total_quantity=100, estado="pending")
    db.add(linea)
    db.commit()
    db.refresh(linea)
    return o, linea


def make_operator(db, tenant, email="op.traz@test.local"):
    u = User(
        tenant_id=tenant.id,
        email=email,
        name="Operario Traza",
        password_hash="x",
        role="operator",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_log_event_crea_production_log(db_session, tenant, user):
    orden, linea = make_order(db_session, tenant)

    log = traceability.log_event(
        db_session,
        tenant_id=tenant.id,
        order_id=orden.id,
        line_id=linea.id,
        operator_id=user.id,
        action="produce",
        quantity=12,
        metadata={"activeCoilCode": "301173852", "device": "tablet"},
    )

    assert log is not None
    assert log.id is not None
    assert log.tenant_id == tenant.id
    assert log.order_id == orden.id
    assert log.line_id == linea.id
    assert log.operator_id == user.id
    assert log.action == "produce"
    assert float(log.quantity) == 12
    assert log.metadata_["activeCoilCode"] == "301173852"
    assert log.metadata_["device"] == "tablet"
    assert log.timestamp is not None

    # Persistido: recuperable desde BD
    recuperado = db_session.get(ProductionLog, log.id)
    assert recuperado is not None
    assert recuperado.action == "produce"


def test_log_event_acepta_timestamp_explicito(db_session, tenant, user):
    orden, linea = make_order(db_session, tenant)
    ts = datetime(2026, 8, 15, 8, 30, tzinfo=UTC)

    log = traceability.log_event(
        db_session,
        tenant_id=tenant.id,
        order_id=orden.id,
        line_id=linea.id,
        operator_id=user.id,
        action="start",
        timestamp=ts,
    )

    # SQLite devuelve datetime naive al leer; comparar normalizado (PG sí
    # devuelve tz-aware)
    leido = log.timestamp
    if leido.tzinfo is None:
        leido = leido.replace(tzinfo=UTC)
    assert leido == ts


def test_log_event_rechaza_accion_fuera_del_enum(db_session, tenant, user):
    orden, linea = make_order(db_session, tenant)

    with pytest.raises(ValueError):
        traceability.log_event(
            db_session,
            tenant_id=tenant.id,
            order_id=orden.id,
            line_id=linea.id,
            operator_id=user.id,
            action="explota",
        )


def test_log_event_best_effort_no_rompe_si_falla(db_session, tenant, user, monkeypatch):
    """Si el guardado falla, el error se traga (spec: DLQ) y no se propaga."""
    orden, linea = make_order(db_session, tenant)

    # Forzamos el fallo: el commit interno lanza
    def _commit_roto():
        raise RuntimeError("boom")

    monkeypatch.setattr(db_session, "commit", _commit_roto)

    log = traceability.log_event(
        db_session,
        tenant_id=tenant.id,
        order_id=orden.id,
        line_id=linea.id,
        operator_id=user.id,
        action="produce",
    )
    assert log is None


def test_get_order_trace_orden_ascendente_con_operario(db_session, tenant, user):
    orden, linea = make_order(db_session, tenant)
    base = datetime(2026, 8, 15, 8, 0, tzinfo=UTC)

    for i, action in enumerate(["start", "produce", "finish"]):
        traceability.log_event(
            db_session,
            tenant_id=tenant.id,
            order_id=orden.id,
            line_id=linea.id,
            operator_id=user.id,
            action=action,
            quantity=10 if action == "produce" else 0,
            timestamp=base + timedelta(minutes=i),
        )

    traza = traceability.get_order_trace(db_session, tenant.id, orden.id)

    assert [e.action for e in traza] == ["start", "produce", "finish"]
    assert [e.timestamp for e in traza] == sorted(e.timestamp for e in traza)
    for e in traza:
        assert e.operator is not None
        assert e.operator.id == user.id


def test_get_order_trace_filtra_por_tenant(db_session, tenant, user):
    """El aislamiento multi-tenant: otro tenant no ve los logs."""
    orden, linea = make_order(db_session, tenant)
    traceability.log_event(
        db_session,
        tenant_id=tenant.id,
        order_id=orden.id,
        line_id=linea.id,
        operator_id=user.id,
        action="start",
    )

    # Aislamiento multi-tenant: otro tenant no ve los logs
    from tests.helpers import make_tenant

    t2 = make_tenant(db_session, name="Otra Empresa")
    db_session.add(t2)
    db_session.commit()
    db_session.refresh(t2)

    traza_otro = traceability.get_order_trace(db_session, t2.id, orden.id)
    assert traza_otro == []

    traza_propio = traceability.get_order_trace(db_session, tenant.id, orden.id)
    assert len(traza_propio) == 1


def test_get_last_active_session_start_sin_stop(db_session, tenant, user):
    orden, linea = make_order(db_session, tenant)
    base = datetime(2026, 8, 15, 8, 0, tzinfo=UTC)
    traceability.log_event(
        db_session,
        tenant_id=tenant.id,
        order_id=orden.id,
        line_id=linea.id,
        operator_id=user.id,
        action="start",
        timestamp=base,
    )

    sesion = traceability.get_last_active_session_start(
        db_session, tenant.id, orden.id, linea.id, user.id
    )
    assert sesion is not None
    assert sesion.action == "start"


def test_get_last_active_session_start_con_stop_devuelve_none(db_session, tenant, user):
    orden, linea = make_order(db_session, tenant)
    base = datetime(2026, 8, 15, 8, 0, tzinfo=UTC)
    traceability.log_event(
        db_session,
        tenant_id=tenant.id,
        order_id=orden.id,
        line_id=linea.id,
        operator_id=user.id,
        action="start",
        timestamp=base,
    )
    traceability.log_event(
        db_session,
        tenant_id=tenant.id,
        order_id=orden.id,
        line_id=linea.id,
        operator_id=user.id,
        action="pause",
        timestamp=base + timedelta(minutes=30),
    )

    sesion = traceability.get_last_active_session_start(
        db_session, tenant.id, orden.id, linea.id, user.id
    )
    assert sesion is None


def test_get_last_active_session_start_elige_resume_mas_reciente(db_session, tenant, user):
    orden, linea = make_order(db_session, tenant)
    base = datetime(2026, 8, 15, 8, 0, tzinfo=UTC)
    traceability.log_event(
        db_session,
        tenant_id=tenant.id,
        order_id=orden.id,
        line_id=linea.id,
        operator_id=user.id,
        action="start",
        timestamp=base,
    )
    traceability.log_event(
        db_session,
        tenant_id=tenant.id,
        order_id=orden.id,
        line_id=linea.id,
        operator_id=user.id,
        action="resume",
        timestamp=base + timedelta(minutes=45),
    )

    sesion = traceability.get_last_active_session_start(
        db_session, tenant.id, orden.id, linea.id, user.id
    )
    assert sesion.action == "resume"
