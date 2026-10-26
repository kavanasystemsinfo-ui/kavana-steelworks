"""Tests del informe de turno (services/informe_turno.py)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.models import Incidencia, ProductionLog
from app.services.informe_turno import informe_csv, informe_turno, ventana_turno
from tests.helpers import auth_headers, make_order, make_order_line

FECHA = date(2026, 10, 26)
# Planta en UTC-5: turno A = 06:00-14:00 local = 11:00-19:00 UTC
EN_TURNO_A = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
EN_TURNO_B = datetime(2026, 10, 26, 20, 0, tzinfo=UTC)


def _log(db, tenant, user, order, line, action, cantidad, ts, **meta):
    db.add(
        ProductionLog(
            tenant_id=tenant.id,
            order_id=order.id,
            line_id=line.id,
            operator_id=user.id,
            timestamp=ts,
            action=action,
            quantity=Decimal(str(cantidad)),
            metadata_=meta,
        )
    )


def test_ventana_del_turno_c_cruza_medianoche():
    inicio, fin = ventana_turno(FECHA, "C")
    assert inicio.hour == 22
    assert (fin - inicio).total_seconds() == 8 * 3600
    assert fin.day == 27


def test_turno_invalido():
    with pytest.raises(ValueError):
        ventana_turno(FECHA, "D")


def test_informe_agrega_por_puesto_solo_dentro_del_turno(db_session, tenant, user):
    order = make_order(db_session, tenant, numero="OP-INF")
    l1 = make_order_line(db_session, order, workstation="PERF-1")
    l2 = make_order_line(db_session, order, workstation="PERF-2", linea_numero=2)
    _log(db_session, tenant, user, order, l1, "produce", 10, EN_TURNO_A,
         consumedAmount=50.5, consumedMaterial="kg")
    _log(db_session, tenant, user, order, l1, "produce", 5, EN_TURNO_A,
         consumedAmount=25, consumedMaterial="kg")
    _log(db_session, tenant, user, order, l1, "scrap", 3.2, EN_TURNO_A, merma_cost=4.0)
    _log(db_session, tenant, user, order, l2, "quality_check", 0, EN_TURNO_A, status="nok")
    _log(db_session, tenant, user, order, l1, "produce", 99, EN_TURNO_B,
         consumedAmount=1, consumedMaterial="kg")  # fuera del turno A
    inc = Incidencia(
        tenant_id=tenant.id, puesto="PERF-2", operario_id=user.id,
        descripcion="Atasco", tipo="maquina", estado="abierta",
        tiempo_parada_min=Decimal("15"),
    )
    db_session.add(inc)
    db_session.commit()
    inc.created_at = EN_TURNO_A
    db_session.commit()

    informe = informe_turno(db_session, tenant.id, FECHA, "A")

    puestos = {p["puesto"]: p for p in informe["puestos"]}
    assert puestos["PERF-1"]["piezas"] == 15.0
    assert puestos["PERF-1"]["consumo_kg"] == 75.5
    assert puestos["PERF-1"]["merma_kg"] == 3.2
    assert puestos["PERF-1"]["merma_coste"] == 4.0
    assert puestos["PERF-1"]["ordenes"] == 1
    assert puestos["PERF-2"]["autocontroles"] == 1
    assert puestos["PERF-2"]["autocontroles_nok"] == 1
    assert puestos["PERF-2"]["incidencias"] == 1
    assert puestos["PERF-2"]["parada_min"] == 15.0
    assert informe["totales"]["piezas"] == 15.0


def test_turno_sin_actividad_sale_vacio(db_session, tenant):
    informe = informe_turno(db_session, tenant.id, FECHA, "B")
    assert informe["puestos"] == []
    assert informe["totales"]["piezas"] == 0


def test_csv_con_punto_y_coma_y_coma_decimal(db_session, tenant, user):
    order = make_order(db_session, tenant, numero="OP-CSV")
    line = make_order_line(db_session, order, workstation="PERF-1")
    _log(db_session, tenant, user, order, line, "produce", 4, EN_TURNO_A,
         consumedAmount=12.25, consumedMaterial="kg")
    db_session.commit()

    texto = informe_csv(informe_turno(db_session, tenant.id, FECHA, "A"))

    lineas = texto.strip().splitlines()
    assert lineas[1].startswith("Puesto;Órdenes;Piezas")
    assert lineas[2].startswith("PERF-1;1;4,00;12,25")
    assert lineas[-1].startswith("TOTAL;")


def test_endpoint_informe_csv_y_permisos(db_session, tenant, user):
    from tests.test_auth_roles import _client

    url = "/api/v1/supervisor/informe-turno?fecha=2026-10-26&turno=a"
    operario = _client(db_session, auth_headers(db_session, tenant, role="operator"))
    assert operario.get(url).status_code == 403

    supervisor = _client(
        db_session, auth_headers(db_session, tenant, role="supervisor", email="sup@test.local")
    )
    r = supervisor.get(url)
    assert r.status_code == 200, r.text
    assert r.json()["turno"] == "A"

    r = supervisor.get(url + "&formato=csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "informe-turno-2026-10-26-A.csv" in r.headers["content-disposition"]

    assert supervisor.get(url.replace("turno=a", "turno=x")).status_code == 400
