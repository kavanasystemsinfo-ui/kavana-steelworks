"""OEE y KPIs del panel Supervisor (spec 03, adaptado a los modelos del v2).

El v2 no tiene ProductionLog/Incidencia/Tooling/UserShift (modelos legacy que
no se portaron). El cálculo usa los datos reales del v2:
- produced_quantity / total_quantity de las líneas de órdenes activas → P
- real_time acumulado vs turno estándar (480 min) → A
- scrap_material_qty vs real_material_qty → Q
- coste real vs estimado de las líneas (services/costes.py) → KPIs financieros

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
    """KPIs financieros: costes, varianzas y tasa de merma (spec 03 3.3).

    El coste sale de las líneas de orden (services/costes.py), la misma
    fuente que la tabla de coste por orden: las dos cifras siempre cuadran.
    La desviación compara material real vs estimado SOLO en las órdenes
    completadas que tienen estimado (precio €/kg y objetivo); sin base, None.
    """
    from app.services.costes import costes_por_orden

    ordenes = costes_por_orden(db, tenant_id)
    activas = sum(1 for o in ordenes if o["estado"] == "active")
    completadas = sum(1 for o in ordenes if o["estado"] == "completed")

    total_real = sum(o["real_total"] for o in ordenes)
    total_material = sum(o["real_material"] for o in ordenes)
    total_mano_obra = sum(o["mano_obra"] for o in ordenes)
    scrap_coste = sum(o["scrap_coste"] for o in ordenes)
    # Comparable = completada y con estimado (ver costes_por_orden)
    con_estimado = [o for o in ordenes if o["desviacion_material"] is not None]
    total_estimado = sum(o["estimado_material"] for o in con_estimado)
    real_comparable = sum(o["real_material_comparable"] for o in con_estimado)

    # Material real: desde líneas (los MaterialConsumo ya están en real_material_qty)
    lineas = db.scalars(
        select(OrderLine)
        .join(Order, Order.id == OrderLine.order_id)
        .where(Order.tenant_id == tenant_id)
    ).all()
    total_material_real = sum(float(linea_i.real_material_qty or 0) for linea_i in lineas)
    total_scrap = sum(float(linea_i.scrap_material_qty or 0) for linea_i in lineas)
    total_target_material = sum(float(linea_i.target_material_qty or 0) for linea_i in lineas)

    cost_variance = round(real_comparable - total_estimado, 2) if con_estimado else None
    cost_efficiency = (
        round((total_estimado / real_comparable) * 100, 1)
        if con_estimado and real_comparable > 0
        else 0.0
    )
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
        "estimated_cost": round(total_estimado, 2) if con_estimado else None,
        "real_cost": round(total_real, 2),
        "real_material_cost": round(total_material, 2),
        "labor_cost": round(total_mano_obra, 2),
        "real_material_comparable": round(real_comparable, 2),
        "orders_with_estimate": len(con_estimado),
        "scrap_cost": round(scrap_coste, 2),
        "cost_variance": cost_variance,
        "cost_efficiency": cost_efficiency,
        "material_variance": material_variance,
        "material_efficiency": material_efficiency,
        "scrap_rate": scrap_rate,
    }
