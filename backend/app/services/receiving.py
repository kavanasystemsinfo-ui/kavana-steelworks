"""Servicio de recepción de materiales (Materias Primas, spec 06).

Flujo estándar de industria adaptado (decisión Jorge 2026-08-14):
- Registro cuando llega (sin albarán previo en flujo mínimo)
- Entrada directa a producción (estado 'activo', sin cuarentena)
- Coste real de compra si se conoce, si no estándar del material
- Kardex de entrada (GRN) + actualización de stock del material
"""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Material, MaterialTransaction, StockItem


def _system_user(db: Session, tenant_id) -> uuid.UUID:
    """Usuario 'system' para movimientos automáticos (patrón del v2)."""
    from app.models import User

    user = db.scalar(
        select(User).where(User.tenant_id == tenant_id, User.email == "system@kavana.local")
    )
    if user is None:
        user = User(
            tenant_id=tenant_id,
            email="system@kavana.local",
            name="System",
            password_hash="!disabled",
            role="admin",
        )
        db.add(user)
        db.flush()
    return user.id


def receive_coil(
    db: Session,
    tenant_id,
    user_id,
    *,
    material_id,
    lote: str,
    coil_id: str | None = None,
    peso: Decimal | float,
    width_mm: Decimal | float | None = None,
    thickness_mm: Decimal | float | None = None,
    coste_real: Decimal | float | None = None,
    ubicacion: str | None = None,
    heat_number: str | None = None,
    grado_acero: str | None = None,
    supplier_coil_id: str | None = None,
) -> StockItem:
    """Da de alta una bobina recibida y registra su entrada en Kardex.

    Devuelve el StockItem creado. La bobina entra activa (entrada directa).
    Si user_id es None, el movimiento se atribuye al usuario 'system'.
    """
    if user_id is None:
        user_id = _system_user(db, tenant_id)

    material = db.get(Material, material_id)
    if material is None:
        raise ValueError(f"Material {material_id} no existe")

    peso_dec = Decimal(str(peso))
    coste_por_unidad = (
        Decimal(str(coste_real)) if coste_real is not None else material.cost_per_unit
    )
    costing_method = "real" if coste_real is not None else "standard"

    bobina = StockItem(
        tenant_id=tenant_id,
        material_id=material_id,
        lote=lote,
        coil_id=coil_id or f"COIL-{lote}",
        cantidad_inicial=peso_dec,
        cantidad_disponible=peso_dec,
        unit=material.unit or "kg",
        width_mm=Decimal(str(width_mm)) if width_mm else None,
        thickness_mm=Decimal(str(thickness_mm)) if thickness_mm else None,
        coste_por_unidad=coste_por_unidad,
        costing_method=costing_method,
        fecha_entrada=datetime.now(UTC),
        ubicacion=ubicacion,
        estado="activo",
        heat_number=heat_number,
        grado_acero=grado_acero,
        supplier_coil_id=supplier_coil_id,
        creado_por=user_id,
    )
    db.add(bobina)
    db.flush()

    # GRN: Kardex de entrada (inmutable)
    db.add(
        MaterialTransaction(
            tenant_id=tenant_id,
            material_id=material_id,
            stock_item_id=bobina.id,
            tipo="entrada_compra",
            cantidad=peso_dec,
            cantidad_anterior=Decimal("0"),
            cantidad_nueva=peso_dec,
            motivo=f"Recepción de bobina {bobina.coil_id} (lote {lote})",
            realizado_por=user_id,
        )
    )

    # Stock agregado del material
    material.stock_current = (material.stock_current or Decimal("0")) + peso_dec

    db.commit()
    db.refresh(bobina)
    return bobina


def build_label(bobina: StockItem) -> dict:
    """Genera los datos de la etiqueta QR escaneable de la bobina.

    Codifica lo que el operario necesita al vincular: identidad, material,
    peso, dimensiones y ubicación (spec 06, paso 4).
    """
    qr_data = json.dumps(
        {
            "coil_id": bobina.coil_id,
            "lote": bobina.lote,
            "material_id": str(bobina.material_id),
            "peso": f"{bobina.cantidad_disponible:.4f}",
            "ancho_mm": f"{bobina.width_mm:.3f}" if bobina.width_mm else "",
            "espesor_mm": f"{bobina.thickness_mm:.3f}" if bobina.thickness_mm else "",
            "ubicacion": bobina.ubicacion or "",
        }
    )
    return {"qr_data": qr_data, "qr_svg": f"<svg>QR-{bobina.coil_id}</svg>"}


def move_coil(
    db: Session,
    tenant_id,
    user_id,
    *,
    stock_item_id,
    nueva_ubicacion: str,
) -> StockItem:
    """Putaway: asigna una nueva ubicación y lo registra como traslado.

    Patrón del v2: el traslado se registra con cantidad 0 y el motivo
    indica la ubicación nueva (Kardex de movimientos).
    """
    bobina = db.get(StockItem, stock_item_id)
    if bobina is None:
        raise ValueError(f"Bobina {stock_item_id} no existe")

    ubicacion_anterior = bobina.ubicacion
    bobina.ubicacion = nueva_ubicacion

    db.add(
        MaterialTransaction(
            tenant_id=tenant_id,
            material_id=bobina.material_id,
            stock_item_id=bobina.id,
            tipo="traslado",
            cantidad=Decimal("0"),
            cantidad_anterior=Decimal("0"),
            cantidad_nueva=Decimal("0"),
            motivo=f"Ubicada en {nueva_ubicacion} (desde {ubicacion_anterior or 'sin ubicación'})",
            realizado_por=user_id,
        )
    )

    db.commit()
    db.refresh(bobina)
    return bobina
