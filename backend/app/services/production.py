"""Registro de producción con auto-consumo de material (spec 02 3.4 + 01 3.12).

Portado de OrderService.recordProduction del legacy al v2:
- Solo rol operator.
- Auto-consumo por density_formula (ancho/espesor del lote, largo de
  meters_per_piece, densidad calibrada Kavana), fallback meters_legacy y
  bom_static.
- Modo auditoría (línea con bobina activa): FIFO por burbuja de vinculación
  + bobina prioritaria; el fallo de deducción BLOQUEA la producción.
- Modo simple (sin bobina): FIFO global; el fallo NO bloquea (produce sin
  descuento, nunca consumos fantasma).
- GUARDIA DE SEGURIDAD: kilos teóricos acumulados <= reales vinculados
  + max(15% del real, 150 kg).
- WIP waterfall entre líneas en cascada.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, OrderLine, StockItem, User

DENSIDAD_CALIBRADA_KAVANA_KG_DM3 = Decimal("7.7807")


def _resolver_usuario(db: Session, tenant_id, user_id):
    """Resuelve el usuario: el recibido, o el 'system' de la demo (patrón repo).

    La spec exige rol operator; el usuario system solo se permite como
    fallback de demo (mismos endpoints sin JWT). Con autenticación real el
    operario llega con su token y su rol operator.
    """
    if user_id is not None:
        user = db.get(User, user_id)
        if user is not None and user.role == "operator":
            return user.id
        if user is not None and user.email == "system@kavana.local":
            return user.id
        raise ValueError("Permiso denegado: solo los operarios pueden registrar producción")
    from app.services.receiving import _system_user

    return _system_user(db, tenant_id)


def _resolve_active_material(db: Session, linea: OrderLine) -> tuple[Any, StockItem | None]:
    """Material de la bobina activa (lote-first, spec 01 3.12)."""
    if linea.active_coil_id:
        bobina = db.get(StockItem, linea.active_coil_id)
        if bobina is not None:
            return bobina.material, bobina
    return None, None


def _calcular_kg_por_pieza(
    *,
    ancho_mm: Decimal | None,
    espesor_mm: Decimal | None,
    largo_m: Decimal | float | None,
    densidad_kgm3: Decimal,
) -> Decimal:
    """Fórmula de densidad: largo_m × (ancho/1000) × (espesor/1000) × densidad.

    Devuelve 0 si faltan dimensiones (se usan los fallbacks de la spec).
    """
    if not ancho_mm or not espesor_mm or not largo_m or largo_m <= 0:
        return Decimal("0")
    ancho_m = Decimal(str(ancho_mm)) / 1000
    espesor_m = Decimal(str(espesor_mm)) / 1000
    largo = Decimal(str(largo_m))
    return largo * ancho_m * espesor_m * densidad_kgm3


def record_production(
    db: Session,
    tenant_id,
    user_id,
    *,
    order_id,
    line_id,
    incremental_quantity: Decimal | float,
    hours_worked: Decimal | float = 0,
    observaciones: str = "",
) -> dict[str, Any]:
    """Registra producción incremental en una línea con auto-consumo FIFO."""
    qty = Decimal(str(incremental_quantity))
    hours = Decimal(str(hours_worked))

    # 1) Contexto y seguridad
    user_id = _resolver_usuario(db, tenant_id, user_id)

    order = db.get(Order, order_id)
    if order is None or order.tenant_id != tenant_id:
        raise ValueError(f"Orden {order_id} no encontrada")
    linea = db.get(OrderLine, line_id)
    if linea is None or linea.order_id != order.id:
        raise ValueError("Línea no encontrada para la orden")

    # 2) Validación de entrada
    if qty < 0:
        raise ValueError("La cantidad no puede ser negativa")
    if qty == 0 and hours <= 0:
        raise ValueError("Debe indicar cantidad u horas de trabajo")

    # 3) WIP waterfall (líneas en cascada)
    lineas_orden = db.scalars(
        select(OrderLine)
        .where(OrderLine.order_id == order.id)
        .order_by(OrderLine.linea_numero.asc())
    ).all()
    idx = next((i for i, linea_i in enumerate(lineas_orden) if linea_i.id == linea.id), 0)
    if idx > 0:
        previa = lineas_orden[idx - 1]
        disponible_wip = (previa.produced_quantity or Decimal("0")) - (
            linea.produced_quantity or Decimal("0")
        )
        if qty > disponible_wip:
            raise ValueError(
                "WIP insuficiente: el paso anterior solo ha entregado "
                f"{previa.produced_quantity or 0} piezas. Disponibles: {disponible_wip}"
            )

    # 4) Auto-consumo (solo si hay piezas)
    material, bobina_activa = _resolve_active_material(db, linea)
    modo_auditoria = bobina_activa is not None and qty > 0

    consumed_amount = Decimal("0")
    consumption_unit = "uds"
    calculation_method = "none"
    kg_por_pieza = Decimal("0")
    incremental_material_cost = Decimal("0")
    material_consumo_ids: list = []

    if qty > 0 and material is not None:
        # 4a. kg por pieza (spec 01 3.12): density_formula > meters_legacy > bom_static
        densidad_kgm3 = (
            (material.density_calibrada or DENSIDAD_CALIBRADA_KAVANA_KG_DM3) * 1000
            if material.density_calibrada
            else (material.density or Decimal("7850"))
        )
        ancho = bobina_activa.width_mm if bobina_activa else material.dimension_ancho_mm
        espesor = bobina_activa.thickness_mm if bobina_activa else material.dimension_espesor_mm
        largo_m = linea.meters_per_piece

        kg_por_pieza = _calcular_kg_por_pieza(
            ancho_mm=ancho, espesor_mm=espesor, largo_m=largo_m, densidad_kgm3=densidad_kgm3
        )

        if kg_por_pieza > 0:
            consumed_amount = (qty * kg_por_pieza).quantize(Decimal("0.0001"))
            consumption_unit = "kg"
            calculation_method = "density_formula"
        elif largo_m and largo_m > 0:
            # meters_legacy: consume metros por pieza
            consumed_amount = (qty * Decimal(str(largo_m))).quantize(Decimal("0.0001"))
            consumption_unit = "m"
            calculation_method = "meters_legacy"
        elif linea.target_material_qty and linea.target_material_qty > 0:
            # bom_static: rate = target / total
            rate = linea.target_material_qty / (linea.total_quantity or Decimal("1"))
            consumed_amount = (qty * rate).quantize(Decimal("0.0001"))
            consumption_unit = linea.target_material_unit or "uds"
            calculation_method = "bom_static"

        # 4b. Financiero (coste del MAESTRO para el cálculo; el coste real del
        # lote va en el MaterialConsumo por lote)
        incremental_material_cost = (
            (consumed_amount * material.cost_per_unit).quantize(Decimal("0.01"))
            if consumed_amount > 0
            else Decimal("0")
        )

        # 4b'. GUARDIA DE SEGURIDAD (modo auditoría): teórico vs real vinculado.
        # Se evalúa ANTES de descontar stock (consume_stock_fifo hace commit
        # interno; un bloqueo posterior dejaría un descuento huérfano).
        if modo_auditoria and qty > 0:
            kg_per_unit = kg_por_pieza
            if kg_per_unit == 0 and linea.target_material_qty:
                kg_per_unit = linea.target_material_qty / (linea.total_quantity or Decimal("1"))
            theoretical_total = (linea.produced_quantity or Decimal("0") + qty) * kg_per_unit
            real_limit = linea.real_material_qty or Decimal("0")
            tolerance = max(real_limit * Decimal("0.15"), Decimal("150"))
            if theoretical_total > real_limit + tolerance:
                raise ValueError(
                    "BLOQUEO DE SEGURIDAD: Los kilos teóricos acumulados "
                    f"({theoretical_total:.1f}kg) superarían a los kilos reales vinculados "
                    f"({real_limit:.1f}kg) con margen de {tolerance:.0f}kg. "
                    "¿Olvidó registrar material?"
                )

        # 4c. Deducción de stock FIFO
        if consumed_amount > 0:
            from app.services.inventory import consume_stock_fifo

            try:
                resultado = consume_stock_fifo(
                    db,
                    tenant_id,
                    user_id,
                    material_id=material.id,
                    cantidad_requerida=consumed_amount,
                    order_id=order.id,
                    order_line_id=linea.id,
                    workstation_id=linea.workstation_id if modo_auditoria else None,
                    priority_stock_item_id=bobina_activa.id if modo_auditoria else None,
                    produced_quantity=qty,
                    kg_por_pieza=kg_por_pieza,
                    calculation_method=calculation_method,
                    consumo_tipo="auto_audit" if modo_auditoria else "automatico",
                    meters_per_piece=linea.meters_per_piece,
                )
                material_consumo_ids = [c["stock_item_id"] for c in resultado["consumos"]]
            except ValueError as exc:
                if modo_auditoria:
                    raise ValueError(
                        f"Error en deducción de material (Modo Auditoría): {exc}"
                    ) from exc
                # Modo simple: produce sin descuento (nunca consumos fantasma)
                consumed_amount = Decimal("0")
                incremental_material_cost = Decimal("0")
                kg_por_pieza = Decimal("0")
                calculation_method = "none"
        else:
            # Sin consumo calculable (sin dimensiones ni BOM): no descuenta
            calculation_method = "none"

    # 6) Coste laboral (sin configuración de máquina/operario/overhead → 0)
    incremental_labor_cost = Decimal("0")

    # 7) Actualizar la línea
    nueva_producida = (linea.produced_quantity or Decimal("0")) + qty
    total_requerida = linea.total_quantity or Decimal("0")
    nuevo_estado = "completed" if nueva_producida >= total_requerida else "in_progress"

    linea.produced_quantity = nueva_producida
    linea.real_time = (linea.real_time or Decimal("0")) + hours * 60
    linea.estado = nuevo_estado

    if modo_auditoria:
        # El material ya se cargó en bulk al vincular (linkCoil); solo labor
        linea.real_cost = (linea.real_cost or Decimal("0")) + incremental_labor_cost
    else:
        linea.real_cost = (
            (linea.real_cost or Decimal("0")) + incremental_material_cost + incremental_labor_cost
        )
        linea.real_material_qty = (linea.real_material_qty or Decimal("0")) + consumed_amount

    # Reparar target_material_qty si faltaba (órdenes legacy sin BOM)
    if not linea.target_material_qty or linea.target_material_qty == 0:
        if kg_por_pieza > 0:
            linea.target_material_qty = (total_requerida * kg_por_pieza).quantize(Decimal("0.0001"))
            linea.target_material_unit = "kg"
        elif consumed_amount > 0 and qty > 0:
            linea.target_material_qty = ((consumed_amount / qty) * total_requerida).quantize(
                Decimal("0.0001")
            )
            linea.target_material_unit = consumption_unit

    # 8) Roll-up del coste total de la orden
    order.real_total_cost = sum(
        (linea_i.real_cost or Decimal("0")) for linea_i in lineas_orden if linea_i.id != linea.id
    ) + (linea.real_cost or Decimal("0"))
    order.estado = (
        "completed"
        if all(linea_i.estado == "completed" for linea_i in lineas_orden)
        else order.estado
    )

    db.commit()
    db.refresh(linea)

    # 9) Trazabilidad ISO 9001 (spec 04): evento produce inmutable, best-effort.
    #    Nunca rompe el flujo: si el log falla, ya se registró y se traga.
    from app.services.traceability import log_event

    log_event(
        db,
        tenant_id=order.tenant_id,
        order_id=order.id,
        line_id=linea.id,
        operator_id=user_id,
        action="produce",
        quantity=float(qty),
        metadata={
            "observaciones": observaciones or None,
            "consumedMaterial": consumption_unit,
            "consumedAmount": float(consumed_amount),
            "incrementalCost": float(incremental_material_cost + incremental_labor_cost),
            "efficiency": (float(qty / hours) if hours > 0 else None),
            "activeCoilId": str(bobina_activa.id) if bobina_activa else None,
            "activeCoilCode": bobina_activa.coil_id if bobina_activa else None,
            "workstationName": linea.workstation_id,
            "manufacturingModel": linea.modelo_id,
            "totalRealized": float(linea.produced_quantity),
            "calculationMethod": calculation_method,
        },
    )

    return {
        "success": True,
        "produced_quantity": float(linea.produced_quantity),
        "incremental_quantity": float(qty),
        "consumed_amount": float(consumed_amount),
        "consumption_unit": consumption_unit,
        "calculation_method": calculation_method,
        "kg_por_pieza": float(kg_por_pieza),
        "incremental_material_cost": float(incremental_material_cost),
        "incremental_labor_cost": float(incremental_labor_cost),
        "estado": linea.estado,
        "material_consumo_ids": material_consumo_ids,
    }
