"""Test TDD del contrato FIFO (spec 01, sección 6.7 punto 9).

El servicio consume_stock_fifo no existe todavía: este test define su
comportamiento obligatorio antes de implementarlo.
"""

from datetime import UTC, datetime, timedelta

from tests.helpers import (
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
)


def test_fifo_respeta_fecha_entrada_asc(db_session, tenant, user):
    """La cascada FIFO consume primero la bobina más antigua."""
    material = make_material(db_session, tenant, cost=2.0)
    t0 = datetime.now(UTC)
    bobina_vieja = make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=50,
        lote="VIEJA",
        fecha_entrada=t0 - timedelta(days=10),
        coste=1.5,
    )
    bobina_nueva = make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=50,
        lote="NUEVA",
        fecha_entrada=t0 - timedelta(days=1),
        coste=2.5,
    )
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order)

    from app.services.inventory import consume_stock_fifo

    resultado = consume_stock_fifo(
        db_session,
        tenant.id,
        user.id,
        material_id=material.id,
        cantidad_requerida=30,
        order_id=order.id,
        order_line_id=line.id,
    )

    db_session.refresh(bobina_vieja)
    db_session.refresh(bobina_nueva)
    assert bobina_vieja.cantidad_disponible == 20  # consumió 30 de la vieja
    assert bobina_nueva.cantidad_disponible == 50  # la nueva intacta
    assert resultado["coste_real_total"] == 45.0  # 30 kg × 1.5 €


def test_fifo_cascada_hereda_entre_bobinas(db_session, tenant, user):
    """Agota la primera bobina y continúa con la siguiente sin mutar el conjunto."""
    material = make_material(db_session, tenant, cost=2.0)
    t0 = datetime.now(UTC)
    bobina_a = make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=20,
        lote="A",
        fecha_entrada=t0 - timedelta(days=5),
        coste=1.0,
    )
    bobina_b = make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=30,
        lote="B",
        fecha_entrada=t0 - timedelta(days=2),
        coste=3.0,
    )
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order)

    from app.services.inventory import consume_stock_fifo

    resultado = consume_stock_fifo(
        db_session,
        tenant.id,
        user.id,
        material_id=material.id,
        cantidad_requerida=40,
        order_id=order.id,
        order_line_id=line.id,
    )

    db_session.refresh(bobina_a)
    db_session.refresh(bobina_b)
    assert bobina_a.cantidad_disponible == 0  # agotada
    assert bobina_b.cantidad_disponible == 10  # heredó 20 de A + 10 de B
    assert resultado["coste_real_total"] == 20.0 * 1.0 + 20.0 * 3.0  # 20×1€ (A) + 20×3€ (B)
