"""Tests de la vista Planta del panel de mando (services/panel_planta.py)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models import Incidencia, ProductionLog, Workstation
from app.services.panel_planta import resumen_planta, ventana_periodo
from tests.helpers import auth_headers, make_order, make_order_line, make_tenant

# Miércoles 28-10-2026 a las 12:00 en planta (UTC-5)
AHORA = datetime(2026, 10, 28, 17, 0, tzinfo=UTC)
LUNES = datetime(2026, 10, 26, 5, 0, tzinfo=UTC)  # lunes 00:00 en planta


def _puesto(db, tenant, code, ritmo=None):
    db.add(
        Workstation(
            tenant_id=tenant.id,
            code=code,
            name=code,
            piezas_hora_nominal=Decimal(str(ritmo)) if ritmo else None,
        )
    )
    db.commit()


def _log(db, tenant, user, order, line, cuando, cantidad, action="produce", meta=None):
    db.add(
        ProductionLog(
            tenant_id=tenant.id,
            order_id=order.id,
            line_id=line.id,
            operator_id=user.id,
            timestamp=cuando,
            action=action,
            quantity=Decimal(str(cantidad)),
            metadata_=meta or {},
        )
    )
    db.commit()


def test_ventanas_de_periodo():
    assert ventana_periodo("hoy", AHORA)[0] == datetime(2026, 10, 28, 5, 0, tzinfo=UTC)
    assert ventana_periodo("semana", AHORA)[0] == LUNES
    assert ventana_periodo("8semanas", AHORA)[0] == LUNES - timedelta(weeks=7)
    with pytest.raises(ValueError):
        ventana_periodo("año", AHORA)


def test_eficiencia_por_factores_y_puesto_que_frena(db_session, tenant, user):
    _puesto(db_session, tenant, "PERF-1", ritmo=100)
    _puesto(db_session, tenant, "PUNZ-1", ritmo=50)
    order = make_order(db_session, tenant)
    perf = make_order_line(db_session, order, workstation="PERF-1", total_quantity=1000)
    punz = make_order_line(
        db_session, order, workstation="PUNZ-1", total_quantity=1000, linea_numero=2
    )
    # PERF-1: 4 h a 80 pz/h (velocidad 80 %)
    _log(
        db_session,
        tenant,
        user,
        order,
        perf,
        LUNES + timedelta(hours=10),
        320,
        meta={"efficiency": 80, "consumedMaterial": "kg", "consumedAmount": 98},
    )
    # PUNZ-1: 2 h a 25 pz/h (velocidad 50 %) y 1 h parado
    _log(
        db_session,
        tenant,
        user,
        order,
        punz,
        LUNES + timedelta(hours=11),
        50,
        meta={"efficiency": 25},
    )
    _log(db_session, tenant, user, order, perf, LUNES + timedelta(hours=12), 2, action="scrap")
    db_session.add(
        Incidencia(
            tenant_id=tenant.id,
            puesto="PUNZ-1",
            operario_id=user.id,
            descripcion="Sin bobina",
            tipo="material",
            estado="resuelta",
            tiempo_parada_min=Decimal("60"),
            created_at=LUNES + timedelta(hours=9),
        )
    )
    db_session.commit()

    r = resumen_planta(db_session, tenant.id, "semana", AHORA)

    assert r["piezas"] == 370
    # Plan: 100×4 h + 50×(2 h + 1 h parado)
    assert r["plan"] == 550
    ef = r["eficiencia"]
    assert ef["disponibilidad"] == round(6 / 7 * 100, 1)
    assert ef["rendimiento"] == round(370 / 500 * 100, 1)
    assert ef["calidad"] == 98.0
    assert [p["puesto"] for p in r["puestos"]] == ["PUNZ-1", "PERF-1"]
    assert r["paradas"]["por_causa"] == [
        {"causa": "falta de material", "minutos": 60, "pct": 100.0}
    ]
    assert r["tendencia"][-1]["semana"] == "S44"
    assert r["tendencia"][-1]["oee"] == ef["oee"]


def test_entregas_a_tiempo_y_periodo_anterior(db_session, tenant, user):
    _puesto(db_session, tenant, "PERF-1", ritmo=100)
    a_tiempo = make_order(db_session, tenant, numero="A")
    tarde = make_order(db_session, tenant, numero="B")
    for orden, entrega in ((a_tiempo, AHORA), (tarde, LUNES)):
        orden.estado = "completed"
        orden.fecha_entrega = entrega
        line = make_order_line(db_session, orden, workstation="PERF-1")
        _log(
            db_session,
            tenant,
            user,
            orden,
            line,
            LUNES + timedelta(hours=20),
            10,
            meta={"efficiency": 100},
        )
    # Semana anterior: 5 piezas
    _log(
        db_session,
        tenant,
        user,
        a_tiempo,
        line,
        LUNES - timedelta(days=2),
        5,
        meta={"efficiency": 100},
    )

    r = resumen_planta(db_session, tenant.id, "semana", AHORA)

    assert r["entregas"] == {"total": 2, "a_tiempo": 1, "tarde": ["B"]}
    assert r["anterior"]["piezas"] == 5


def test_sin_horas_registradas_no_hay_eficiencia(db_session, tenant):
    _puesto(db_session, tenant, "PERF-1", ritmo=100)

    r = resumen_planta(db_session, tenant.id, "hoy", AHORA)

    assert r["eficiencia"] is None
    assert r["plan"] is None
    assert all(s["oee"] is None for s in r["tendencia"])


def test_endpoint_planta(db_session, tenant):
    from tests.test_auth_roles import _client

    otro = make_tenant(db_session, name="Otro", slug="otro")
    _puesto(db_session, otro, "AJENO-1", ritmo=50)
    sup = _client(
        db_session, auth_headers(db_session, tenant, role="supervisor", email="s@t.local")
    )
    r = sup.get("/api/v1/supervisor/planta?periodo=8semanas")
    assert r.status_code == 200
    assert r.json()["puestos"] == []
    assert sup.get("/api/v1/supervisor/planta?periodo=año").status_code == 400
    op = _client(db_session, auth_headers(db_session, tenant, role="operator", email="o@t.local"))
    assert op.get("/api/v1/supervisor/planta").status_code == 403
