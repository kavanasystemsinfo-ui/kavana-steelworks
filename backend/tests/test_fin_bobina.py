"""Tests TDD del fin de bobina (spec 01, sección 3.9 createRetal).

Contrato (la visión de Jorge: medir los milímetros de radio restantes):
- El sistema cree que quedan X kg (FIFO); el operario mide Y kg reales.
- Si Y < X: la diferencia es merma invisible (hiddenMerma) y se registra.
- El sobrante REAL vuelve a inventario como retal (ubicación 'Retales').
- Si el operario mide 0: la bobina se agota.
- La línea queda sin bobina activa y se reembolsa lo devuelto.
"""

from datetime import UTC, datetime, timedelta

from app.models import MaterialConsumo, MaterialTransaction
from tests.helpers import make_material, make_order, make_order_line, make_stock_item


def _setup(db, tenant, user, peso=800.0, consumido=300.0):
    """Bobina vinculada a una orden con parte del stock ya consumido."""
    from app.services.inventory import consume_stock_fifo, link_coil

    material = make_material(db, tenant, cost=2.0)
    bobina = make_stock_item(
        db,
        tenant,
        material,
        cantidad=peso,
        lote="L-RETAL",
        fecha_entrada=datetime.now(UTC) - timedelta(days=1),
        coste=2.0,
        ancho=122.0,
        espesor=0.5,
    )
    order = make_order(db, tenant, numero="OP-RETAL")
    line = make_order_line(db, order, workstation="LINEA-1")

    link_coil(db, tenant.id, user.id, stock_item_id=bobina.id, order_id=order.id, line_id=line.id)
    consume_stock_fifo(
        db,
        tenant.id,
        user.id,
        material_id=material.id,
        cantidad_requerida=consumido,
        order_id=order.id,
        order_line_id=line.id,
    )
    db.refresh(bobina)
    return material, bobina, order, line


def test_fin_bobina_con_merma_invisible(db_session, tenant, user):
    """El sistema cree que quedan 500 kg; el operario mide 420: 80 kg de merma."""
    from app.services.inventory import create_retal

    material, bobina, order, line = _setup(db_session, tenant, user, peso=800.0)

    resultado = create_retal(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        remaining_weight=420.0,
        order_id=order.id,
        line_id=line.id,
    )

    db_session.refresh(bobina)
    assert resultado["merma_kg"] == 80.0  # 500 - 420 = 80 de merma invisible
    # El sobrante real vuelve al inventario como retal
    assert bobina.cantidad_disponible == 420.0
    assert bobina.estado in ("activo", "pico")
    assert bobina.ubicacion == "Retales"
    assert bobina.es_pico is True  # 420 > 0 → retal


def test_fin_bobina_mide_cero_agota_bobina(db_session, tenant, user):
    """Si el operario mide 0, la bobina se agota y todo lo restante es merma."""
    from app.services.inventory import create_retal

    material, bobina, order, line = _setup(db_session, tenant, user, peso=800.0)

    resultado = create_retal(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        remaining_weight=0,
        order_id=order.id,
        line_id=line.id,
    )

    db_session.refresh(bobina)
    assert resultado["merma_kg"] == 500.0  # todo lo que quedaba
    assert bobina.cantidad_disponible == 0
    assert bobina.estado == "agotado"
    assert bobina.es_pico is False


def test_fin_bobina_registra_merma_en_kardex_y_consumo(db_session, tenant, user):
    """La merma queda como MaterialConsumo merma_puntas y Kardex ajuste."""
    from app.services.inventory import create_retal

    material, bobina, order, line = _setup(db_session, tenant, user, peso=800.0)

    create_retal(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        remaining_weight=420.0,
        order_id=order.id,
        line_id=line.id,
    )

    merma = (
        db_session.query(MaterialConsumo)
        .filter(
            MaterialConsumo.stock_item_id == bobina.id,
            MaterialConsumo.tipo == "merma_puntas",
        )
        .all()
    )
    assert len(merma) == 1
    assert merma[0].consumed_quantity == 80.0
    assert merma[0].calculation_method == "coil_end_scrap"

    ajustes = (
        db_session.query(MaterialTransaction)
        .filter(
            MaterialTransaction.stock_item_id == bobina.id,
            MaterialTransaction.tipo == "ajuste_inventario",
        )
        .all()
    )
    assert len(ajustes) == 1
    assert ajustes[0].cantidad_anterior == 500.0
    assert ajustes[0].cantidad_nueva == 420.0


def test_fin_bobina_sin_merma_no_crea_consumo(db_session, tenant, user):
    """Si el operario mide exactamente lo que el sistema cree: sin merma."""
    from app.services.inventory import create_retal

    material, bobina, order, line = _setup(db_session, tenant, user, peso=800.0)

    resultado = create_retal(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        remaining_weight=500.0,
        order_id=order.id,
        line_id=line.id,
    )

    assert resultado["merma_kg"] == 0
    merma = (
        db_session.query(MaterialConsumo).filter(MaterialConsumo.stock_item_id == bobina.id).all()
    )
    # Solo el consumo FIFO previo (300 kg), no hay consumo de merma
    assert len(merma) == 1


def test_fin_bobina_reembolsa_a_la_orden(db_session, tenant, user):
    """La orden recupera el coste del peso devuelto a inventario."""
    from app.services.inventory import create_retal

    material, bobina, order, line = _setup(db_session, tenant, user, peso=800.0)

    create_retal(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        remaining_weight=420.0,
        order_id=order.id,
        line_id=line.id,
    )

    db_session.refresh(line)
    # Se reembolsa 420×2 = 840, queda 1600 - 840 = 760 (300 consumidos × 2 + 80 merma × 2 = 760)
    assert line.real_cost == 760.0
    assert line.scrap_material_qty == 80.0  # la merma va al scrap de la línea
    assert line.active_coil_id is None  # sin bobina activa
