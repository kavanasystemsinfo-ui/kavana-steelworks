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

    operario = (
        db_session.query(User)
        .filter(User.tenant_id == tenant.id, User.role == "operator")
        .one()
    )
    assert operario.role == "operator"


def test_seed_demo_crea_usuarios_por_rol_con_password_kavana(db_session):
    """Fase 6: login + roles. Todos los usuarios demo comparten password kavana."""
    from app.services.auth import verify_password

    seed_demo(db_session)

    esperados = {
        "operario@demo.local": "operator",
        "supervisor@demo.local": "supervisor",
        "materias@demo.local": "materials",
        "admin@demo.local": "admin",
    }
    for email, rol in esperados.items():
        user = db_session.query(User).filter(User.email == email).one()
        assert user.role == rol, f"{email}: rol {user.role} != {rol}"
        assert verify_password("kavana", user.password_hash), f"{email} no verifica kavana"


def test_seed_demo_actualiza_password_legacy_a_kavana(db_session):
    """Un usuario demo existente con password antiguo se repara a kavana."""
    from app.services.auth import hash_password, verify_password

    seed_demo(db_session)
    operario = db_session.query(User).filter(User.email == "operario@demo.local").one()
    operario.password_hash = hash_password("otra-clave")  # simula despliegue antiguo
    db_session.commit()

    seed_demo(db_session)  # idempotente: repara el password

    db_session.refresh(operario)
    assert verify_password("kavana", operario.password_hash)


def test_seed_demo_idempotente(db_session):
    primero = seed_demo(db_session)
    segundo = seed_demo(db_session)

    assert primero["created"] is True
    assert segundo["created"] is False
    # Solo un tenant demo, sin duplicados
    tenants = db_session.query(Tenant).filter(Tenant.name == "Demo Aceros").all()
    assert len(tenants) == 1
    assert db_session.query(StockItem).count() == 1
