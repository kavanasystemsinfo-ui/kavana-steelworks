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


def find_coil(
    db,
    tenant_id,
    *,
    coil_id=None,
    lote=None,
):
    """Escaneo de bobina (anexo A): busca por coil_id o lote.

    Devuelve los datos completos para el modo automático (material,
    dimensiones, peso) o manual. None si no existe.
    """
    from sqlalchemy import select

    from app.models import StockItem

    stmt = select(StockItem)
    if tenant_id is not None:
        stmt = stmt.where(StockItem.tenant_id == tenant_id)
    if coil_id:
        stmt = stmt.where(StockItem.coil_id == coil_id)
    elif lote:
        stmt = stmt.where(StockItem.lote == lote)
    else:
        raise ValueError("Indica coil_id o lote")

    bobina = db.scalar(stmt)
    if bobina is None:
        return None

    return {
        "id": str(bobina.id),
        "lote": bobina.lote,
        "coil_id": bobina.coil_id,
        "peso_kg": float(bobina.cantidad_disponible),
        "ancho_mm": float(bobina.width_mm) if bobina.width_mm else None,
        "espesor_mm": float(bobina.thickness_mm) if bobina.thickness_mm else None,
        "material_code": bobina.material.code if bobina.material else None,
        "material_name": bobina.material.name if bobina.material else None,
        "estado": bobina.estado,
        "ubicacion": bobina.ubicacion,
        "modo": "auto",
    }


def create_retal(
    db: Session,
    tenant_id,
    user_id,
    *,
    stock_item_id,
    radio_mm: float,
    order_id,
    line_id,
) -> dict:
    """Fin de bobina (spec 01 3.9): mide los milímetros de radio y reconcilia.

    El operario MIDE LOS MILÍMETROS DE RADIO de la bobina con un metro (en
    planta no se puede pesar una bobina montada en la máquina). El sistema
    convierte radio → kg con la fórmula v2 (coil_math, Densidad Calibrada
    Kavana) y compara con lo que el FIFO cree que queda: la diferencia es
    merma invisible. El sobrante NO es merma: queda como pico en el puesto
    y pasa al siguiente turno como material FIFO (visión Jorge, anexo A).
    """
    from decimal import Decimal

    from app.models import MaterialConsumo, MaterialTransaction, Order, OrderLine
    from app.services.coil_math import peso_desde_radio_mm

    bobina = db.get(StockItem, stock_item_id)
    if bobina is None:
        raise ValueError("Bobina no encontrada")

    if tenant_id is None:
        tenant_id = bobina.tenant_id
    if user_id is None:
        from app.services.receiving import _system_user

        user_id = _system_user(db, tenant_id)

    order = db.get(Order, order_id)
    if order is None:
        raise ValueError(f"Orden {order_id} no existe")
    linea = db.get(OrderLine, line_id)
    if linea is None or linea.order_id != order.id:
        raise ValueError("Línea no encontrada para la orden")

    # Fórmula v2: radio medido → kg restantes (densidad calibrada del material)
    densidad = (
        bobina.material.density_calibrada
        if bobina.material and bobina.material.density_calibrada
        else None
    )
    real_remaining = Decimal(
        str(
            peso_desde_radio_mm(
                radio_mm=radio_mm,
                width_mm=bobina.width_mm,
                densidad_kg_dm3=densidad if densidad is not None else 7.7807,
            )
        )
    )
    system_remaining = bobina.cantidad_disponible
    hidden_merma = max(Decimal("0"), system_remaining - real_remaining)
    merma_cost = hidden_merma * bobina.coste_por_unidad
    coste_reembolso = real_remaining * bobina.coste_por_unidad

    # 1) Merma invisible (reconciliación ISO 9001)
    if hidden_merma > Decimal("0.01"):
        db.add(
            MaterialConsumo(
                tenant_id=tenant_id,
                order_id=order_id,
                order_line_id=line_id,
                workstation_id="reconciliacion",
                material_id=bobina.material_id,
                stock_item_id=bobina.id,
                lote=bobina.lote,
                consumed_quantity=hidden_merma,
                unit=bobina.unit or "kg",
                produced_quantity=Decimal("0"),
                kg_por_pieza=Decimal("0"),
                calculation_method="coil_end_scrap",
                cost_per_unit=bobina.coste_por_unidad,
                total_cost=merma_cost,
                tipo="merma_puntas",
                observaciones=(
                    f"Merma de Fin de Bobina: {bobina.lote}. "
                    f"Sistema: {system_remaining}kg → Real: {real_remaining}kg. "
                    f"Diferencia: {hidden_merma}kg ({merma_cost:.2f}€)"
                ),
                operator_id=user_id,
            )
        )

    # 2) Actualizar la bobina física: el sobrante QUEDA EN EL PUESTO como pico
    #    (material FIFO para el siguiente turno, visión Jorge). Solo el botón
    #    "Retirar" lo devuelve al inventario.
    bobina.cantidad_disponible = real_remaining
    if real_remaining > 0:
        bobina.estado = "pico"  # sobrante que sigue en la máquina
        bobina.es_pico = True
        # NO se mueve a 'Retales': sigue en su puesto (workstation)
    else:
        bobina.estado = "agotado"
        bobina.es_pico = False

    # 3) Kardex de ajuste de inventario
    db.add(
        MaterialTransaction(
            tenant_id=tenant_id,
            material_id=bobina.material_id,
            stock_item_id=bobina.id,
            tipo="ajuste_inventario",
            cantidad=real_remaining,
            cantidad_anterior=system_remaining,
            cantidad_nueva=real_remaining,
            motivo=(
                f"Fin de Bobina. Queda en puesto: {real_remaining}kg. "
                f"Merma detectada: {hidden_merma}kg ({merma_cost:.2f}€)."
            ),
            realizado_por=user_id,
        )
    )

    # 4) Reembolsar a la línea lo que deja de estar comprometido + merma a scrap
    linea.real_material_qty = (linea.real_material_qty or Decimal("0")) - real_remaining
    linea.real_cost = (linea.real_cost or Decimal("0")) - coste_reembolso
    order.real_total_cost = (order.real_total_cost or Decimal("0")) - coste_reembolso
    if hidden_merma > Decimal("0.01"):
        linea.scrap_material_qty = (linea.scrap_material_qty or Decimal("0")) + hidden_merma
    linea.active_coil_id = None
    linea.active_coil_code = None

    db.commit()
    db.refresh(bobina)
    db.refresh(linea)
    return {
        "success": True,
        "merma_kg": float(hidden_merma),
        "merma_cost": float(merma_cost),
        "radio_mm": radio_mm,
        "peso_restante_kg": float(real_remaining),
        "msg": (
            "Pico retirado a inventario"
            if real_remaining > 0
            else "Bobina agotada"
        ),
    }


