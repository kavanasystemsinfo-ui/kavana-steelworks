"""Tests TDD del fin de bobina (spec 01 3.9) + botón Retirar (visión Jorge).

Contrato (la visión de Jorge, corregida 2026-08-14):
- El operario MIDE LOS MILÍMETROS DE RADIO de la bobina con un metro; el
  sistema convierte radio → kg con la fórmula v2 (Densidad Calibrada Kavana).
- La merma invisible = lo que el FIFO cree que queda − lo que la medición
  dice que queda (reconciliación ISO 9001).
- El sobrante NO es merma: queda como pico EN EL PUESTO y pasa al siguiente
  turno como material FIFO.
- El botón "Retirar" (segunda opción) devuelve el pico al inventario
  ('Retales') y aparece como sugerencia de uso.
- Si el operario mide 0: la bobina se agota.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import MaterialConsumo, MaterialTransaction
from app.services.coil_math import peso_desde_radio_mm
from tests.helpers import make_material, make_order, make_order_line, make_stock_item


def _setup(db, tenant, user, peso=800.0, consumido=300.0, ancho: float | None = 122.0):
    """Bobina vinculada a una orden con parte del stock ya consumido.

    Tras el setup el FIFO cree que quedan peso − consumido kg. La bobina
    tiene ancho fijo para poder convertir radio → kg con la fórmula v2.
    """
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
        ancho=ancho,
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
    """El sistema cree que quedan 500 kg; el radio medido da menos: merma.

    Bobina de 800 kg, consumidos 300 → quedan 500. El operario mide un radio
    que corresponde a ~422 kg → ~78 kg de merma invisible.
    """
    from app.services.inventory import create_retal

    material, bobina, order, line = _setup(db_session, tenant, user, peso=800.0)

    # radio 200 mm con ancho 122 → 422,27 kg (calculado con la fórmula v2)
    radio = 200.0
    peso_esperado = peso_desde_radio_mm(radio_mm=radio, width_mm=122.0)

    resultado = create_retal(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        radio_mm=radio,
        order_id=order.id,
        line_id=line.id,
    )

    db_session.refresh(bobina)
    assert resultado["peso_restante_kg"] == pytest.approx(peso_esperado, abs=0.01)
    assert resultado["merma_kg"] == pytest.approx(500.0 - peso_esperado, abs=0.01)
    # El sobrante queda EN EL PUESTO (no se mueve a Retales) como pico FIFO
    assert float(bobina.cantidad_disponible) == pytest.approx(peso_esperado, abs=0.01)
    assert bobina.estado == "pico"
    assert bobina.es_pico is True
    assert bobina.ubicacion == "LINEA-1"  # sigue en la máquina


def test_fin_bobina_mide_cero_agota_bobina(db_session, tenant, user):
    """Si el operario mide 0 mm, la bobina se agota y todo lo restante es merma."""
    from app.services.inventory import create_retal

    material, bobina, order, line = _setup(db_session, tenant, user, peso=800.0)

    resultado = create_retal(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        radio_mm=0,
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
    peso_esperado = peso_desde_radio_mm(radio_mm=200.0, width_mm=122.0)

    create_retal(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        radio_mm=200.0,
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
    assert float(merma[0].consumed_quantity) == pytest.approx(500.0 - peso_esperado, abs=0.01)
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
    assert float(ajustes[0].cantidad_anterior) == 500.0
    assert float(ajustes[0].cantidad_nueva) == pytest.approx(peso_esperado, abs=0.01)


def test_fin_bobina_sin_merma_no_crea_consumo(db_session, tenant, user):
    """Si la medición da MÁS kg que el sistema (sobrante físico): sin merma.

    El sobrante nunca es merma (visión Jorge): es material FIFO que queda.
    """
    from app.services.inventory import create_retal

    material, bobina, order, line = _setup(db_session, tenant, user, peso=800.0)

    # radio 250 mm con ancho 122 → 565,12 kg > 500 que cree el sistema
    resultado = create_retal(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        radio_mm=250.0,
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
    """La orden recupera el coste del material que deja de estar comprometido."""
    from app.services.inventory import create_retal

    material, bobina, order, line = _setup(db_session, tenant, user, peso=800.0)
    peso_esperado = peso_desde_radio_mm(radio_mm=200.0, width_mm=122.0)

    create_retal(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        radio_mm=200.0,
        order_id=order.id,
        line_id=line.id,
    )

    db_session.refresh(line)
    # Tras link: 800×2 = 1600. Reembolso: peso_esperado×2. Queda la merma y lo consumido.
    coste_reembolso = peso_esperado * 2.0
    assert float(line.real_cost) == pytest.approx(1600.0 - coste_reembolso, abs=0.01)
    assert float(line.scrap_material_qty) == pytest.approx(500.0 - peso_esperado, abs=0.01)
    assert line.active_coil_id is None  # sin bobina activa


def test_fin_bobina_requiere_ancho_para_medir_radio(db_session, tenant, user):
    """Sin ancho registrado no se puede convertir radio → kg: error claro."""
    from app.services.inventory import create_retal

    material, bobina, order, line = _setup(db_session, tenant, user, peso=800.0, ancho=None)

    with pytest.raises(ValueError, match="ancho"):
        create_retal(
            db_session,
            tenant.id,
            user.id,
            stock_item_id=bobina.id,
            radio_mm=200.0,
            order_id=order.id,
            line_id=line.id,
        )


# ── Botón "Retirar" ──────────────────────────────────────────────────────────

def test_retirar_pico_devuelve_a_inventario(db_session, tenant, user):
    """Retirar mueve el pico a 'Retales' y lo deja como sugerible."""
    from app.services.inventory import create_retal, retirar_pico

    material, bobina, order, line = _setup(db_session, tenant, user, peso=800.0)
    create_retal(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        radio_mm=200.0,
        order_id=order.id,
        line_id=line.id,
    )

    resultado = retirar_pico(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        order_id=order.id,
        line_id=line.id,
    )

    db_session.refresh(bobina)
    assert resultado["success"] is True
    assert bobina.estado == "pico"
    assert bobina.es_pico is True
    assert bobina.ubicacion == "Retales"
    assert float(bobina.cantidad_disponible) == pytest.approx(
        peso_desde_radio_mm(radio_mm=200.0, width_mm=122.0), abs=0.01
    )


def test_retirar_pico_sin_material_error(db_session, tenant, user):
    """Retirar una bobina agotada o sin material es un error claro."""
    from app.services.inventory import create_retal, retirar_pico

    material, bobina, order, line = _setup(db_session, tenant, user, peso=800.0)
    create_retal(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        radio_mm=0,
        order_id=order.id,
        line_id=line.id,
    )

    with pytest.raises(ValueError, match="no tiene material"):
        retirar_pico(
            db_session,
            tenant.id,
            user.id,
            stock_item_id=bobina.id,
            order_id=order.id,
            line_id=line.id,
        )


def test_picos_solo_almacen_no_puesto(db_session, tenant, user):
    """/picos sugiere solo picos retirados al almacén, no los de la máquina."""
    from app.routers.stock import sugerencias_picos
    from app.services.inventory import create_retal, retirar_pico

    material, bobina, order, line = _setup(db_session, tenant, user, peso=800.0)
    create_retal(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        radio_mm=200.0,
        order_id=order.id,
        line_id=line.id,
    )

    # Antes de retirar: el pico está en el puesto (LINEA-1) → NO se sugiere
    sugeridos = sugerencias_picos(db_session)
    assert len(sugeridos) == 0

    retirar_pico(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        order_id=order.id,
        line_id=line.id,
    )

    # Tras retirar: está en 'Retales' → se sugiere
    sugeridos = sugerencias_picos(db_session)
    assert len(sugeridos) == 1
    assert sugeridos[0].stock_item_id == bobina.id
    assert sugeridos[0].ubicacion == "Retales"
