"""Tests TDD del desvinculado de bobina (Fase 1, ciclo de vida).

Contrato unlinkCoil:
- Reembolsa a la orden SOLO lo no consumido: el peso restante de la bobina
  (cantidad_disponible tras el consumo FIFO) y su coste (spec: cambiar de
  bobina a mitad de línea sin devolver lo ya producido).
- Limpia el active_coil de la línea (la bobina queda libre en su ubicación).
- NO toca el stock físico de la bobina.
- Falla con ValueError si la bobina no es la activa de la línea (el
  endpoint lo traduce a 400).
- Registra kardex de reversión (motivo patrón "Bobina desvinculada").
- Si existía la burbuja CoilLink, queda en estado "desvinculada".
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import MaterialTransaction
from app.routers import stock as stock_router
from tests.helpers import (
    authed_client_for,
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
)
from tests.helpers import (
    link_coil as crear_burbuja,
)


def _override_get_db(db_session):
    def _gen():
        yield db_session

    return _gen


def _cliente(db, user):
    app.dependency_overrides[stock_router.get_db] = _override_get_db(db)
    return authed_client_for(db, user)


def _escenario(db, tenant, material, peso=800.0, lote="L-UNLINK"):
    bobina = make_stock_item(
        db,
        tenant,
        material,
        cantidad=peso,
        lote=lote,
        fecha_entrada=datetime.now(UTC) - timedelta(days=1),
        coste=2.0,
    )
    order = make_order(db, tenant, numero="OP-UNLINK")
    line = make_order_line(db, order)
    return bobina, order, line


def _link(db, tenant, user, bobina, order, line):
    from app.services.inventory import link_coil

    return link_coil(
        db,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        order_id=order.id,
        line_id=line.id,
    )


def _unlink(db, tenant, user, bobina, order, line):
    from app.services.inventory import unlink_coil

    return unlink_coil(
        db,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        order_id=order.id,
        line_id=line.id,
    )


def test_unlink_coil_reembolsa_lo_no_consumido(db_session, tenant, user):
    """800kg cobrados, 300kg restantes → devuelve 300kg y su coste a la línea."""
    material = make_material(db_session, tenant, cost=2.0)
    bobina, order, line = _escenario(db_session, tenant, material)
    _link(db_session, tenant, user, bobina, order, line)

    # Consumo parcial simulado (FIFO): la bobina queda en 300kg
    bobina.cantidad_disponible = 300.0
    db_session.commit()
    db_session.refresh(bobina)

    resultado = _unlink(db_session, tenant, user, bobina, order, line)

    db_session.refresh(line)
    db_session.refresh(order)
    assert resultado["success"] is True
    assert resultado["refunded_qty"] == 300.0
    # 800 - 300 = 500kg siguen en la línea; coste 1600 - 600 = 1000
    assert float(line.real_material_qty) == 500.0
    assert float(line.real_material_cost) == 1000.0
    assert float(line.real_cost) == 1000.0
    assert float(order.real_total_cost) == 1000.0
    assert line.active_coil_id is None
    assert line.active_coil_code is None


def test_unlink_coil_no_toca_stock_fisico(db_session, tenant, user):
    """La bobina no se descuenta ni cambia de estado al desvincularse."""
    material = make_material(db_session, tenant, cost=2.0)
    bobina, order, line = _escenario(db_session, tenant, material)
    _link(db_session, tenant, user, bobina, order, line)

    bobina.cantidad_disponible = 300.0
    db_session.commit()
    db_session.refresh(bobina)

    _unlink(db_session, tenant, user, bobina, order, line)

    db_session.refresh(bobina)
    assert float(bobina.cantidad_disponible) == 300.0
    assert bobina.estado == "activo"


def test_unlink_coil_sin_bobina_activa_falla(db_session, tenant, user):
    """Desvincular una bobina que no es la activa de la línea es un error."""
    material = make_material(db_session, tenant, cost=2.0)
    bobina, order, line = _escenario(db_session, tenant, material)

    with pytest.raises(ValueError, match="no está vinculada"):
        _unlink(db_session, tenant, user, bobina, order, line)


def test_unlink_coil_dos_veces_falla(db_session, tenant, user):
    """Tras el primer unlink la bobina deja de ser la activa: segundo intento → error."""
    material = make_material(db_session, tenant, cost=2.0)
    bobina, order, line = _escenario(db_session, tenant, material)
    _link(db_session, tenant, user, bobina, order, line)
    bobina.cantidad_disponible = 300.0
    db_session.commit()
    db_session.refresh(bobina)

    _unlink(db_session, tenant, user, bobina, order, line)

    with pytest.raises(ValueError, match="no está vinculada"):
        _unlink(db_session, tenant, user, bobina, order, line)


def test_unlink_coil_registra_kardex_de_reversion(db_session, tenant, user):
    """El kardex deja constancia de la reversión con el peso reembolsado."""
    from sqlalchemy import select

    material = make_material(db_session, tenant, cost=2.0)
    bobina, order, line = _escenario(db_session, tenant, material)
    _link(db_session, tenant, user, bobina, order, line)
    bobina.cantidad_disponible = 300.0
    db_session.commit()
    db_session.refresh(bobina)

    _unlink(db_session, tenant, user, bobina, order, line)

    tx = db_session.scalar(
        select(MaterialTransaction).where(
            MaterialTransaction.tenant_id == tenant.id,
            MaterialTransaction.stock_item_id == bobina.id,
            MaterialTransaction.motivo.contains("Bobina desvinculada"),
        )
    )
    assert tx is not None
    assert float(tx.cantidad) == 300.0


def test_unlink_coil_marca_burbuja_desvinculada(db_session, tenant, user):
    """La burbuja CoilLink pasa a estado 'desvinculada' (estado reservado en el enum)."""

    material = make_material(db_session, tenant, cost=2.0)
    bobina, order, line = _escenario(db_session, tenant, material)
    _link(db_session, tenant, user, bobina, order, line)
    cl = crear_burbuja(db_session, tenant, bobina, order, line)
    bobina.cantidad_disponible = 300.0
    db_session.commit()
    db_session.refresh(bobina)

    _unlink(db_session, tenant, user, bobina, order, line)

    db_session.refresh(cl)
    assert cl.estado == "desvinculada"


def test_endpoint_unlink_sin_token_devuelve_401(db_session):
    app.dependency_overrides[stock_router.get_db] = _override_get_db(db_session)
    client = TestClient(app)
    r = client.post(
        "/api/v1/stock-items/unlink",
        json={
            "stock_item_id": str(uuid.uuid4()),
            "order_id": str(uuid.uuid4()),
            "line_id": str(uuid.uuid4()),
        },
    )
    assert r.status_code == 401


def test_endpoint_unlink_devuelve_200(db_session, tenant, user):
    cliente = _cliente(db_session, user)
    material = make_material(db_session, tenant, cost=2.0)
    bobina, order, line = _escenario(db_session, tenant, material)
    _link(db_session, tenant, user, bobina, order, line)
    bobina.cantidad_disponible = 300.0
    db_session.commit()
    db_session.refresh(bobina)

    r = cliente.post(
        "/api/v1/stock-items/unlink",
        json={
            "stock_item_id": str(bobina.id),
            "order_id": str(order.id),
            "line_id": str(line.id),
        },
    )
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert r.json()["refunded_qty"] == 300.0


def test_endpoint_unlink_no_vinculada_devuelve_400(db_session, tenant, user):
    cliente = _cliente(db_session, user)
    material = make_material(db_session, tenant, cost=2.0)
    bobina, order, line = _escenario(db_session, tenant, material)

    r = cliente.post(
        "/api/v1/stock-items/unlink",
        json={
            "stock_item_id": str(bobina.id),
            "order_id": str(order.id),
            "line_id": str(line.id),
        },
    )
    assert r.status_code == 400


def test_unlink_y_relink_de_la_misma_bobina_recobra(db_session, tenant, user):
    """Ciclo de cambio de bobina: re-vincular tras unlink SÍ vuelve a cobrar.

    La idempotencia de link solo aplica si la bobina sigue siendo la activa;
    tras un unlink la bobina se re-vincula y se cobra lo restante (800 -
    300 reembolsados + 300 reclamados = 800 en la línea).
    """
    material = make_material(db_session, tenant, cost=2.0)
    bobina, order, line = _escenario(db_session, tenant, material)
    _link(db_session, tenant, user, bobina, order, line)
    bobina.cantidad_disponible = 300.0
    db_session.commit()
    db_session.refresh(bobina)

    _unlink(db_session, tenant, user, bobina, order, line)
    _link(db_session, tenant, user, bobina, order, line)

    db_session.refresh(line)
    assert float(line.real_material_qty) == 800.0
    assert line.active_coil_id == bobina.id
