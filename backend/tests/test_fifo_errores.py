"""Tests de errores y auditoría del motor FIFO."""

from datetime import UTC, datetime

import pytest

from app.models import MaterialConsumo
from tests.helpers import (
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
)


def test_stock_insuficiente_lanza_error(db_session, tenant, user):
    """Si no hay stock suficiente, la operación falla sin consumir nada."""
    material = make_material(db_session, tenant, cost=2.0)
    bobina = make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=10,
        lote="POCA",
        fecha_entrada=datetime.now(UTC),
    )
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order)

    from app.services.inventory import consume_stock_fifo

    with pytest.raises(ValueError, match="insuficiente"):
        consume_stock_fifo(
            db_session,
            tenant.id,
            user.id,
            material_id=material.id,
            cantidad_requerida=50,
            order_id=order.id,
            order_line_id=line.id,
        )

    db_session.refresh(bobina)
    assert bobina.cantidad_disponible == 10  # sin cambios


def test_registra_consumos_auditoria(db_session, tenant, user):
    """Cada bobina consumida deja su MaterialConsumo con coste y método."""
    material = make_material(db_session, tenant, cost=3.0)
    make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=40,
        lote="AUDIT",
        fecha_entrada=datetime.now(UTC),
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
        cantidad_requerida=25,
        order_id=order.id,
        order_line_id=line.id,
    )

    consumos = db_session.query(MaterialConsumo).filter(MaterialConsumo.order_id == order.id).all()
    assert len(consumos) == 1
    assert consumos[0].consumed_quantity == 25
    assert consumos[0].total_cost == 75.0  # 25 × 3 €
    assert resultado["coste_real_total"] == 75.0
