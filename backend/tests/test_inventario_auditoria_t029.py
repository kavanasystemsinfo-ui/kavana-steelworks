"""T-033 H3/H5/H7 (auditoría T-029): unlink con tenant, link atómico, retirar pico."""

import pytest

from tests.helpers import (
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
    make_tenant,
)


@pytest.fixture()
def otra(db_session):
    return make_tenant(db_session, name="Otra Empresa")


# ── H3: unlink_coil no comprueba el tenant de la orden ────────────────────


def test_h3_unlink_rechaza_orden_de_otra_empresa(db_session, tenant, user, otra):
    from app.services.inventory import link_coil, unlink_coil

    material = make_material(db_session, tenant, code="PROPIO", cost=2.0)
    bobina = make_stock_item(db_session, tenant, material, cantidad=100, lote="L-P")
    orden = make_order(db_session, tenant, numero="OP-PROPIA")
    linea = make_order_line(db_session, orden, workstation="LINEA-1")
    link_coil(
        db_session, tenant.id, user.id,
        stock_item_id=bobina.id, order_id=orden.id, line_id=linea.id,
    )

    orden_ajena = make_order(db_session, otra, numero="OP-AJENA")
    linea_ajena = make_order_line(db_session, orden_ajena, workstation="LINEA-1")

    with pytest.raises(ValueError, match="no existe"):
        unlink_coil(
            db_session, tenant.id, user.id,
            stock_item_id=bobina.id, order_id=orden_ajena.id, line_id=linea_ajena.id,
        )


# ── H7: retirar pico deja la línea con la bobina "montada" ────────────────


def test_h7_retirar_pico_desvincula_la_linea(db_session, tenant, user):
    """El botón Retirar (que el panel envía solo con stock_item_id) saca la
    bobina del puesto: la línea no puede seguir apuntándola como montada.

    Hoy retirar_pico solo desvincula si le llegan order_id y line_id; el
    frontend (OperarioPage.tsx:710) manda únicamente stock_item_id, así que la
    bobina acaba en 'Retales' y la línea sigue con active_coil_id: el pico
    queda bloqueado para otra orden y la línea mantiene el cobro completo.
    """
    from app.services.inventory import link_coil, retirar_pico

    material = make_material(db_session, tenant, code="M-RET", cost=2.0)
    bobina = make_stock_item(db_session, tenant, material, cantidad=100, lote="L-RET")
    orden = make_order(db_session, tenant, numero="OP-RET")
    linea = make_order_line(db_session, orden, workstation="LINEA-1")
    link_coil(
        db_session, tenant.id, user.id,
        stock_item_id=bobina.id, order_id=orden.id, line_id=linea.id,
    )

    # Mismo payload que manda el panel de operario.
    retirar_pico(db_session, tenant.id, user.id, stock_item_id=bobina.id)

    db_session.expire_all()
    db_session.refresh(linea)
    db_session.refresh(bobina)
    assert bobina.ubicacion == "Retales"
    assert linea.active_coil_id is None, (
        "la bobina está en Retales pero la línea sigue apuntándola como montada "
        f"(active_coil_id={linea.active_coil_id})"
    )


# ── H5: link_coil no es atómico (commit dentro de unlink_coil) ────────────


def test_h5_link_coil_no_deja_la_bobina_suelta_si_falla(db_session, tenant, user, monkeypatch):
    """Misma máquina, cambio de orden: o queda vinculada a la nueva, o a la vieja.

    Hoy link_coil llama a unlink_coil (que hace commit) y después sigue; si
    algo falla en medio, la bobina queda desvinculada de las dos órdenes y el
    reembolso ya está confirmado.
    """
    from app.services import inventory

    material = make_material(db_session, tenant, code="M-ATOM", cost=2.0)
    bobina = make_stock_item(db_session, tenant, material, cantidad=800, lote="L-ATOM")
    orden_a = make_order(db_session, tenant, numero="OP-A")
    linea_a = make_order_line(db_session, orden_a, workstation="LINEA-1")
    orden_b = make_order(db_session, tenant, numero="OP-B")
    linea_b = make_order_line(db_session, orden_b, workstation="LINEA-1")

    inventory.link_coil(
        db_session, tenant.id, user.id,
        stock_item_id=bobina.id, order_id=orden_a.id, line_id=linea_a.id,
    )

    llamadas = {"n": 0}
    original = inventory.validar_material_compatible

    def _falla_en_la_segunda(db, bob, linea):
        llamadas["n"] += 1
        if llamadas["n"] >= 2:
            raise RuntimeError("fallo tras el commit interno de unlink_coil")
        return original(db, bob, linea)

    monkeypatch.setattr(inventory, "validar_material_compatible", _falla_en_la_segunda)

    with pytest.raises(RuntimeError):
        inventory.link_coil(
            db_session, tenant.id, user.id,
            stock_item_id=bobina.id, order_id=orden_b.id, line_id=linea_b.id,
        )

    db_session.expire_all()
    db_session.refresh(linea_a)
    assert linea_a.active_coil_id == bobina.id, (
        "commit parcial: la bobina quedó desvinculada de la orden A y no llegó "
        "a vincularse a la B"
    )

