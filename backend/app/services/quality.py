"""Servicio de autocontrol de calidad (spec 04 §3.2): evaluación y registro.

Portado de QualityService.js y QualityController.js del legacy v2:
- límites inclusivos (min <= valor <= max), tolerancias asimétricas
- checks sin medición entrante se omiten (no bloquean el registro)
- approved (todo pasa) / rejected (falla un crítico) / rework (solo no críticos)
- pass_fail/visual: solo `true`, `'pass'` u `'OK'` pasan (spec 04 §5)
- largos dinámicos de la orden: override del nominal a `meters_per_piece * 1000`
  para checks cuyo nombre matchea /largo\\s*total|longitud/i (spec 04 regla 5)

El registro NUNCA bloquea la producción: un resultado `rejected` se persiste
igual y la trazabilidad es best-effort (log_event traga errores).
"""

import re
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.quality import ManufacturingModel, QualityMeasurement, QualityRecord
from app.services import traceability

_PATRON_LARGO = re.compile(r"largo\s*total|longitud", re.IGNORECASE)


def evaluar_numerico(nominal, tol_plus, tol_minus, valor) -> bool:
    """Límites INCLUSIVOS (spec 04 regla 4): un valor en el límite pasa."""
    max_limite = nominal + (tol_plus if tol_plus is not None else 0)
    min_limite = nominal - (tol_minus if tol_minus is not None else 0)
    try:
        return min_limite <= valor <= max_limite
    except TypeError:
        return False  # valor no numérico en check numeric: falla (spec 04 §5)


def evaluar_inspeccion(plan, mediciones, context_overrides=None):
    """Evalúa las mediciones contra el plan y devuelve (procesadas, estado).

    `plan` es la lista de QualityPlanCheck del modelo; `mediciones` es la lista
    entrante `[{check_name, value_entered}]`. Los checks sin medición se omiten.
    """
    overrides = context_overrides or {}
    procesadas: list[dict] = []
    todo_pasa = True
    fallo_critico = False

    for check in plan:
        entrada = next(
            (m for m in mediciones if m["check_name"] == check.name), None
        )
        if entrada is None:
            continue  # check sin medición: no bloquea (spec 04 regla 6)

        valor = entrada["value_entered"]
        nominal_efectivo = overrides.get(check.name, {}).get(
            "nominal_value", check.nominal_value
        )

        if check.tipo == "numeric":
            pasa = evaluar_numerico(
                nominal_efectivo, check.tolerance_plus, check.tolerance_minus, valor
            )
        else:  # pass_fail | visual
            pasa = valor is True or valor == "pass" or valor == "OK"

        procesadas.append(
            {
                "check_name": check.name,
                "value_entered": valor,
                "is_passed": pasa,
                "nominal": nominal_efectivo,
                "tol_plus": check.tolerance_plus,
                "tol_minus": check.tolerance_minus,
            }
        )

        if not pasa:
            todo_pasa = False
            if check.is_critical:
                fallo_critico = True

    estado = "approved" if todo_pasa else ("rejected" if fallo_critico else "rework")
    return procesadas, estado


def _resolver_tenant(db: Session):
    """Primer tenant (patrón demo; auth por roles pendiente Fase 5)."""
    from app.models import Tenant

    return db.query(Tenant).order_by(Tenant.created_at).first()


def _resolver_operario(db: Session, tenant_id) -> uuid.UUID:
    """Operario de la demo (primer user del tenant); fallback al usuario system."""
    from app.models import User
    from app.services.receiving import _system_user

    operario = (
        db.query(User)
        .filter(User.tenant_id == tenant_id, User.role == "operator")
        .order_by(User.created_at)
        .first()
    )
    if operario is not None:
        return operario.id
    return _system_user(db, tenant_id)


def _resolver_linea(db: Session, order_id, workstation_id):
    """Línea de la orden en el puesto (para largo dinámico y traza)."""
    from app.models import OrderLine

    return db.scalar(
        select(OrderLine).where(
            OrderLine.order_id == order_id,
            OrderLine.workstation_id == workstation_id,
        )
    )


