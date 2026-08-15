"""Helpers para tests del motor FIFO de bobinas."""

from datetime import UTC, datetime

from app.models import CoilLink, Material, Order, OrderLine, StockItem


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


def make_order_line(db, order, workstation="LINEA-1", total_quantity=10.0, linea_numero=1):
    line = OrderLine(
        order_id=order.id,
        linea_numero=linea_numero,
        workstation_id=workstation,
        total_quantity=total_quantity,
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