def retirar_pico(
    db: Session,
    tenant_id,
    user_id,
    *,
    stock_item_id,
    order_id=None,
    line_id=None,
) -> dict:
    """Botón 'Retirar' (segunda opción del fin de bobina, visión Jorge).

    Devuelve el pico al inventario (ubicación 'Retales'). A diferencia del
    fin de bobina (que deja el pico en la máquina para el siguiente turno),
    Retirar saca el material del puesto y lo pone como sugerencia de uso en
    el almacén. Si la bobina aún está vinculada a una línea, la desvincula
    y reembolsa lo que deja de estar comprometido.
    """
    from decimal import Decimal

    from app.models import MaterialTransaction, OrderLine

    bobina = db.get(StockItem, stock_item_id)
    if bobina is None:
        raise ValueError("Bobina no encontrada")

    if tenant_id is None:
        tenant_id = bobina.tenant_id
    if user_id is None:
        from app.services.receiving import _system_user

        user_id = _system_user(db, tenant_id)

    if bobina.estado not in ("activo", "pico") or bobina.cantidad_disponible <= 0:
        raise ValueError("La bobina no tiene material retirable")

    peso = bobina.cantidad_disponible
    coste_reembolso = peso * bobina.coste_por_unidad

    # Si sigue vinculada a una línea activa, desvincular y reembolsar
    if order_id and line_id:
        linea = db.get(OrderLine, line_id)
        if linea is not None and linea.order_id == order_id:
            if linea.active_coil_id == bobina.id:
                linea.real_material_qty = (linea.real_material_qty or Decimal("0")) - peso
                linea.real_cost = (linea.real_cost or Decimal("0")) - coste_reembolso
                linea.active_coil_id = None
                linea.active_coil_code = None

    # Devuelve al inventario como retal/pico sugerible
    bobina.estado = "pico"
    bobina.es_pico = True
    bobina.ubicacion = "Retales"

    db.add(
        MaterialTransaction(
            tenant_id=tenant_id,
            material_id=bobina.material_id,
            stock_item_id=bobina.id,
            tipo="traslado",
            cantidad=Decimal("0"),
            cantidad_anterior=Decimal("0"),
            cantidad_nueva=Decimal("0"),
            motivo=f"Pico retirado de la máquina a inventario: {peso}kg ({coste_reembolso:.2f}€)",
            realizado_por=user_id,
        )
    )

    db.commit()
    db.refresh(bobina)
    return {
        "success": True,
        "peso_kg": float(peso),
        "ubicacion": "Retales",
        "msg": f"Pico retirado a inventario: {peso}kg ({coste_reembolso:.2f}€)",
    }