def test_h5_link_coil_fallo_tras_unlink_rollback_completo(db_session, tenant, user, monkeypatch):
    """Fuerza una excepción después de unlink_coil dentro de link_coil y comprueba
    con una sesión nueva que la orden anterior sigue con active_coil_id = bobina,
    la nueva no la tiene, y no hay reembolso (devolucion) ni movimiento confirmado.
    """
    from app.services import inventory
    from app.models import MaterialTransaction

    material = make_material(db_session, tenant, code="M-ROLLBACK", cost=2.0)
    bobina = make_stock_item(db_session, tenant, material, cantidad=800, lote="L-ROLL")
    orden_a = make_order(db_session, tenant, numero="OP-ROLL-A")
    linea_a = make_order_line(db_session, orden_a, workstation="LINEA-1")
    orden_b = make_order(db_session, tenant, numero="OP-ROLL-B")
    linea_b = make_order_line(db_session, orden_b, workstation="LINEA-1")

    # Vincular a la orden A
    inventory.link_coil(
        db_session, tenant.id, user.id,
        stock_item_id=bobina.id, order_id=orden_a.id, line_id=linea_a.id,
    )

    # Forzar fallo en la validación de material al vincular a la orden B
    # (esto ocurre DESPUÉS de unlink_coil con commit=False dentro de link_coil)
    original_validar = inventory.validar_material_compatible
    def _falla_despues_unlink(db, bob, linea):
        # Solo falla en la segunda llamada (la de la orden B)
        if linea.id == linea_b.id:
            raise RuntimeError("fallo simulado tras unlink_coil")
        return original_validar(db, bob, linea)

    monkeypatch.setattr(inventory, "validar_material_compatible", _falla_despues_unlink)

    with pytest.raises(RuntimeError, match="fallo simulado tras unlink_coil"):
        inventory.link_coil(
            db_session, tenant.id, user.id,
            stock_item_id=bobina.id, order_id=orden_b.id, line_id=linea_b.id,
        )

    # IMPORTANTE: usar expire_all + refresh para ver el estado real en BD tras rollback
    db_session.expire_all()
    db_session.refresh(linea_a)
    db_session.refresh(linea_b)
    db_session.refresh(bobina)

    # Verificaciones:
    # 1. La orden anterior (A) SIGUE con la bobina montada
    assert linea_a.active_coil_id == bobina.id, (
        f"Rollback falló: orden A perdió la bobina (active_coil_id={linea_a.active_coil_id})"
    )

    # 2. La orden nueva (B) NO tiene la bobina
    assert linea_b.active_coil_id is None, (
        f"Rollback falló: orden B tiene la bobina (active_coil_id={linea_b.active_coil_id})"
    )

    # 3. No hay reembolso (devolucion) confirmado - el unlink_coil(commit=False) crea
    # una MaterialTransaction tipo "devolucion" que debería haberse deshecho en el rollback
    devoluciones = db_session.query(MaterialTransaction).filter(
        MaterialTransaction.stock_item_id == bobina.id,
        MaterialTransaction.tipo == "devolucion",
    ).all()
    assert len(devoluciones) == 0, (
        f"Hay {len(devoluciones)} transacciones de devolucion que no deberían existir tras rollback"
    )

    # 4. La bobina sigue en el puesto (no en Retales)
    assert bobina.ubicacion != "Retales", (
        f"La bobina se movió a Retales ({bobina.ubicacion}) cuando debería seguir en el puesto"
    )

