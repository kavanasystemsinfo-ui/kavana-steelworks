"""Coste de producción por orden (adopción del centro de costes del legacy).

Frontera MES/ERP (ISA-95): aquí solo se VALORA lo que pasa en planta con dos
tablas de precios que ya existen en el modelo:
- Material.cost_per_unit (€/kg estándar del material)
- Workstation.hourly_cost (€/h del puesto)

Nada de facturas, clientes ni contabilidad: eso es del ERP del cliente.

Todo se calcula desde las líneas de orden (la misma fuente que el panel de
operario), nunca desde contadores duplicados. Sin precio configurado el coste
es 0 y el estimado queda como None: nunca se inventa una cifra.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Material, Order, OrderLine, Workstation

ESTADOS_CON_COSTE = ("active", "completed")


def coste_hora_puesto(db: Session, tenant_id, workstation_code: str | None) -> Decimal:
    """€/h configurado del puesto; 0 si no existe o no tiene coste."""
    if not workstation_code:
        return Decimal("0")
    coste = db.scalar(
        select(Workstation.hourly_cost).where(
            Workstation.tenant_id == tenant_id,
            Workstation.code == workstation_code,
        )
    )
    return coste or Decimal("0")


def _coste_kg_linea(linea: OrderLine, material: Material | None) -> Decimal:
    """€/kg real de la línea (lo pagado por las bobinas); si no hay, el estándar."""
    real_qty = linea.real_material_qty or Decimal("0")
    real_cost = linea.real_material_cost or Decimal("0")
    if real_qty > 0 and real_cost > 0:
        return real_cost / real_qty
    if material is not None:
        return material.cost_per_unit or Decimal("0")
    return Decimal("0")


def costes_linea(linea: OrderLine, material: Material | None) -> dict:
    """Desglose de coste de una línea. estimado_material es None si no hay base."""
    real_material = linea.real_material_cost or Decimal("0")
    real_total = linea.real_cost or Decimal("0")
    mano_obra = max(real_total - real_material, Decimal("0"))
    scrap_kg = linea.scrap_material_qty or Decimal("0")
    scrap_coste = scrap_kg * _coste_kg_linea(linea, material)

    estimado = None
    if (
        material is not None
        and linea.target_material_qty
        and linea.target_material_qty > 0
        and (material.cost_per_unit or 0) > 0
    ):
        estimado = linea.target_material_qty * material.cost_per_unit

    return {
        "real_material": real_material,
        "mano_obra": mano_obra,
        "real_total": real_total,
        "estimado_material": estimado,
        "scrap_kg": scrap_kg,
        "scrap_coste": scrap_coste,
    }


def _r(valor: Decimal | None) -> float | None:
    return None if valor is None else float(round(valor, 2))


def costes_por_orden(db: Session, tenant_id: uuid.UUID) -> list[dict]:
    """Coste real vs estimado de cada orden activa o completada."""
    ordenes = db.scalars(
        select(Order)
        .where(Order.tenant_id == tenant_id, Order.estado.in_(ESTADOS_CON_COSTE))
        .order_by(Order.created_at.desc())
    ).all()
    materiales = {
        m.id: m for m in db.scalars(select(Material).where(Material.tenant_id == tenant_id))
    }

    resultado = []
    for orden in ordenes:
        lineas = db.scalars(select(OrderLine).where(OrderLine.order_id == orden.id)).all()
        real_material = mano_obra = real_total = scrap_kg = scrap_coste = Decimal("0")
        estimado: Decimal | None = None
        real_material_con_estimado = Decimal("0")
        piezas = objetivo = Decimal("0")
        for linea in lineas:
            c = costes_linea(linea, materiales.get(linea.material_id))
            real_material += c["real_material"]
            mano_obra += c["mano_obra"]
            real_total += c["real_total"]
            scrap_kg += c["scrap_kg"]
            scrap_coste += c["scrap_coste"]
            if c["estimado_material"] is not None:
                estimado = (estimado or Decimal("0")) + c["estimado_material"]
                real_material_con_estimado += c["real_material"]
            piezas += linea.produced_quantity or Decimal("0")
            objetivo += linea.total_quantity or Decimal("0")

        # Desviación solo en órdenes completadas y sobre las líneas con estimado.
        # En curso no es comparable: la bobina se carga entera al vincularla
        # (cobro bulk, spec 01 3.6) y se reembolsa al cerrarla.
        desviacion = (
            real_material_con_estimado - estimado
            if estimado is not None and orden.estado == "completed"
            else None
        )
        resultado.append(
            {
                "order_id": str(orden.id),
                "numero": orden.numero,
                "cliente": orden.cliente,
                "estado": orden.estado,
                "piezas": float(piezas),
                "objetivo": float(objetivo),
                "real_material": _r(real_material),
                "mano_obra": _r(mano_obra),
                "real_total": _r(real_total),
                "estimado_material": _r(estimado),
                "desviacion_material": _r(desviacion),
                "real_material_comparable": _r(real_material_con_estimado),
                "scrap_kg": _r(scrap_kg),
                "scrap_coste": _r(scrap_coste),
            }
        )
    return resultado


def actualizar_costes_orden(db: Session, order: Order) -> None:
    """Roll-up de las líneas a la cabecera de la orden (no hace commit)."""
    materiales = {
        m.id: m
        for m in db.scalars(select(Material).where(Material.tenant_id == order.tenant_id))
    }
    lineas = db.scalars(select(OrderLine).where(OrderLine.order_id == order.id)).all()
    real_material = real_total = estimado = Decimal("0")
    for linea in lineas:
        c = costes_linea(linea, materiales.get(linea.material_id))
        real_material += c["real_material"]
        real_total += c["real_total"]
        estimado += c["estimado_material"] or Decimal("0")
    order.real_material_cost = real_material
    order.real_total_cost = real_total
    order.estimado_total_cost = estimado
