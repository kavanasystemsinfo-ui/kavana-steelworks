"""Tests de la reparación del histórico de la demo (OP-EST-2600).

La siembra antigua dejó la orden completada con una bobina de 1.500 mm de ancho
para piezas de estantería: el objetivo salía 8.753 kg por línea frente a 450 kg
consumidos y el panel de costes enseñaba -94 % de desviación. La reparación debe
dejar la orden coherente, el kardex cuadrado y no tocar nada si ya lo está.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.models import MaterialConsumo, MaterialTransaction, OrderLine, StockItem
from app.services.seed_estanterias import _objetivo_material, reparar_historico_demo
from tests.helpers import make_material, make_order, make_stock_item


def _material_con_geometria(db, tenant, code, cost, ancho, espesor):
    m = make_material(db, tenant, code=code, cost=cost)
    m.dimension_ancho_mm = Decimal(ancho)
    m.dimension_espesor_mm = Decimal(espesor)
    db.commit()
    db.refresh(m)
    return m


def _escenario_incoherente(db, tenant, user):
    """Reproduce el estado que dejó la siembra antigua en producción."""
    bobina = _material_con_geometria(db, tenant, "ACERO-S355", "1.05", "1500", "3.0")
    fleje = _material_con_geometria(db, tenant, "FLEJE-D265-18", "1.22", "265", "1.8")

    viejo = make_stock_item(db, tenant, bobina, cantidad=5000, coil_id="COIL-S355-001")
    nuevo_1 = make_stock_item(db, tenant, fleje, cantidad=5000, coil_id="COIL-FD265-002")
    nuevo_2 = make_stock_item(db, tenant, fleje, cantidad=5000, coil_id="COIL-FD265-003")

    orden = make_order(db, tenant, numero="OP-EST-2600")
    orden.estado = "completed"

    lineas = []
    for numero, total, consumo, coste_real in (
        (1, "100", "450", "472.50"),
        (2, "60", "240", "276.00"),
    ):
        linea = OrderLine(
            order_id=orden.id,
            linea_numero=numero,
            workstation_id="LINEA-1",
            estado="completed",
            total_quantity=Decimal(total),
            produced_quantity=Decimal(total),
            real_time=Decimal("0"),
            meters_per_piece=Decimal("2.5"),
            material_id=bobina.id,
            target_material_qty=Decimal("8753.2875") if numero == 1 else Decimal("2917.7625"),
            target_material_unit="kg",
            real_material_qty=Decimal(consumo),
            real_material_cost=Decimal(coste_real),
            real_cost=Decimal(coste_real)
            + (Decimal("145.67") if numero == 1 else Decimal("86.17")),
        )
        db.add(linea)
        lineas.append(linea)
    db.flush()

    for linea, consumo, coste in zip(lineas, ("450", "240"), ("472.50", "276.00"), strict=True):
        db.add(
            MaterialConsumo(
                tenant_id=tenant.id,
                order_id=orden.id,
                order_line_id=linea.id,
                workstation_id="LINEA-1",
                material_id=bobina.id,
                stock_item_id=viejo.id,
                lote=viejo.lote,
                consumed_quantity=Decimal(consumo),
                unit="kg",
                produced_quantity=linea.total_quantity,
                meters_per_piece=Decimal("2.5"),
                kg_por_pieza=Decimal("4.5") if consumo == "450" else Decimal("4.0"),
                calculation_method="bom_static",
                cost_per_unit=bobina.cost_per_unit,
                total_cost=Decimal(coste),
                tipo="automatico",
                operator_id=user.id,
                date=datetime.now(UTC),
            )
        )
        db.add(
            MaterialTransaction(
                tenant_id=tenant.id,
                material_id=bobina.id,
                stock_item_id=viejo.id,
                tipo="salida_produccion",
                cantidad=Decimal(consumo),
                cantidad_anterior=Decimal("5000"),
                cantidad_nueva=Decimal("5000") - Decimal(consumo),
                orden_id=orden.id,
                linea_orden_id=linea.id,
                motivo="Consumo en produccion",
                realizado_por=user.id,
            )
        )
    db.commit()

    # el consumo ya se descontó del stock cuando se registró (como en producción)
    viejo.cantidad_disponible = Decimal("5000") - Decimal("690")
    db.commit()
    db.refresh(viejo)

    return {
        "orden": orden,
        "bobina": bobina,
        "fleje": fleje,
        "viejo": viejo,
        "nuevo_1": nuevo_1,
        "nuevo_2": nuevo_2,
        "lineas": lineas,
    }


def test_repara_la_orden_incoherente(db_session, tenant, user):
    datos = _escenario_incoherente(db_session, tenant, user)

    cambios = reparar_historico_demo(db_session, tenant.id)
    db_session.commit()

    assert cambios == {"lineas": 2, "consumos": 2, "transacciones": 2}

    lineas = {ln.linea_numero: ln for ln in datos["orden"].lines}
    objetivo_1 = _objetivo_material(datos["fleje"], Decimal("100"), "3.0")
    objetivo_2 = _objetivo_material(datos["fleje"], Decimal("60"), "2.7")

    for numero, objetivo, consumo in ((1, objetivo_1, "1120"), (2, objetivo_2, "605")):
        linea = lineas[numero]
        assert linea.material_id == datos["fleje"].id
        assert linea.target_material_qty == objetivo
        assert linea.real_material_qty == Decimal(consumo)
        assert linea.real_material_cost == (Decimal(consumo) * Decimal("1.22")).quantize(
            Decimal("0.01")
        )
        # la mano de obra ya registrada se conserva
        mano = Decimal("145.67") if numero == 1 else Decimal("86.17")
        assert linea.real_cost == linea.real_material_cost + mano

    # el objetivo sale de la geometría del fleje, no de la bobina ancha
    assert objetivo_1 < Decimal("1200")
    assert objetivo_2 < Decimal("700")

    # kardex: lo consumido vuelve a la bobina vieja y se descuenta del fleje
    db_session.refresh(datos["viejo"])
    db_session.refresh(datos["nuevo_1"])
    db_session.refresh(datos["nuevo_2"])
    assert datos["viejo"].cantidad_disponible == Decimal("5000")
    assert datos["nuevo_1"].cantidad_disponible == Decimal("3880")
    assert datos["nuevo_2"].cantidad_disponible == Decimal("4395")

    # el consumo grabado apunta ya al fleje y a su bobina
    consumo = db_session.scalar(
        select(MaterialConsumo).where(MaterialConsumo.order_line_id == lineas[1].id)
    )
    assert consumo.material_id == datos["fleje"].id
    assert consumo.stock_item_id == datos["nuevo_1"].id
    assert consumo.consumed_quantity == Decimal("1120")
    assert consumo.total_cost == Decimal("1366.40")

    # y la cabecera de la orden queda con los totales de sus líneas
    db_session.refresh(datos["orden"])
    assert datos["orden"].real_material_cost == Decimal("2104.50")


def test_no_toca_nada_si_ya_es_coherente(db_session, tenant, user):
    _escenario_incoherente(db_session, tenant, user)
    reparar_historico_demo(db_session, tenant.id)
    db_session.commit()

    stock_antes = {
        s.coil_id: s.cantidad_disponible for s in db_session.scalars(select(StockItem)).all()
    }

    cambios = reparar_historico_demo(db_session, tenant.id)
    db_session.commit()

    assert cambios == {"lineas": 0, "consumos": 0, "transacciones": 0}
    stock_despues = {
        s.coil_id: s.cantidad_disponible for s in db_session.scalars(select(StockItem)).all()
    }
    assert stock_antes == stock_despues


def test_el_panel_de_coste_deja_de_ensenar_una_desviacion_absurda(db_session, tenant, user):
    """El síntoma que vio Jorge: -94 % de desviación en la vista Costes."""
    from app.services.panel_costes import panel_costes

    datos = _escenario_incoherente(db_session, tenant, user)
    datos["orden"].updated_at = datetime.now(UTC)
    db_session.commit()

    antes = panel_costes(db_session, tenant.id, periodo="mes")
    assert antes["desviacion"]["pct"] is not None
    assert antes["desviacion"]["pct"] < -50  # bobina ancha: estimado disparado

    reparar_historico_demo(db_session, tenant.id)
    db_session.commit()

    despues = panel_costes(db_session, tenant.id, periodo="mes")
    assert despues["desviacion"]["ordenes_con_estimado"] == 1
    assert abs(despues["desviacion"]["pct"]) < 5
    assert despues["kg_total"] == 1725.0
    assert despues["coste_kg"]["valor"] > 0


def test_sin_la_orden_no_hace_nada(db_session, tenant):
    assert reparar_historico_demo(db_session, tenant.id) == {
        "lineas": 0,
        "consumos": 0,
        "transacciones": 0,
    }
