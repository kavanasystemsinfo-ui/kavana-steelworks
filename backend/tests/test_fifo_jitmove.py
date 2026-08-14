"""Tests de JIT Move y filtro por puesto (spec 01, sección 3.2).

- JIT Move: si la bobina prioritaria está en otro puesto, el sistema la mueve
  al puesto actual antes de consumir.
- Filtro por puesto (modo simple): sin bobina vinculada, solo consume bobinas
  físicamente en el puesto (con normalización de espacios/mayúsculas).
"""

from datetime import UTC, datetime, timedelta

from tests.helpers import (
    link_coil,
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
)


def test_jit_move_traslada_bobina_prioritaria_al_puesto(db_session, tenant, user):
    """La bobina prioritaria en otro puesto se mueve al puesto actual."""
    material = make_material(db_session, tenant, cost=2.0)
    t0 = datetime.now(UTC)
    bobina = make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=50,
        lote="LEJOS",
        fecha_entrada=t0 - timedelta(days=1),
        coste=2.0,
        ubicacion="ALMACEN-3",
    )
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order, workstation="LINEA-1")
    link_coil(db_session, tenant, bobina, order, line)

    from app.services.inventory import consume_stock_fifo

    consume_stock_fifo(
        db_session,
        tenant.id,
        user.id,
        material_id=material.id,
        cantidad_requerida=10,
        order_id=order.id,
        order_line_id=line.id,
        workstation_id="LINEA-1",
        priority_stock_item_id=bobina.id,
    )

    db_session.refresh(bobina)
    assert bobina.ubicacion == "LINEA-1"  # JIT Move ejecutado


def test_modo_simple_filtra_por_puesto(db_session, tenant, user):
    """Sin bobina vinculada, solo consume bobinas físicamente en el puesto."""
    material = make_material(db_session, tenant, cost=2.0)
    t0 = datetime.now(UTC)
    en_puesto = make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=50,
        lote="PUESTO",
        fecha_entrada=t0 - timedelta(days=2),
        coste=2.0,
        ubicacion="LINEA-1",
    )
    en_almacen = make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=100,
        lote="ALMACEN",
        fecha_entrada=t0 - timedelta(days=1),
        coste=2.0,
        ubicacion="ALMACEN-1",
    )
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order, workstation="LINEA-1")

    from app.services.inventory import consume_stock_fifo

    consume_stock_fifo(
        db_session,
        tenant.id,
        user.id,
        material_id=material.id,
        cantidad_requerida=30,
        order_id=order.id,
        order_line_id=line.id,
        workstation_id="LINEA-1",
    )

    db_session.refresh(en_puesto)
    db_session.refresh(en_almacen)
    assert en_puesto.cantidad_disponible == 20  # consumió del puesto
    assert en_almacen.cantidad_disponible == 100  # el almacén intacto