def _resolver_largo_orden(db: Session, order_id, workstation_id) -> Decimal | None:
    """Largo real de la orden en mm (spec 04 regla 5): meters_per_piece * 1000."""
    linea = _resolver_linea(db, order_id, workstation_id)
    if linea is not None and linea.meters_per_piece is not None:
        return Decimal(str(linea.meters_per_piece)) * Decimal("1000")
    return None


def registrar_autocontrol(
    db: Session,
    *,
    tenant_id: uuid.UUID | None,
    operator_id: uuid.UUID | None,
    order_id: uuid.UUID,
    workstation_id: str,
    manufacturing_model_id: uuid.UUID,
    stock_item_id: uuid.UUID | None = None,
    mediciones: list[dict],
    notes: str | None = None,
) -> QualityRecord:
    """Orquesta el registro de un autocontrol (spec 04 §3.2.3)."""
    if tenant_id is None:
        tenant = _resolver_tenant(db)
        if tenant is None:
            raise ValueError("No hay tenant configurado")
        tenant_id = tenant.id
    if operator_id is None:
        operator_id = _resolver_operario(db, tenant_id)

    modelo = db.get(ManufacturingModel, manufacturing_model_id)
    if modelo is None or modelo.tenant_id != tenant_id:
        raise ValueError("Plantilla de calidad no encontrada")

    overrides = {}
    largo = _resolver_largo_orden(db, order_id, workstation_id)
    if largo is not None:
        for check in modelo.quality_plan:
            if _PATRON_LARGO.search(check.name):
                overrides[check.name] = {"nominal_value": largo}

    procesadas, estado = evaluar_inspeccion(modelo.quality_plan, mediciones, overrides)

    record = QualityRecord(
        tenant_id=tenant_id,
        order_id=order_id,
        workstation_id=workstation_id,
        operator_id=operator_id,
        stock_item_id=stock_item_id,
        manufacturing_model_id=modelo.id,
        overall_status=estado,
        notes=notes,
    )
    db.add(record)
    db.flush()

    for m in procesadas:
        db.add(
            QualityMeasurement(
                quality_record_id=record.id,
                check_name=m["check_name"],
                value_entered=m["value_entered"],
                is_passed=m["is_passed"],
                nominal=m["nominal"],
                tol_plus=m["tol_plus"],
                tol_minus=m["tol_minus"],
            )
        )

    # Trazabilidad best-effort (spec 04 §3.1): si el log falla, no rompe el
    # registro de calidad ni la planta. line_id se resuelve de la línea del
    # puesto (ProductionLog.line_id es NOT NULL en el v2; el legacy usaba null).
    linea = _resolver_linea(db, order_id, workstation_id)
    traceability.log_event(
        db,
        tenant_id=tenant_id,
        order_id=order_id,
        line_id=linea.id if linea is not None else None,
        operator_id=operator_id,
        action="quality_check",
        quantity=0,
        metadata={
            "workstationId": workstation_id,
            "status": estado,
            "manufacturingModel": modelo.name,
            "measurementsCount": len(procesadas),
            "stockItemId": str(stock_item_id) if stock_item_id else None,
        },
    )

    db.commit()
    db.refresh(record)
    return record


def listar_registros(
    db: Session, tenant_id: uuid.UUID, order_id: uuid.UUID | None = None, limit: int = 20
) -> list[QualityRecord]:
    """Registros de calidad del tenant, createdAt desc, límite duro (spec 04)."""
    q = db.query(QualityRecord).filter(QualityRecord.tenant_id == tenant_id)
    if order_id is not None:
        q = q.filter(QualityRecord.order_id == order_id)
    return q.order_by(QualityRecord.created_at.desc()).limit(min(limit, 50)).all()


def listar_modelos(db: Session, tenant_id: uuid.UUID) -> list[ManufacturingModel]:
    """Plantillas activas del tenant con su qualityPlan ordenado."""
    return (
        db.query(ManufacturingModel)
        .filter(ManufacturingModel.tenant_id == tenant_id, ManufacturingModel.is_active)
        .order_by(ManufacturingModel.created_at)
        .all()
    )
