"""OEE y KPIs del panel Supervisor (spec 03, adaptado a los modelos del v2).

El v2 no tiene ProductionLog/Incidencia/Tooling/UserShift (modelos legacy que
no se portaron). El cálculo usa los datos reales del v2:
- produced_quantity / total_quantity de las líneas de órdenes activas → P
- real_time acumulado vs turno estándar (480 min) → A
- scrap_material_qty vs real_material_qty → Q
- Order.estimado_total_cost vs real_total_cost → KPIs financieros

OEE = A × P × Q, cada componente clamp a [0, 100]. Sin datos: 0, nunca
datos ficticios (AUDIT FIX 2.3 de la spec 03).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Incidencia, Order, OrderLine

TURNO_MINUTOS = 480  # turno estándar de 8 h (spec 03 3.2)


def _clamp(value: float, maximo: float = 100.0) -> float:
    return round(max(0.0, min(value, maximo)), 2)


def calcular_oee(db: Session, tenant_id) -> dict:
    """OEE global del turno actual para el panel Supervisor."""
    lineas = db.scalars(
        select(OrderLine)
        .join(Order, Order.id == OrderLine.order_id)
        .where(Order.tenant_id == tenant_id)
    ).all()

    total_piezas = sum(float(linea_i.produced_quantity or 0) for linea_i in lineas)
    total_objetivo = sum(float(linea_i.total_quantity or 0) for linea_i in lineas)
    total_tiempo = sum(float(linea_i.real_time or 0) for linea_i in lineas)
    total_scrap = sum(float(linea_i.scrap_material_qty or 0) for linea_i in lineas)
    total_material = sum(float(linea_i.real_material_qty or 0) for linea_i in lineas)

    # Downtime declarado por incidencias (spec 04 regla 8): los minutos de
    # parada de las incidencias del tenant restan al tiempo operativo efectivo.
    total_downtime = sum(
        float(i.tiempo_parada_min or 0)
        for i in db.scalars(
            select(Incidencia).where(Incidencia.tenant_id == tenant_id)
        )
    )

    # Disponibilidad: (tiempo operativo real - downtime) / turno estándar
    lineas_con_tiempo = sum(1 for linea_i in lineas if (linea_i.real_time or 0) > 0)
    disponible = TURNO_MINUTOS * max(lineas_con_tiempo, 1) if lineas_con_tiempo else 0
    tiempo_efectivo = max(total_tiempo - total_downtime, 0)
    availability = _clamp((tiempo_efectivo / disponible) * 100) if disponible > 0 else 0.0

    # Rendimiento: piezas producidas / objetivo
    performance = _clamp((total_piezas / total_objetivo) * 100) if total_objetivo > 0 else 0.0

    # Calidad: material bueno / material total (1 - tasa de merma)
    material_bueno = total_material - total_scrap
    quality = _clamp((material_bueno / total_material) * 100) if total_material > 0 else 100.0

    oee = round(availability * performance * quality / 10000, 2)

    return {
        "availability": availability,
        "performance": performance,
        "quality": quality,
        "oee": oee,
        "raw": {
            "total_pieces": round(total_piezas, 2),
            "total_objetivo": round(total_objetivo, 2),
            "total_tiempo_min": round(total_tiempo, 2),
            "scrap_kg": round(total_scrap, 2),
            "material_kg": round(total_material, 2),
            "total_downtime_min": round(total_downtime, 2),
        },
    }


def calcular_kpis(db: Session, tenant_id) -> dict:
    """KPIs financieros: costes, varianzas y tasa de merma (spec 03 3.3)."""
    ordenes = db.scalars(
        select(Order).where(
            Order.tenant_id == tenant_id,
            Order.estado.in_(["active", "completed", "in_progress"]),
        )
    ).all()

    total_estimado = sum(float(o.estimado_total_cost or 0) for o in ordenes)
    total_real = sum(float(o.real_total_cost or 0) for o in ordenes)
    activas = sum(1 for o in ordenes if o.estado == "active")
    completadas = sum(1 for o in ordenes if o.estado == "completed")

    # Material real: desde líneas (los MaterialConsumo ya están en real_material_qty)
    lineas = db.scalars(
        select(OrderLine)
        .join(Order, Order.id == OrderLine.order_id)
        .where(Order.tenant_id == tenant_id)
    ).all()
    total_material_real = sum(float(linea_i.real_material_qty or 0) for linea_i in lineas)
    total_scrap = sum(float(linea_i.scrap_material_qty or 0) for linea_i in lineas)
    total_target_material = sum(float(linea_i.target_material_qty or 0) for linea_i in lineas)

    cost_variance = round(total_real - total_estimado, 2)
    cost_efficiency = round((total_estimado / total_real) * 100, 1) if total_real > 0 else 0.0
    material_variance = round(total_material_real - total_target_material, 2)
    material_efficiency = (
        round((total_target_material / total_material_real) * 100, 1)
        if total_material_real > 0
        else 0.0
    )
    scrap_rate = (
        round((total_scrap / total_material_real) * 100, 1) if total_material_real > 0 else 0.0
    )

    return {
        "orders_total": len(ordenes),
        "orders_active": activas,
        "orders_completed": completadas,
        "estimated_cost": round(total_estimado, 2),
        "real_cost": round(total_real, 2),
        "cost_variance": cost_variance,
        "cost_efficiency": cost_efficiency,
        "material_variance": material_variance,
        "material_efficiency": material_efficiency,
        "scrap_rate": scrap_rate,
    }
