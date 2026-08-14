"""Motor de consumo FIFO de bobinas (corazón del sistema).

Contrato extraído de la spec 01 (InventoryService.consumeStockFIFO):
- Cascada FIFO por fecha_entrada ASC dentro de la burbuja de vinculación.
- Hereda entre bobinas sin mutar el conjunto elegible.
- Permite saldo negativo solo en la bobina prioritaria (modo auditoría).
- coste_real_total = Σ cantidad_tomada × coste_por_unidad del lote.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Material, MaterialConsumo, StockItem


def _elegibles_fifo(
    db: Session,
    tenant_id,
    material_id,
    *,
    order_id=None,
    order_line_id=None,
    priority_stock_item_id=None,
    workstation_id=None,
) -> list[StockItem]:
    """Bobinas elegibles del material, ordenadas por fecha_entrada ASC (FIFO).

    Modo simple (sin burbuja): todas las activas/pico del material.
    Modo auditoría (con priority_stock_item_id): solo las de la burbuja de
    vinculación (coil_links de la orden/línea) + la prioritaria, que siempre
    se inyecta aunque el vínculo no esté registrado (spec 01, sección 3.2).
    """
    stmt = (
        select(StockItem)
        .where(
            StockItem.tenant_id == tenant_id,
            StockItem.material_id == material_id,
            StockItem.estado.in_(("activo", "pico")),
        )
        .order_by(StockItem.fecha_entrada.asc())
    )

    if priority_stock_item_id:
        from app.models import CoilLink

        burbuja_ids = set(
            db.scalars(
                select(CoilLink.stock_item_id).where(
                    CoilLink.tenant_id == tenant_id,
                    CoilLink.order_id == order_id,
                    CoilLink.order_line_id == order_line_id,
                    CoilLink.estado.in_(("vinculada", "consumida")),
                )
            )
        )
        burbuja_ids.add(priority_stock_item_id)
        stmt = stmt.where(StockItem.id.in_(burbuja_ids))
    elif workstation_id:
        # Modo simple con filtro de puesto: solo bobinas físicamente aquí
        # (normalización legacy: sin espacios, case-insensitive)
        from sqlalchemy import func as sa_func

        normalized = workstation_id.replace(" ", "").upper()
        stmt = stmt.where(
            sa_func.upper(sa_func.replace(StockItem.ubicacion, " ", "")) == normalized
        )

    return list(db.scalars(stmt))


def consume_stock_fifo(
    db: Session,
    tenant_id,
    user_id,
    *,
    material_id,
    cantidad_requerida: Decimal | float,
    order_id,
    order_line_id,
    workstation_id=None,
    priority_stock_item_id=None,
) -> dict[str, Any]:
    """Consume cantidad_requerida aplicando cascada FIFO.

    workstation_id + priority_stock_item_id activan el modo auditoría
    (burbuja de vinculación): solo las bobinas vinculadas a la orden y la
    prioritaria son elegibles. Devuelve dict con `consumos` (por bobina) y
    `coste_real_total`.
    """
    requerida = Decimal(str(cantidad_requerida))
    elegibles = _elegibles_fifo(
        db,
        tenant_id,
        material_id,
        order_id=order_id,
        order_line_id=order_line_id,
        priority_stock_item_id=priority_stock_item_id,
        workstation_id=workstation_id,
    )
    if not elegibles:
        raise ValueError("Sin stock disponible para el material")

    # JIT Move: si la bobina prioritaria está en otro puesto, se mueve al actual
    # (spec 01, sección 3.2 punto 1: "JIT Move para la bobina actual")
    if priority_stock_item_id and workstation_id:
        prioritaria = next((b for b in elegibles if b.id == priority_stock_item_id), None)
        if prioritaria and prioritaria.ubicacion != workstation_id:
            prioritaria.ubicacion = workstation_id

    material = db.get(Material, material_id)
    restante = requerida
    consumos: list[dict] = []
    coste_total = Decimal("0")

    for bobina in elegibles:
        if restante <= 0:
            break
        tomada = min(bobina.cantidad_disponible, restante)
        if tomada > 0:
            cantidad_anterior = bobina.cantidad_disponible
            bobina.cantidad_disponible -= tomada
            coste_total += tomada * bobina.coste_por_unidad
            consumos.append(
                {
                    "stock_item_id": bobina.id,
                    "lote": bobina.lote,
                    "cantidad": tomada,
                    "coste_por_unidad": bobina.coste_por_unidad,
                    "cantidad_anterior": cantidad_anterior,
                    "cantidad_nueva": bobina.cantidad_disponible,
                }
            )
            restante -= tomada
            if bobina.cantidad_disponible <= 0:
                bobina.estado = "agotado"
        elif restante > 0:
            # bobina agotada en la lista: salta a la siguiente (sin mutar)
            continue

    # Saldo negativo solo en la última bobina prioritaria si aún falta
    if restante > 0 and elegibles:
        ultima = elegibles[-1]
        if ultima.cantidad_disponible >= 0 and ultima.estado != "agotado":
            # permitir negativo (tolerancia de superávit, modo auditoría)
            tomada = restante
            cantidad_anterior = ultima.cantidad_disponible
            ultima.cantidad_disponible -= tomada
            coste_total += tomada * ultima.coste_por_unidad
            consumos.append(
                {
                    "stock_item_id": ultima.id,
                    "lote": ultima.lote,
                    "cantidad": tomada,
                    "coste_por_unidad": ultima.coste_por_unidad,
                    "cantidad_anterior": cantidad_anterior,
                    "cantidad_nueva": ultima.cantidad_disponible,
                }
            )
            restante = Decimal("0")

    if restante > 0:
        raise ValueError(f"Stock insuficiente: faltan {restante} unidades")

    # Registrar consumos en material_consumos (auditoría / roll-up)
    from app.models import MaterialTransaction

    for c in consumos:
        db.add(
            MaterialConsumo(
                tenant_id=tenant_id,
                order_id=order_id,
                order_line_id=order_line_id,
                material_id=material_id,
                stock_item_id=c["stock_item_id"],
                lote=c["lote"],
                consumed_quantity=c["cantidad"],
                unit=material.unit if material else "kg",
                cost_per_unit=c["coste_por_unidad"],
                total_cost=round(c["cantidad"] * c["coste_por_unidad"], 2),
                tipo="automatico",
                operator_id=user_id,
            )
        )
        # Kardex inmutable: snapshot antes/después del lote
        db.add(
            MaterialTransaction(
                tenant_id=tenant_id,
                material_id=material_id,
                stock_item_id=c["stock_item_id"],
                tipo="salida_produccion",
                cantidad=c["cantidad"],
                cantidad_anterior=c["cantidad_anterior"],
                cantidad_nueva=c["cantidad_nueva"],
                orden_id=order_id,
                linea_orden_id=order_line_id,
                motivo=f"Consumo FIFO (Parte de {cantidad_requerida})",
                realizado_por=user_id,
            )
        )

    # Actualizar stock agregado del material padre (spec 01, updateMaterialAggregates)
    if material is not None:
        material.stock_current = max(material.stock_current - requerida, Decimal("0"))

    db.commit()
    return {
        "consumos": consumos,
        "coste_real_total": coste_total,
    }
