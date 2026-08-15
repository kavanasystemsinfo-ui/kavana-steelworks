"""Integración de trazabilidad con los flujos reales (spec 04 §3.1).

record_production y create_retal deben escribir ProductionLog automáticamente
sin romper el flujo de planta (best-effort).
"""

from app.models import ProductionLog
from app.services import inventory, production
from tests.helpers import make_material, make_order, make_order_line, make_stock_item


def _order_con_linea(db, tenant, numero="OP-TZ"):
    orden = make_order(db, tenant, numero=numero)
    linea = make_order_line(db, orden, total_quantity=100, linea_numero=1)
    return orden, linea


def test_record_production_escribe_log_produce(db_session, tenant, user, monkeypatch):
    material = make_material(db_session, tenant)
    bobina = make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=500,
        lote="TZ1",
        ancho=1000,
        espesor=1.5,
    )
    orden, linea = _order_con_linea(db_session, tenant, numero="OP-TZ1")
    linea.meters_per_piece = 1.0
    db_session.commit()

    inventory.link_coil(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        order_id=orden.id,
        line_id=linea.id,
    )

    res = production.record_production(
        db_session,
        tenant.id,
        user.id,
        order_id=orden.id,
        line_id=linea.id,
        incremental_quantity=5,
        hours_worked=1,
    )
    assert res["success"] is True

    logs = (
        db_session.query(ProductionLog)
        .filter_by(order_id=orden.id)
        .order_by(ProductionLog.timestamp)
        .all()
    )
    acciones = [e.action for e in logs]
    assert "produce" in acciones
    produce = next(e for e in logs if e.action == "produce")
    assert float(produce.quantity) == 5
    assert produce.metadata_["activeCoilCode"] == bobina.coil_id
    assert produce.operator_id == user.id
    assert produce.tenant_id == tenant.id


def test_record_production_mejor_esfuerzo_no_rompe_si_log_falla(
    db_session, tenant, user, monkeypatch
):
    """Si el log de trazabilidad falla, la producción NO se rompe."""
    material = make_material(db_session, tenant)
    bobina = make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=500,
        lote="TZ2",
        ancho=1000,
        espesor=1.5,
    )
    orden, linea = _order_con_linea(db_session, tenant, numero="OP-TZ2")
    linea.meters_per_piece = 1.0
    db_session.commit()
    inventory.link_coil(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        order_id=orden.id,
        line_id=linea.id,
    )

    # Simulamos que el log falla siempre (devuelve None sin lanzar): el
    # import local de record_production resuelve este símbolo en runtime
    monkeypatch.setattr(
        "app.services.traceability.log_event",
        lambda *a, **k: None,
    )

    res = production.record_production(
        db_session,
        tenant.id,
        user.id,
        order_id=orden.id,
        line_id=linea.id,
        incremental_quantity=3,
        hours_worked=0.5,
    )
    assert res["success"] is True
    assert float(res["produced_quantity"]) == 3


def test_fin_bobina_escribe_log_scrap(db_session, tenant, user):
    material = make_material(db_session, tenant, code="ACERO-TZ")
    bobina = make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=500,
        lote="TZ3",
        ancho=1000,
        espesor=1.5,
    )
    orden, linea = _order_con_linea(db_session, tenant, numero="OP-TZ2")
    linea.meters_per_piece = 1.0
    db_session.commit()
    inventory.link_coil(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        order_id=orden.id,
        line_id=linea.id,
    )

    res = inventory.create_retal(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        radio_mm=250,
        order_id=orden.id,
        line_id=linea.id,
    )
    assert res["success"] is True

    logs = db_session.query(ProductionLog).filter_by(order_id=orden.id).all()
    scrap = next(e for e in logs if e.action == "scrap")
    assert scrap.metadata_["reason"] == "fin_bobina"
    assert scrap.metadata_["radio_mm"] == 250
    assert float(scrap.quantity) == float(res["merma_kg"])
