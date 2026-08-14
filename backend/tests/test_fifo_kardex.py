"""Tests de Kardex (MaterialTransaction) y stock padre (spec 01, 3.2/6.3).

- Cada consumo de lote registra una MaterialTransaction inmutable con
  snapshots (cantidad_anterior / cantidad_nueva).
- El material padre (stock_current) se decrementa tras el consumo.
"""

from datetime import UTC, datetime

from app.models import MaterialTransaction
from tests.helpers import (
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
)


def test_consumo_registra_kardex_con_snapshots(db_session, tenant, user):
    """Cada lote consumido deja su MaterialTransaction con snapshots."""
    material = make_material(db_session, tenant, cost=2.0)
    bobina = make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=50,
        lote="KARDEX",
        fecha_entrada=datetime.now(UTC),
        coste=2.0,
    )
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order)

    from app.services.inventory import consume_stock_fifo

    consume_stock_fifo(
        db_session,
        tenant.id,
        user.id,
        material_id=material.id,
        cantidad_requerida=20,
        order_id=order.id,
        order_line_id=line.id,
    )

    tx = (
        db_session.query(MaterialTransaction)
        .filter(MaterialTransaction.stock_item_id == bobina.id)
        .all()
    )
    assert len(tx) == 1
    assert tx[0].tipo == "salida_produccion"
    assert tx[0].cantidad == 20
    assert tx[0].cantidad_anterior == 50
    assert tx[0].cantidad_nueva == 30
    assert tx[0].orden_id == order.id


def test_consumo_decrementa_stock_del_material(db_session, tenant, user):
    """stock_current del material maestro baja tras consumir."""
    material = make_material(db_session, tenant, cost=2.0)
    material.stock_current = 80
    db_session.commit()
    make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=80,
        lote="STOCKPADRE",
        fecha_entrada=datetime.now(UTC),
        coste=2.0,
    )
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order)

    from app.services.inventory import consume_stock_fifo

    consume_stock_fifo(
        db_session,
        tenant.id,
        user.id,
        material_id=material.id,
        cantidad_requerida=30,
        order_id=order.id,
        order_line_id=line.id,
    )

    db_session.refresh(material)
    assert material.stock_current == 50  # 80 - 30
