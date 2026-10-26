"""Tests del coste de producción por orden (services/costes.py).

Contrato:
- Mano de obra = horas declaradas × €/h del puesto (0 si no hay coste).
- Estimado de material = objetivo kg × €/kg estándar; sin base → None.
- La desviación compara solo lo comparable (líneas con estimado).
- KPIs y tabla por orden salen de la misma fuente: siempre cuadran.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models import Workstation
from app.services.costes import costes_por_orden
from app.services.oee_kpis import calcular_kpis
from tests.helpers import (
    auth_headers,
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
)


def _puesto(db, tenant, code="LINEA-1", coste_hora="30.00"):
    ws = Workstation(
        tenant_id=tenant.id, code=code, name=f"Puesto {code}", hourly_cost=Decimal(coste_hora)
    )
    db.add(ws)
    db.commit()
    return ws


def _orden_con_bobina(db, tenant, user, *, material_en_linea=True):
    from app.services.inventory import link_coil

    material = make_material(db, tenant, code="ACERO-COSTE", cost=2.0)
    bobina = make_stock_item(
        db,
        tenant,
        material,
        cantidad=800.0,
        lote="L-COSTE",
        fecha_entrada=datetime.now(UTC) - timedelta(days=1),
        coste=2.0,
        ancho=122.0,
        espesor=0.5,
    )
    order = make_order(db, tenant, numero="OP-COSTE")
    line = make_order_line(
        db,
        order,
        workstation="LINEA-1",
        total_quantity=10.0,
        material=material if material_en_linea else None,
    )
    line.meters_per_piece = Decimal("2.0")
    db.commit()
    link_coil(db, tenant.id, user.id, stock_item_id=bobina.id, order_id=order.id, line_id=line.id)
    return material, order, line


def test_mano_de_obra_usa_coste_hora_del_puesto(db_session, tenant, user):
    from app.services.production import record_production

    _puesto(db_session, tenant, coste_hora="30.00")
    _, order, line = _orden_con_bobina(db_session, tenant, user)
    coste_material = float(line.real_material_cost)

    resultado = record_production(
        db_session,
        tenant.id,
        user.id,
        order_id=order.id,
        line_id=line.id,
        incremental_quantity=2,
        hours_worked=1.5,
    )

    db_session.refresh(line)
    assert resultado["incremental_labor_cost"] == pytest.approx(45.0)  # 1,5 h × 30 €/h
    assert float(line.real_cost) == pytest.approx(coste_material + 45.0)


def test_puesto_sin_coste_no_inventa_mano_de_obra(db_session, tenant, user):
    from app.services.production import record_production

    _, order, line = _orden_con_bobina(db_session, tenant, user)  # sin Workstation

    resultado = record_production(
        db_session,
        tenant.id,
        user.id,
        order_id=order.id,
        line_id=line.id,
        incremental_quantity=1,
        hours_worked=2,
    )

    assert resultado["incremental_labor_cost"] == 0


def test_roll_up_a_la_cabecera_de_la_orden(db_session, tenant, user):
    from app.services.production import record_production

    _puesto(db_session, tenant, coste_hora="20.00")
    _, order, line = _orden_con_bobina(db_session, tenant, user)

    record_production(
        db_session,
        tenant.id,
        user.id,
        order_id=order.id,
        line_id=line.id,
        incremental_quantity=1,
        hours_worked=1,
    )

    db_session.refresh(order)
    db_session.refresh(line)
    assert float(order.real_total_cost) == pytest.approx(float(line.real_cost))
    assert float(order.real_material_cost) == pytest.approx(float(line.real_material_cost))


def test_estimado_y_desviacion_por_orden(db_session, tenant):
    material = make_material(db_session, tenant, code="ACERO-EST", cost=2.0)
    order = make_order(db_session, tenant, numero="OP-EST")
    order.estado = "completed"
    line = make_order_line(db_session, order, total_quantity=10.0, material=material)
    line.target_material_qty = Decimal("100")  # 100 kg × 2 €/kg = 200 € estimado
    line.real_material_qty = Decimal("110")
    line.real_material_cost = Decimal("220")
    line.real_cost = Decimal("250")  # 30 € de mano de obra
    line.scrap_material_qty = Decimal("5")
    db_session.commit()

    [fila] = costes_por_orden(db_session, tenant.id)

    assert fila["numero"] == "OP-EST"
    assert fila["estimado_material"] == 200.0
    assert fila["real_material"] == 220.0
    assert fila["mano_obra"] == 30.0
    assert fila["real_total"] == 250.0
    assert fila["desviacion_material"] == 20.0
    assert fila["scrap_coste"] == 10.0  # 5 kg × 2 €/kg real


def test_orden_en_curso_tiene_estimado_pero_no_desviacion(db_session, tenant):
    """En curso la bobina está cargada entera (bulk): comparar engañaría."""
    material = make_material(db_session, tenant, code="ACERO-CURSO", cost=2.0)
    order = make_order(db_session, tenant, numero="OP-CURSO")  # active
    line = make_order_line(db_session, order, material=material)
    line.target_material_qty = Decimal("100")
    line.real_material_cost = Decimal("1600")  # bobina de 800 kg vinculada
    db_session.commit()

    [fila] = costes_por_orden(db_session, tenant.id)
    kpis = calcular_kpis(db_session, tenant.id)

    assert fila["estimado_material"] == 200.0
    assert fila["desviacion_material"] is None
    assert kpis["cost_variance"] is None
    assert kpis["orders_with_estimate"] == 0


def test_sin_precio_no_hay_estimado(db_session, tenant):
    material = make_material(db_session, tenant, code="ACERO-SIN", cost=0)
    order = make_order(db_session, tenant, numero="OP-SIN")
    line = make_order_line(db_session, order, material=material)
    line.target_material_qty = Decimal("100")
    db_session.commit()

    [fila] = costes_por_orden(db_session, tenant.id)

    assert fila["estimado_material"] is None
    assert fila["desviacion_material"] is None


def test_kpis_cuadran_con_la_tabla_por_orden(db_session, tenant):
    material = make_material(db_session, tenant, code="ACERO-KPI", cost=1.0)
    for i, (target, real) in enumerate([(100, 120), (50, 40)]):
        order = make_order(db_session, tenant, numero=f"OP-K{i}")
        order.estado = "completed"
        line = make_order_line(db_session, order, material=material)
        line.target_material_qty = Decimal(target)
        line.real_material_qty = Decimal(real)
        line.real_material_cost = Decimal(real)
        line.real_cost = Decimal(real + 10)
    sin_estimado = make_order(db_session, tenant, numero="OP-K-SIN")
    linea = make_order_line(db_session, sin_estimado)
    linea.real_cost = Decimal("5")
    db_session.commit()

    filas = costes_por_orden(db_session, tenant.id)
    kpis = calcular_kpis(db_session, tenant.id)

    assert kpis["real_cost"] == pytest.approx(sum(f["real_total"] for f in filas))
    assert kpis["estimated_cost"] == 150.0
    assert kpis["real_material_comparable"] == 160.0
    assert kpis["cost_variance"] == 10.0  # solo las 2 órdenes con estimado
    assert kpis["orders_with_estimate"] == 2
    assert kpis["labor_cost"] == 25.0


def test_endpoint_costes_ordenes_solo_supervisor(db_session, tenant, user):
    from tests.test_auth_roles import _client

    operario = _client(db_session, auth_headers(db_session, tenant, role="operator"))
    assert operario.get("/api/v1/supervisor/costes-ordenes").status_code == 403

    supervisor = _client(
        db_session, auth_headers(db_session, tenant, role="supervisor", email="sup@test.local")
    )
    r = supervisor.get("/api/v1/supervisor/costes-ordenes")
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_coste_global_de_empresa_si_el_puesto_no_tiene(db_session, tenant):
    from app.services.costes import coste_hora_puesto

    _puesto(db_session, tenant, code="CON-COSTE", coste_hora="30.00")
    _puesto(db_session, tenant, code="SIN-COSTE", coste_hora="0")
    assert coste_hora_puesto(db_session, tenant.id, "SIN-COSTE") == 0

    tenant.finances = {"overhead_hourly_cost": 22.5}
    db_session.commit()

    assert coste_hora_puesto(db_session, tenant.id, "SIN-COSTE") == Decimal("22.5")
    assert coste_hora_puesto(db_session, tenant.id, "CON-COSTE") == Decimal("30.00")
    assert coste_hora_puesto(db_session, tenant.id, "NO-EXISTE") == Decimal("22.5")
