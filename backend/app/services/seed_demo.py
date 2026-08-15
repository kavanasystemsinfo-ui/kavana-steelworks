"""Seed de datos demo para la demo pública de Steelworks.

Idempotente: solo crea datos si el tenant demo no existe. Se ejecuta en el
entrypoint de producción para que la demo desplegada tenga datos reales
(material, bobina, orden, operario) sin pasos manuales.

Contenido honesto: datos ficticios de demostración, sin clientes reales.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Material, Order, OrderLine, StockItem, Tenant, User


def seed_demo(db: Session) -> dict:
    """Crea el tenant demo con material, bobina, orden y operario si no existe."""
    existente = db.scalar(select(Tenant).where(Tenant.name == "Demo Aceros"))
    if existente is not None:
        return {"created": False, "tenant": str(existente.id)}

    tenant = Tenant(name="Demo Aceros")
    db.add(tenant)
    db.flush()

    operario = User(
        tenant_id=tenant.id,
        email="operario@demo.local",
        name="Operario Demo",
        password_hash="!demo",  # sin login real: la demo usa el flujo sin JWT
        role="operator",
    )
    db.add(operario)

    material = Material(
        tenant_id=tenant.id,
        code="ACERO-DC01",
        name="Bobina acero decapado 1.2x1220",
        stock_current=Decimal("800.00"),
        stock_minimum=Decimal("200.00"),
        cost_per_unit=Decimal("2.00"),
        dimension_ancho_mm=Decimal("1220"),
        dimension_espesor_mm=Decimal("1.2"),
        unit="kg",
    )
    db.add(material)
    db.flush()

    bobina = StockItem(
        tenant_id=tenant.id,
        material_id=material.id,
        lote="L-DEMO-001",
        coil_id="COIL-DEMO-001",
        cantidad_inicial=Decimal("800.00"),
        cantidad_disponible=Decimal("800.00"),
        unit="kg",
        width_mm=Decimal("1220"),
        thickness_mm=Decimal("1.2"),
        coste_por_unidad=Decimal("2.00"),
        costing_method="standard",
        moneda="EUR",
        fecha_entrada=datetime.now(UTC) - timedelta(days=2),
        ubicacion="ALMACEN-1",
        estado="activo",
        es_pico=False,
    )
    db.add(bobina)
    db.flush()

    order = Order(
        tenant_id=tenant.id,
        numero="OP-DEMO-001",
        estado="active",
        cliente="Cliente demo",
        fecha_entrega=datetime.now(UTC) + timedelta(days=7),
        notas="Orden de demostración pública",
    )
    db.add(order)
    db.flush()

    linea = OrderLine(
        order_id=order.id,
        linea_numero=1,
        workstation_id="LINEA-1",
        estado="pending",
        total_quantity=Decimal("50"),
        produced_quantity=Decimal("0"),
        real_time=Decimal("0"),
        meters_per_piece=Decimal("2.0"),
    )
    db.add(linea)

    db.commit()
    return {"created": True, "tenant": str(tenant.id)}
