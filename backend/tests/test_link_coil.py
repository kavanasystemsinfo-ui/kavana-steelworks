"""Tests TDD del flujo de vinculación del operario (spec 01, sección 3.6).

Contrato linkCoil:
- Cobra el peso TOTAL de la bobina a la orden por adelantado (BULK).
- El stock físico de la bobina NO se descuenta (sigue viva en la máquina).
- Idempotente: vincular dos veces no vuelve a cobrar.
- Reubica la bobina al puesto de la línea (JIT).
- Registra el Kardex de vinculación (motivo patrón "Bobina vinculada").
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import MaterialTransaction
from tests.helpers import make_material, make_order, make_order_line, make_stock_item


def _bobina(db, tenant, material, peso=800.0, lote="L-VINC", dias=1):
    return make_stock_item(
        db,
        tenant,
        material,
        cantidad=peso,
        lote=lote,
        fecha_entrada=datetime.now(UTC) - timedelta(days=dias),
        coste=2.0,
    )


def test_link_coil_cobra_toda_la_bobina_a_la_orden(db_session, tenant, user):
    """El cobro BULK suma el peso y el coste total a la línea de la orden."""
    from app.services.inventory import link_coil

    material = make_material(db_session, tenant, cost=2.0)
    bobina = _bobina(db_session, tenant, material, peso=800.0)
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order)

    resultado = link_coil(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        order_id=order.id,
        line_id=line.id,
    )

    db_session.refresh(line)
    assert resultado["success"] is True
    assert resultado["coil_weight"] == 800.0
    # BULK: la línea carga el peso total y su coste (800 × 2.0 = 1600)
    assert line.real_material_qty == 800.0
    assert line.real_material_cost == 1600.0
    assert line.active_coil_id == bobina.id


def test_link_coil_no_descuenta_stock_fisico(db_session, tenant, user):
    """El stock de la bobina sigue intacto tras vincular (está en la máquina)."""
    from app.services.inventory import link_coil

    material = make_material(db_session, tenant, cost=2.0)
    bobina = _bobina(db_session, tenant, material, peso=800.0)
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order)

    link_coil(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        order_id=order.id,
        line_id=line.id,
    )

    db_session.refresh(bobina)
    assert bobina.cantidad_disponible == 800.0  # NO se descuenta


def test_link_coil_es_idempotente(db_session, tenant, user):
    """Vincular dos veces no vuelve a cobrar (patrón motivo)."""
    from app.services.inventory import link_coil

    material = make_material(db_session, tenant, cost=2.0)
    bobina = _bobina(db_session, tenant, material, peso=800.0)
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order)

    link_coil(
        db_session, tenant.id, user.id, stock_item_id=bobina.id, order_id=order.id, line_id=line.id
    )
    link_coil(
        db_session, tenant.id, user.id, stock_item_id=bobina.id, order_id=order.id, line_id=line.id
    )

    db_session.refresh(line)
    assert line.real_material_cost == 1600.0  # una sola vez


def test_link_coil_reubica_bobina_al_puesto(db_session, tenant, user):
    """Si la bobina está en otro puesto, se mueve al de la línea."""
    from app.services.inventory import link_coil

    material = make_material(db_session, tenant, cost=2.0)
    bobina = _bobina(db_session, tenant, material)
    bobina.ubicacion = "ALMACEN-3"
    db_session.commit()

    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order, workstation="LINEA-1")

    link_coil(
        db_session, tenant.id, user.id, stock_item_id=bobina.id, order_id=order.id, line_id=line.id
    )

    db_session.refresh(bobina)
    assert bobina.ubicacion == "LINEA-1"

    # El traslado queda en Kardex
    traslados = (
        db_session.query(MaterialTransaction)
        .filter(
            MaterialTransaction.stock_item_id == bobina.id,
            MaterialTransaction.tipo == "traslado",
        )
        .all()
    )
    assert len(traslados) == 1


def test_link_coil_registra_kardex_de_vinculacion(db_session, tenant, user):
    """La vinculación deja una salida_produccion con motivo patrón."""
    from app.services.inventory import link_coil

    material = make_material(db_session, tenant, cost=2.0)
    bobina = _bobina(db_session, tenant, material)
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order)

    link_coil(
        db_session, tenant.id, user.id, stock_item_id=bobina.id, order_id=order.id, line_id=line.id
    )

    vinculos = (
        db_session.query(MaterialTransaction)
        .filter(
            MaterialTransaction.stock_item_id == bobina.id,
            MaterialTransaction.tipo == "salida_produccion",
            MaterialTransaction.motivo.contains("Bobina vinculada"),
        )
        .all()
    )
    assert len(vinculos) == 1


def test_link_coil_bobina_inactiva_falla(db_session, tenant, user):
    """No se puede vincular una bobina agotada o inexistente."""
    from app.services.inventory import link_coil

    material = make_material(db_session, tenant, cost=2.0)
    bobina = _bobina(db_session, tenant, material)
    bobina.estado = "agotado"
    bobina.es_pico = False
    db_session.commit()

    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order)

    with pytest.raises(ValueError, match="[Bb]obina"):
        link_coil(
            db_session,
            tenant.id,
            user.id,
            stock_item_id=bobina.id,
            order_id=order.id,
            line_id=line.id,
        )
