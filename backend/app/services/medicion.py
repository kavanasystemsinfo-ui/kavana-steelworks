"""Medición de cierre de turno: el balance de material de cada operario.

Modelo de planta (Jorge, 28-10): al vincular, la línea carga el peso entero
de la bobina (el de la etiqueta del proveedor, en el que se confía). Cada
registro de piezas descuenta sus kilos teóricos. Al acabar el turno el
operario MIDE EL RADIO de la bobina que deja montada: lo que el sistema creía
que quedaba menos lo que queda de verdad son kilos que salieron de la bobina
y no están en piezas buenas, es decir, su chatarra.

A diferencia del fin de bobina (create_retal), la bobina NO se desvincula:
sigue en la máquina, con lo medido como punto de partida del relevo.

La medición es obligatoria: un operario que ha producido con una bobina
desde su última medición no puede cerrar la jornada ni la sesión
(mediciones_pendientes). Cambiar de orden con el mismo material no obliga a
medir: la chatarra se reconcilia en la siguiente medición.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    MaterialConsumo,
    MaterialTransaction,
    Order,
    OrderLine,
    ProductionLog,
    StockItem,
    UserShift,
)

OBSERVACION_SIMULADOR = "simulador demo"


class MedicionPendiente(Exception):
    """El operario tiene bobinas sin medir y no puede cerrar el turno."""


def medir_bobina(
    db: Session,
    tenant_id,
    user_id,
    *,
    stock_item_id,
    radio_mm: float,
    order_id,
    line_id,
    momento: datetime | None = None,
) -> dict:
    """Mide el radio, apunta la chatarra del operario y deja la bobina montada."""
    from app.services.coil_math import peso_desde_radio_mm
    from app.services.traceability import log_event

    bobina = db.get(StockItem, stock_item_id)
    if bobina is None or bobina.tenant_id != tenant_id:
        raise ValueError("Bobina no encontrada")
    orden = db.get(Order, order_id)
    linea = db.get(OrderLine, line_id)
    if orden is None or linea is None or linea.order_id != orden.id:
        raise ValueError("Línea no encontrada para la orden")
    if linea.active_coil_id != bobina.id:
        raise ValueError("La bobina no está vinculada a esta línea")

    densidad = (
        bobina.material.density_calibrada
        if bobina.material and bobina.material.density_calibrada
        else 7.7807
    )
    peso = peso_desde_radio_mm(
        radio_mm=radio_mm, width_mm=bobina.width_mm, densidad_kg_dm3=densidad
    )
    real = Decimal(str(peso))
    sistema = bobina.cantidad_disponible
    chatarra = max(Decimal("0"), sistema - real)
    coste = chatarra * bobina.coste_por_unidad

    if chatarra > Decimal("0.01"):
        db.add(
            MaterialConsumo(
                tenant_id=tenant_id,
                order_id=orden.id,
                order_line_id=linea.id,
                workstation_id="reconciliacion",
                material_id=bobina.material_id,
                stock_item_id=bobina.id,
                lote=bobina.lote,
                consumed_quantity=chatarra,
                unit=bobina.unit or "kg",
                produced_quantity=Decimal("0"),
                kg_por_pieza=Decimal("0"),
                # Mismo método que el fin de bobina; el evento lleva reason=cierre_turno
                calculation_method="coil_end_scrap",
                cost_per_unit=bobina.coste_por_unidad,
                total_cost=coste,
                tipo="merma_puntas",
                observaciones=(
                    f"Cierre de turno: {bobina.lote}. Sistema: {sistema}kg → "
                    f"Real: {real}kg. Chatarra: {chatarra}kg ({coste:.2f}€)"
                ),
                operator_id=user_id,
            )
        )
        linea.scrap_material_qty = (linea.scrap_material_qty or Decimal("0")) + chatarra

    # La bobina sigue activa y vinculada: solo se corrige lo que queda
    bobina.cantidad_disponible = real
    db.add(
        MaterialTransaction(
            tenant_id=tenant_id,
            material_id=bobina.material_id,
            stock_item_id=bobina.id,
            tipo="ajuste_inventario",
            cantidad=real,
            cantidad_anterior=sistema,
            cantidad_nueva=real,
            motivo=(
                f"Cierre de turno. Queda montada: {real}kg. "
                f"Chatarra: {chatarra}kg ({coste:.2f}€)."
            ),
            realizado_por=user_id,
        )
    )
    db.commit()

    # Siempre se registra (también con 0 kg): marca que la bobina está medida
    log_event(
        db,
        tenant_id=tenant_id,
        order_id=orden.id,
        line_id=linea.id,
        operator_id=user_id,
        action="scrap",
        quantity=float(chatarra),
        timestamp=momento,
        metadata={
            "radio_mm": radio_mm,
            "peso_restante_kg": float(real),
            "system_remaining_kg": float(sistema),
            "merma_cost": float(coste),
            "reason": "cierre_turno",
            "activeCoilId": str(bobina.id),
            "activeCoilCode": bobina.coil_id,
        },
    )
    return {
        "success": True,
        "chatarra_kg": float(chatarra),
        "chatarra_coste": round(float(coste), 2),
        "peso_restante_kg": float(real),
        "msg": f"Bobina medida: quedan {real} kg montados",
    }


# Error normal al medir la carne con un metro sobre una bobina montada (Jorge, 29-10).
# Una merma por debajo de lo que pesan estos milímetros puede ser solo la medida.
MM_ERROR_METRO = 3


def prever_medida(db: Session, tenant_id, *, stock_item_id, radio_mm: float) -> dict:
    """Vista previa de una medición: los kg que quedan según los mm de carne
    y la merma que se apuntaría, sin guardar nada (legacy CoilCalculator).

    Usa la misma fórmula y densidad que medir_bobina y create_retal, para que
    el operario vea antes de confirmar lo que el sistema va a registrar.
    Devuelve también la ficha con la que se calcula (ancho, mandril,
    densidad) y cuántos kg pesa un milímetro de carne a ese tamaño: con eso la
    pantalla distingue una merma real de un error del metro.
    """
    from app.services.coil_math import DIAMETRO_INTERIOR_MM_DEFAULT, peso_desde_radio_mm

    bobina = db.get(StockItem, stock_item_id)
    if bobina is None or bobina.tenant_id != tenant_id:
        raise LookupError("Bobina no encontrada")
    densidad = (
        bobina.material.density_calibrada
        if bobina.material and bobina.material.density_calibrada
        else 7.7807
    )

    def peso(mm: float) -> Decimal:
        kg = peso_desde_radio_mm(radio_mm=mm, width_mm=bobina.width_mm, densidad_kg_dm3=densidad)
        return Decimal(str(kg))

    real = peso(radio_mm)
    kg_por_mm = peso(radio_mm + 1) - real
    sistema = bobina.cantidad_disponible
    merma = max(Decimal("0"), sistema - real)
    margen = kg_por_mm * MM_ERROR_METRO
    return {
        "radio_mm": radio_mm,
        "peso_restante_kg": float(real),
        "sistema_kg": float(sistema),
        "merma_kg": float(merma),
        "merma_pct": float(round(merma / sistema * 100, 1)) if sistema > 0 else 0.0,
        "kg_por_mm": float(kg_por_mm),
        "margen_error_kg": float(margen),
        "merma_dentro_del_margen": merma <= margen,
        "coil_code": bobina.coil_id,
        "material_code": bobina.material.code if bobina.material else None,
        "ancho_mm": float(bobina.width_mm),
        "mandril_mm": DIAMETRO_INTERIOR_MM_DEFAULT,
        "densidad_kg_dm3": float(densidad),
    }


def _ultima_medicion(db: Session, tenant_id, coil_id: str) -> datetime | None:
    """Último fin de bobina o cierre de turno de la bobina (evento scrap)."""
    momentos = [
        log.timestamp
        for log in db.scalars(
            select(ProductionLog).where(
                ProductionLog.tenant_id == tenant_id, ProductionLog.action == "scrap"
            )
        )
        if (log.metadata_ or {}).get("activeCoilId") == coil_id
    ]
    return max(momentos) if momentos else None


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def mediciones_pendientes(db: Session, tenant_id, user_id) -> list[dict]:
    """Bobinas montadas con las que el operario ha producido en su turno sin medirlas.

    Cuenta su producción desde que inició sesión (turno activo) y no la del
    simulador de la demo, para que las cuentas demo puedan salir.
    """
    turno = db.scalar(
        select(UserShift).where(UserShift.operator_id == user_id, UserShift.status == "active")
    )
    if turno is None:
        return []
    desde = _utc(turno.login_time)

    montadas = {
        str(ln.active_coil_id): ln
        for ln in db.scalars(
            select(OrderLine)
            .join(Order, Order.id == OrderLine.order_id)
            .where(Order.tenant_id == tenant_id, OrderLine.active_coil_id.is_not(None))
        )
    }
    if not montadas:
        return []

    usadas: dict[str, datetime] = {}
    for log in db.scalars(
        select(ProductionLog).where(
            ProductionLog.tenant_id == tenant_id,
            ProductionLog.operator_id == user_id,
            ProductionLog.action == "produce",
            ProductionLog.timestamp >= desde,
        )
    ):
        meta = log.metadata_ or {}
        coil = meta.get("activeCoilId")
        if coil in montadas and meta.get("observaciones") != OBSERVACION_SIMULADOR:
            usadas[coil] = max(usadas.get(coil, _utc(log.timestamp)), _utc(log.timestamp))

    pendientes = []
    for coil, ultima_pieza in usadas.items():
        medida = _ultima_medicion(db, tenant_id, coil)
        if medida is not None and _utc(medida) >= ultima_pieza:
            continue
        linea = montadas[coil]
        pendientes.append(
            {
                "stock_item_id": coil,
                "coil_code": linea.active_coil_code,
                "order_id": str(linea.order_id),
                "line_id": str(linea.id),
                "puesto": linea.workstation_id,
            }
        )
    return pendientes


def exigir_mediciones(db: Session, user_id: uuid.UUID) -> None:
    """Corta el cierre de turno o de sesión si quedan bobinas sin medir."""
    from app.models import User

    usuario = db.get(User, user_id)
    if usuario is None or usuario.role != "operator":
        return
    pendientes = mediciones_pendientes(db, usuario.tenant_id, usuario.id)
    if pendientes:
        codigos = ", ".join(p["coil_code"] or "?" for p in pendientes)
        raise MedicionPendiente(
            f"Antes de salir, mide el radio de la bobina montada: {codigos}."
        )