def link_coil(
    db,
    tenant_id,
    user_id,
    *,
    stock_item_id,
    order_id,
    line_id,
) -> dict:
    """Vincula la bobina a la orden con cobro BULK por adelantado (spec 01 3.6)."""
    from sqlalchemy import select

    from app.models import MaterialTransaction, Order, OrderLine, StockItem

    if user_id is None:
        from app.services.receiving import _system_user

        user_id = _system_user(db, tenant_id)

    bobina = db.get(StockItem, stock_item_id)
    if bobina is None or bobina.estado not in ("activo", "pico"):
        raise ValueError("Bobina no encontrada o inactiva")

    order = db.get(Order, order_id)
    if order is None:
        raise ValueError(f"Orden {order_id} no existe")

    linea = db.get(OrderLine, line_id)
    if linea is None or linea.order_id != order.id:
        raise ValueError("Línea no encontrada para la orden")

    # JIT: reubicar al puesto de la línea
    workstation = linea.workstation_id
    if workstation and bobina.ubicacion != workstation:
        bobina.ubicacion = workstation
        db.add(
            MaterialTransaction(
                tenant_id=tenant_id,
                material_id=bobina.material_id,
                stock_item_id=bobina.id,
                tipo="traslado",
                cantidad=Decimal("0"),
                cantidad_anterior=Decimal("0"),
                cantidad_nueva=Decimal("0"),
                motivo=f"Ubicada en {workstation} (Vinculada a orden {order.numero})",
                realizado_por=user_id,
            )
        )

    # Idempotencia: si ya está vinculada, no volver a cobrar
    ya_vinculada = db.scalar(
        select(MaterialTransaction).where(
            MaterialTransaction.tenant_id == tenant_id,
            MaterialTransaction.stock_item_id == bobina.id,
            MaterialTransaction.orden_id == order_id,
            MaterialTransaction.linea_orden_id == line_id,
            MaterialTransaction.tipo == "salida_produccion",
            MaterialTransaction.motivo.contains("Bobina vinculada"),
        )
    )
    if ya_vinculada is not None:
        return {
            "success": True,
            "coil_weight": float(bobina.cantidad_disponible),
            "msg": "Bobina ya estaba vinculada.",
        }

    # Cobro BULK: la orden paga toda la bobina por adelantado
    coil_weight = bobina.cantidad_disponible
    coil_cost = coil_weight * bobina.coste_por_unidad
    linea.real_material_qty = (linea.real_material_qty or Decimal("0")) + coil_weight
    linea.real_material_cost = (linea.real_material_cost or Decimal("0")) + coil_cost
    linea.real_cost = (linea.real_cost or Decimal("0")) + coil_cost
    order.real_total_cost = (order.real_total_cost or Decimal("0")) + coil_cost
    linea.active_coil_id = bobina.id
    linea.active_coil_code = bobina.coil_id or bobina.lote

    # Kardex de vinculación (salida virtual: el material está en la línea)
    db.add(
        MaterialTransaction(
            tenant_id=tenant_id,
            material_id=bobina.material_id,
            stock_item_id=bobina.id,
            orden_id=order_id,
            linea_orden_id=line_id,
            tipo="salida_produccion",
            cantidad=coil_weight,
            cantidad_anterior=coil_weight,
            cantidad_nueva=coil_weight,
            motivo=f"Bobina vinculada a la Línea. Carga total de Entrada: {coil_weight:.2f}kg",
            realizado_por=user_id,
        )
    )

    db.commit()
    db.refresh(linea)
    return {
        "success": True,
        "coil_weight": float(coil_weight),
        "order": str(order.id),
    }
