"""Helpers para tests del motor FIFO de bobinas."""

import uuid
from datetime import UTC, datetime

from app.models import CoilLink, Material, Order, OrderLine, StockItem, Tenant, User


def make_tenant(db, name="Aceros Test", slug=None):
    """Crea un Tenant válido con los campos de spec 07 (slug NOT NULL)."""
    t = Tenant(
        name=name,
        slug=slug or f"slug-{uuid.uuid4().hex[:8]}",
        status="active",
        is_active=True,
        auth={},
        theme={},
        finances={},
        sequences_config={},
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t



def make_user(db, tenant, email="operario@test.local", role="operator", name="Usuario Test"):
    """Crea un usuario con password 'kavana' (hash bcrypt real) y devuelve el User."""
    from app.services.auth import hash_password

    u = User(
        tenant_id=tenant.id,
        email=email,
        name=name,
        password_hash=hash_password("kavana"),
        role=role,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def auth_headers(db, tenant, role="operator", email=None):
    """Devuelve headers Authorization con un JWT real de un usuario del rol.

    El usuario se crea con password 'kavana' (mismo patrón que la demo).
    """
    from app.services.auth import login

    email = email or f"{role}@test.local"
    user = db.scalar(
        __import__("sqlalchemy").select(User).where(User.email == email)
    )
    if user is None:
        user = make_user(db, tenant, email=email, role=role)
    token = login(db, tenant.id, email, "kavana")
    return {"Authorization": f"Bearer {token}"}


def auth_headers_for(db, user):
    """Headers de auth para un User existente (password kavana del fixture)."""
    from app.services.auth import login

    token = login(db, user.tenant_id, user.email, "kavana")
    return {"Authorization": f"Bearer {token}"}


def authed_client(db, tenant, role="operator"):
    """TestClient de la app con headers de auth del rol (overrides aparte)."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    client.headers.update(auth_headers(db, tenant, role=role))
    return client


def authed_client_for(db, user):
    """TestClient con headers de auth del User dado (el operario del token)."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    client.headers.update(auth_headers_for(db, user))
    return client



def make_material(db, tenant, code="ACERO-01", cost=1.0, density=7850):
    m = Material(
        tenant_id=tenant.id,
        code=code,
        name=f"Material {code}",
        cost_per_unit=cost,
        density=density,
        unit="kg",
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def make_stock_item(
    db,
    tenant,
    material,
    cantidad=100.0,
    lote="L1",
    fecha_entrada=None,
    coil_id=None,
    coste=None,
    ubicacion="LINEA-1",
    estado="activo",
    ancho=None,
    espesor=None,
):
    si = StockItem(
        tenant_id=tenant.id,
        material_id=material.id,
        lote=lote,
        coil_id=coil_id or f"COIL-{lote}",
        cantidad_inicial=cantidad,
        cantidad_disponible=cantidad,
        unit="kg",
        coste_por_unidad=coste if coste is not None else material.cost_per_unit,
        fecha_entrada=fecha_entrada or datetime.now(UTC),
        ubicacion=ubicacion,
        estado=estado,
        es_pico=(estado == "pico"),
        width_mm=ancho,
        thickness_mm=espesor,
    )
    db.add(si)
    db.commit()
    db.refresh(si)
    return si


def make_order(db, tenant, numero="OP-001"):
    o = Order(tenant_id=tenant.id, numero=numero, estado="active")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def make_order_line(
    db,
    order,
    workstation="LINEA-1",
    total_quantity=10.0,
    linea_numero=1,
    material=None,
):
    line = OrderLine(
        order_id=order.id,
        linea_numero=linea_numero,
        workstation_id=workstation,
        total_quantity=total_quantity,
        material_id=material.id if material else None,
    )
    db.add(line)
    db.commit()
    db.refresh(line)
    return line


def link_coil(db, tenant, stock_item, order, line, estado="vinculada"):
    """Crea la burbuja de vinculación bobina ↔ orden ↔ línea."""
    cl = CoilLink(
        tenant_id=tenant.id,
        stock_item_id=stock_item.id,
        order_id=order.id,
        order_line_id=line.id,
        estado=estado,
    )
    db.add(cl)
    db.commit()
    db.refresh(cl)
    return cl


def ws_token(db, tenant, email="ws@test.local", role="operator"):
    """JWT real de un usuario del tenant para conectar el WebSocket.

    El WS exige token obligatorio desde la auditoría 2026-08-24 (hallazgo 2).
    """
    from sqlalchemy import select

    from app.services.auth import login

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = make_user(db, tenant, email=email, role=role)
    return login(db, tenant.id, email, "kavana")
