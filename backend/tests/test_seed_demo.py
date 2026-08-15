"""Tests TDD del seed de demo (idempotente)."""

from app.models import Material, Order, OrderLine, StockItem, Tenant, User
from app.services.seed_demo import seed_demo


def test_seed_demo_crea_datos(db_session):
    resultado = seed_demo(db_session)

    assert resultado["created"] is True
    tenant = db_session.query(Tenant).filter(Tenant.name == "Demo Aceros").one()
    assert tenant is not None

    material = db_session.query(Material).filter(Material.tenant_id == tenant.id).one()
    assert material.code == "ACERO-DC01"

    bobina = db_session.query(StockItem).filter(StockItem.tenant_id == tenant.id).one()
    assert float(bobina.cantidad_disponible) == 800.0
    assert bobina.estado == "activo"

    orden = db_session.query(Order).filter(Order.tenant_id == tenant.id).one()
    linea = db_session.query(OrderLine).filter(OrderLine.order_id == orden.id).one()
    assert linea.workstation_id == "LINEA-1"

    operario = db_session.query(User).filter(User.tenant_id == tenant.id).one()
    assert operario.role == "operator"


def test_seed_demo_idempotente(db_session):
    primero = seed_demo(db_session)
    segundo = seed_demo(db_session)

    assert primero["created"] is True
    assert segundo["created"] is False
    # Solo un tenant demo, sin duplicados
    tenants = db_session.query(Tenant).filter(Tenant.name == "Demo Aceros").all()
    assert len(tenants) == 1
    assert db_session.query(StockItem).count() == 1
