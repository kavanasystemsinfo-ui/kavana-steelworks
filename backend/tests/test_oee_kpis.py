"""Tests TDD del OEE y KPIs del panel Supervisor (spec 03, adaptado al v2).

El v2 no tiene ProductionLog/Incidencia/Tooling/UserShift (modelos legacy que
no se portaron). El cálculo usa los datos reales del v2:
- produced_quantity / total_quantity de las líneas → rendimiento (P)
- real_time acumulado vs turno estándar (480 min) → disponibilidad (A)
- scrap_material_qty vs real_material_qty → calidad (Q)
- Order.estimado_total_cost vs real_total_cost → KPIs financieros

OEE = A × P × Q, cada componente clamp a [0, 100].
"""

from decimal import Decimal

from app.models import Tenant
from app.services.oee_kpis import calcular_kpis, calcular_oee
from tests.helpers import make_order, make_order_line


def _tenant_con_orden(
    db,
    *,
    produced=10.0,
    total=20.0,
    real_time=240.0,
    scrap=5.0,
    real_mat=100.0,
    est=1000.0,
    real_cost=900.0,
):
    tenant = Tenant(name="Aceros OEE")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    order = make_order(db, tenant, numero="OP-OEE")
    line = make_order_line(db, order, workstation="LINEA-1", total_quantity=total)
    line.produced_quantity = Decimal(str(produced))
    line.real_time = Decimal(str(real_time))
    line.scrap_material_qty = Decimal(str(scrap))
    line.real_material_qty = Decimal(str(real_mat))
    line.estado = "in_progress"
    order.estimado_total_cost = Decimal(str(est))
    order.real_total_cost = Decimal(str(real_cost))
    db.commit()
    db.refresh(line)
    db.refresh(order)
    return tenant, order, line


def test_oee_calcula_componentes(db_session):
    """A=240/480=50%, P=10/20=50%, Q=95/100=95% → OEE=23,75%."""
    tenant, order, line = _tenant_con_orden(db_session)

    resultado = calcular_oee(db_session, tenant.id)

    assert resultado["availability"] == 50.0
    assert resultado["performance"] == 50.0
    assert resultado["quality"] == 95.0
    assert resultado["oee"] == 23.75
    assert resultado["raw"]["total_pieces"] == 10
    assert resultado["raw"]["scrap_kg"] == 5.0


def test_oee_sin_datos_cero_sin_inventar(db_session):
    """Sin producción ni tiempo: 0, nunca datos ficticios (AUDIT FIX 2.3)."""
    tenant = Tenant(name="Aceros Vacio")
    db_session.add(tenant)
    db_session.commit()

    resultado = calcular_oee(db_session, tenant.id)

    assert resultado["availability"] == 0
    assert resultado["performance"] == 0
    assert resultado["quality"] == 100.0  # sin scrap, calidad perfecta por defecto
    assert resultado["oee"] == 0


def test_oee_cuenta_produccion_de_orden_completada(db_session):
    """La producción ya realizada cuenta aunque la orden esté completed."""
    tenant, order, line = _tenant_con_orden(db_session, produced=15.0, total=20.0)
    order.estado = "completed"
    db_session.commit()

    resultado = calcular_oee(db_session, tenant.id)

    assert resultado["raw"]["total_pieces"] == 15.0
    assert resultado["performance"] == 75.0  # 15/20


def test_kpis_financieros(db_session):
    """Coste real vs estimado y eficiencia (invertido: >100 = mejor)."""
    tenant, order, line = _tenant_con_orden(
        db_session, est=1000.0, real_cost=900.0, real_mat=100.0, scrap=5.0
    )

    kpis = calcular_kpis(db_session, tenant.id)

    assert kpis["orders_total"] == 1
    assert kpis["orders_active"] == 1
    assert kpis["cost_variance"] == -100.0  # 900 - 1000
    assert kpis["cost_efficiency"] == 111.1  # 1000/900*100
    assert kpis["scrap_rate"] == 5.0  # 5/100*100
    assert kpis["material_efficiency"] == 0.0  # sin target, 0 (spec 3.3)


def test_kpis_sin_costes_no_divide_por_cero(db_session):
    """Sin costes: ratios a 0, sin excepciones."""
    tenant = Tenant(name="Aceros Sin Costes")
    db_session.add(tenant)
    db_session.commit()

    kpis = calcular_kpis(db_session, tenant.id)

    assert kpis["orders_total"] == 0
    assert kpis["cost_efficiency"] == 0
    assert kpis["scrap_rate"] == 0
