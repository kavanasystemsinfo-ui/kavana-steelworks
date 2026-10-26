"""Tests del monitor de puestos (services/puestos.py)."""

from datetime import UTC, datetime
from decimal import Decimal

from app.models import Incidencia, ProductionLog, Workstation
from app.services.puestos import estado_puestos
from tests.helpers import auth_headers, make_order, make_order_line


def _puesto(db, tenant, code, name=None):
    ws = Workstation(tenant_id=tenant.id, code=code, name=name or f"Puesto {code}")
    db.add(ws)
    db.commit()
    return ws


def _por_code(resultado):
    return {p["code"]: p for p in resultado}


def test_puesto_sin_ordenes_esta_libre(db_session, tenant):
    _puesto(db_session, tenant, "PERF-1", "Perfiladora 1")

    [p] = estado_puestos(db_session, tenant.id)

    assert p["name"] == "Perfiladora 1"
    assert p["estado"] == "libre"
    assert p["orden"] is None
    assert p["ultima_actividad"] is None


def test_linea_en_curso_con_bobina_y_ultima_actividad(db_session, tenant, user):
    _puesto(db_session, tenant, "PERF-1")
    order = make_order(db_session, tenant, numero="OP-MON")
    line = make_order_line(db_session, order, workstation="PERF-1", total_quantity=20)
    line.estado = "in_progress"
    line.produced_quantity = Decimal("7")
    line.active_coil_code = "COIL-123"
    db_session.add(
        ProductionLog(
            tenant_id=tenant.id,
            order_id=order.id,
            line_id=line.id,
            operator_id=user.id,
            timestamp=datetime.now(UTC),
            action="produce",
            quantity=Decimal("7"),
            metadata_={},
        )
    )
    db_session.commit()

    [p] = estado_puestos(db_session, tenant.id)

    assert p["estado"] == "en_curso"
    assert p["orden"]["numero"] == "OP-MON"
    assert p["orden"]["piezas"] == 7.0
    assert p["orden"]["objetivo"] == 20.0
    assert p["orden"]["bobina"] == "COIL-123"
    assert p["ultima_actividad"]["accion"] == "produce"
    assert p["ultima_actividad"]["operario"] == user.name


def test_en_curso_tiene_prioridad_sobre_pendiente(db_session, tenant):
    _puesto(db_session, tenant, "PERF-1")
    pendiente = make_order(db_session, tenant, numero="OP-PEND")
    make_order_line(db_session, pendiente, workstation="PERF-1")
    en_curso = make_order(db_session, tenant, numero="OP-CURSO")
    linea = make_order_line(db_session, en_curso, workstation="PERF-1")
    linea.estado = "in_progress"
    db_session.commit()

    [p] = estado_puestos(db_session, tenant.id)

    assert p["orden"]["numero"] == "OP-CURSO"


def test_incidencia_abierta_manda_sobre_el_estado(db_session, tenant, user):
    _puesto(db_session, tenant, "PERF-1")
    _puesto(db_session, tenant, "PERF-2")
    order = make_order(db_session, tenant, numero="OP-INC")
    line = make_order_line(db_session, order, workstation="PERF-1")
    line.estado = "in_progress"
    for estado, puesto in (("abierta", "PERF-1"), ("resuelta", "PERF-2")):
        db_session.add(
            Incidencia(
                tenant_id=tenant.id,
                puesto=puesto,
                operario_id=user.id,
                descripcion=f"Atasco {puesto}",
                tipo="maquina",
                estado=estado,
            )
        )
    db_session.commit()

    puestos = _por_code(estado_puestos(db_session, tenant.id))

    assert puestos["PERF-1"]["estado"] == "incidencia"
    assert puestos["PERF-1"]["orden"]["numero"] == "OP-INC"
    assert puestos["PERF-1"]["incidencias_abiertas"][0]["descripcion"] == "Atasco PERF-1"
    assert puestos["PERF-2"]["estado"] == "libre"  # la resuelta no cuenta


def test_ordenes_cerradas_no_ocupan_el_puesto(db_session, tenant):
    _puesto(db_session, tenant, "PERF-1")
    order = make_order(db_session, tenant, numero="OP-FIN")
    make_order_line(db_session, order, workstation="PERF-1")
    order.estado = "completed"
    db_session.commit()

    [p] = estado_puestos(db_session, tenant.id)

    assert p["estado"] == "libre"


def test_endpoint_puestos_solo_supervisor(db_session, tenant, user):
    from tests.test_auth_roles import _client

    operario = _client(db_session, auth_headers(db_session, tenant, role="operator"))
    assert operario.get("/api/v1/supervisor/puestos").status_code == 403

    supervisor = _client(
        db_session, auth_headers(db_session, tenant, role="supervisor", email="sup@test.local")
    )
    r = supervisor.get("/api/v1/supervisor/puestos")
    assert r.status_code == 200, r.text
    assert r.json() == []
