"""Caso límite crítico de la spec 01: burbuja de vinculación (modo auditoría).

En modo auditoría (priority_stock_item_id + workstation_id), SOLO las bobinas
vinculadas explícitamente a la orden (coil_links) + la prioritaria son
elegibles. Las bobinas fantasma (restos de turnos anteriores en el puesto)
NO se consumen, aunque sean más antiguas.
"""

from datetime import UTC, datetime, timedelta

from tests.helpers import (
    link_coil,
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
)


def test_bobina_fantasma_no_se_consume_en_auditoria(db_session, tenant, user):
    """La bobina más antigua NO vinculada queda intacta en modo auditoría."""
    material = make_material(db_session, tenant, cost=2.0)
    t0 = datetime.now(UTC)
    fantasma = make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=100,
        lote="FANTASMA",
        fecha_entrada=t0 - timedelta(days=30),
        coste=1.0,
        ubicacion="LINEA-1",
    )
    vinculada = make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=50,
        lote="VINCULADA",
        fecha_entrada=t0 - timedelta(days=1),
        coste=2.0,
        ubicacion="LINEA-1",
    )
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order, workstation="LINEA-1")
    link_coil(db_session, tenant, vinculada, order, line)

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
        priority_stock_item_id=vinculada.id,
    )

    db_session.refresh(fantasma)
    db_session.refresh(vinculada)
    assert fantasma.cantidad_disponible == 100  # intacta
    assert vinculada.cantidad_disponible == 20  # consumió de la vinculada


def test_bobina_prioritaria_siempre_elegible(db_session, tenant, user):
    """La bobina activa es elegible aunque el vínculo no se haya registrado."""
    material = make_material(db_session, tenant, cost=2.0)
    t0 = datetime.now(UTC)
    fantasma = make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=100,
        lote="FANTASMA",
        fecha_entrada=t0 - timedelta(days=30),
        coste=1.0,
        ubicacion="LINEA-1",
    )
    prioritaria = make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=50,
        lote="PRIORITARIA",
        fecha_entrada=t0 - timedelta(days=1),
        coste=2.0,
        ubicacion="LINEA-1",
    )
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order, workstation="LINEA-1")
    # SIN link_coil: la prioritaria se inyecta aunque no haya vínculo registrado

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
        priority_stock_item_id=prioritaria.id,
    )

    db_session.refresh(fantasma)
    db_session.refresh(prioritaria)
    assert fantasma.cantidad_disponible == 100  # intacta
    assert prioritaria.cantidad_disponible == 20  # consumió de la prioritaria
