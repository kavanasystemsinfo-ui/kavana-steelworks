"""El relevo que vincula un pico paga solo lo que dejó el compañero (Jorge, 06-11)."""

from decimal import Decimal

from app.services import coil_math
from app.services.inventory import create_retal, link_coil
from tests.helpers import make_material, make_order, make_order_line, make_stock_item


def test_relevo_vincula_el_pico_y_se_le_cobra_solo_el_pico(db_session, tenant, user, monkeypatch):
    material = make_material(db_session, tenant, code="M-RELEVO", cost=2.0)
    bobina = make_stock_item(
        db_session, tenant, material, cantidad=1000.0, lote="L-REL", ancho=122, espesor=0.5
    )
    orden_a = make_order(db_session, tenant, numero="OP-TURNO-1")
    linea_a = make_order_line(db_session, orden_a, workstation="LINEA-1")
    link_coil(
        db_session, tenant.id, user.id,
        stock_item_id=bobina.id, order_id=orden_a.id, line_id=linea_a.id,
    )
    assert linea_a.real_material_qty == Decimal("1000")  # la orden paga la bobina entera

    # El turno 1 consume 400 kg y hace fin de bobina midiendo 500 kg.
    bobina.cantidad_disponible = Decimal("600")
    db_session.commit()
    monkeypatch.setattr(coil_math, "peso_desde_radio_mm", lambda **_: 500.0)
    create_retal(
        db_session, tenant.id, user.id,
        stock_item_id=bobina.id, radio_mm=170.0, order_id=orden_a.id, line_id=linea_a.id,
    )
    db_session.refresh(bobina)
    assert bobina.cantidad_disponible == Decimal("500")

    # Relevo: otra orden, misma bobina (el pico).
    orden_b = make_order(db_session, tenant, numero="OP-TURNO-2")
    linea_b = make_order_line(db_session, orden_b, workstation="LINEA-1")
    link_coil(
        db_session, tenant.id, user.id,
        stock_item_id=bobina.id, order_id=orden_b.id, line_id=linea_b.id,
    )
    db_session.refresh(linea_b)
    assert linea_b.real_material_qty == Decimal("500")  # solo el pico, no los 1000 kg
    assert linea_b.active_coil_id == bobina.id
