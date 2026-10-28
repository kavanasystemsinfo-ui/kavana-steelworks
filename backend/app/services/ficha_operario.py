"""Ficha de la orden para el panel de operario y horas automáticas.

Rediseño del panel de operario (maqueta aprobada por Jorge, 28-10): arriba,
siempre a la vista, los datos clave de la orden (número, cliente, entrega,
modelo, material con medidas, largo, ritmo y lo hecho), y la bobina montada
con los kilos que quedan y para cuántas piezas dan.

Las horas no las escribe el operario: un registro de piezas cuenta el tiempo
desde su último registro en esa línea dentro de su turno, o desde que
inició sesión (horas_automaticas).
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ManufacturingModel,
    Material,
    Order,
    OrderLine,
    Product,
    ProductionLog,
    StockItem,
    UserShift,
    Workstation,
)

TOPE_HORAS = Decimal("12")  # un registro nunca cuenta más que un turno largo


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def inicio_tramo(db: Session, user_id, line_id) -> datetime | None:
    """Desde cuándo cuenta el próximo registro: el último del operario en la
    línea dentro de su turno, o el inicio de sesión. None sin turno activo."""
    turno = db.scalar(
        select(UserShift).where(UserShift.operator_id == user_id, UserShift.status == "active")
    )
    if turno is None:
        return None
    login = _utc(turno.login_time)
    ultimo = db.scalar(
        select(ProductionLog.timestamp)
        .where(
            ProductionLog.operator_id == user_id,
            ProductionLog.line_id == line_id,
            ProductionLog.action == "produce",
            ProductionLog.timestamp >= login,
        )
        .order_by(ProductionLog.timestamp.desc())
    )
    return _utc(ultimo) if ultimo else login


def horas_automaticas(db: Session, user_id, line_id, ahora: datetime | None = None) -> Decimal:
    """Horas trabajadas desde el inicio del tramo (mínimo 0,01; tope 12)."""
    desde = inicio_tramo(db, user_id, line_id)
    if desde is None:
        return Decimal("0")
    segundos = max(((ahora or datetime.now(UTC)) - desde).total_seconds(), 0)
    horas = Decimal(str(round(segundos / 3600, 2)))
    return min(max(horas, Decimal("0.01")), TOPE_HORAS)


def _plazo(entrega: datetime | None, faltan: Decimal, ritmo: Decimal | None) -> str:
    """a_tiempo / en_riesgo / retraso / sin_plazo, con lo que falta al ritmo previsto."""
    if entrega is None:
        return "sin_plazo"
    ahora = datetime.now(UTC)
    entrega = _utc(entrega)
    if faltan <= 0:
        return "a_tiempo"
    if entrega < ahora:
        return "retraso"
    if ritmo and ahora + timedelta(hours=float(faltan / ritmo)) > entrega:
        return "en_riesgo"
    return "a_tiempo"


def ficha_orden(db: Session, tenant_id, user_id, order_id, line_id) -> dict:
    from app.services.production import _calcular_kg_por_pieza

    orden = db.get(Order, order_id)
    linea = db.get(OrderLine, line_id)
    if orden is None or orden.tenant_id != tenant_id or linea is None or linea.order_id != orden.id:
        raise ValueError("Orden no encontrada")

    material = db.get(Material, linea.material_id) if linea.material_id else None
    modelo = db.get(ManufacturingModel, linea.modelo_id) if linea.modelo_id else None
    producto = db.get(Product, linea.product_id) if linea.product_id else None
    puesto = db.scalar(
        select(Workstation).where(
            Workstation.tenant_id == tenant_id, Workstation.code == linea.workstation_id
        )
    )
    ritmo = puesto.piezas_hora_nominal if puesto and puesto.piezas_hora_nominal else None
    total = linea.total_quantity or Decimal("0")
    hechas = linea.produced_quantity or Decimal("0")
    faltan = max(total - hechas, Decimal("0"))

    bobina = None
    if linea.active_coil_id:
        b = db.get(StockItem, linea.active_coil_id)
        densidad = (
            (material.density_calibrada * 1000)
            if material and material.density_calibrada
            else (material.density if material and material.density else Decimal("7850"))
        )
        kg_pieza = _calcular_kg_por_pieza(
            ancho_mm=b.width_mm or (material.dimension_ancho_mm if material else None),
            espesor_mm=b.thickness_mm or (material.dimension_espesor_mm if material else None),
            largo_m=linea.meters_per_piece,
            densidad_kgm3=densidad,
        )
        bobina = {
            "id": str(b.id),
            "codigo": b.coil_id or b.lote,
            "kg": round(float(b.cantidad_disponible), 1),
            "kg_inicial": round(float(b.cantidad_inicial), 1),
            "piezas_estimadas": int(b.cantidad_disponible / kg_pieza) if kg_pieza > 0 else None,
        }

    desde = inicio_tramo(db, user_id, linea.id)
    return {
        "numero": orden.numero,
        "cliente": orden.cliente,
        "fecha_entrega": orden.fecha_entrega.isoformat() if orden.fecha_entrega else None,
        "plazo": _plazo(orden.fecha_entrega, faltan, ritmo),
        "modelo": (modelo.code if modelo else None) or (producto.code if producto else None),
        "modelo_nombre": (modelo.name if modelo else None) or (producto.name if producto else None),
        "material": material.code if material else None,
        "material_nombre": material.name if material else None,
        "ancho_mm": float(material.dimension_ancho_mm)
        if material and material.dimension_ancho_mm
        else None,
        "espesor_mm": float(material.dimension_espesor_mm)
        if material and material.dimension_espesor_mm
        else None,
        "largo_mm": round(float(linea.meters_per_piece) * 1000)
        if linea.meters_per_piece
        else None,
        "ritmo": float(ritmo) if ritmo else None,
        "total": float(total),
        "hechas": float(hechas),
        "faltan": float(faltan),
        "bobina": bobina,
        "tramo_desde": desde.isoformat() if desde else None,
    }
