"""Catálogo de features y planes (ADR-003).

Los planes son puntos de partida: un tenant puede activar features sueltas
sin cambiar de plan completo.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TenantFeature

FEATURES_DEFAULT: dict[str, bool] = {
    "receiving_simple": True,
    "receiving_asn": False,
    "receiving_quality_check": False,
    "auto_link_coil": False,
    "fifo_bubble": False,
    "fifo_suggestions": False,
    "pico_suggestion": False,
    "coste_real": False,
    "coste_estandar": True,
    "oee_kpis": False,
    "traceability_full": False,
    "kardex_audit": True,  # obligatorio en todos los planes
}

PLANES: dict[str, dict[str, bool]] = {
    "basico": {**FEATURES_DEFAULT},
    "pro": {
        **FEATURES_DEFAULT,
        "auto_link_coil": True,
        "fifo_bubble": True,
        "fifo_suggestions": True,
        "pico_suggestion": True,
        "coste_real": True,
        "oee_kpis": True,
    },
    "industrial": {
        **FEATURES_DEFAULT,
        "receiving_asn": True,
        "receiving_quality_check": True,
        "auto_link_coil": True,
        "fifo_bubble": True,
        "fifo_suggestions": True,
        "pico_suggestion": True,
        "coste_real": True,
        "oee_kpis": True,
        "traceability_full": True,
    },
}


def get_tenant_features(db: Session, tenant_id: Any) -> dict[str, bool]:
    """Devuelve el mapa de features del tenant (default si no existe fila)."""
    row = db.scalar(select(TenantFeature).where(TenantFeature.tenant_id == tenant_id))
    if row is None:
        return {**FEATURES_DEFAULT}
    return {**FEATURES_DEFAULT, **row.features}


def set_tenant_plan(db: Session, tenant_id: Any, plan: str) -> TenantFeature:
    """Crea o actualiza el tenant con un plan predefinido."""
    if plan not in PLANES:
        raise ValueError(f"Plan desconocido: {plan}. Válidos: {list(PLANES)}")
    row = db.get(TenantFeature, tenant_id)
    if row is None:
        row = TenantFeature(tenant_id=tenant_id, plan=plan, features={**PLANES[plan]})
        db.add(row)
    else:
        row.plan = plan
        row.features = {**PLANES[plan]}
    db.commit()
    db.refresh(row)
    return row


def has_feature(db: Session, tenant_id: Any, feature: str) -> bool:
    """¿Tiene el tenant esta feature activa?"""
    return get_tenant_features(db, tenant_id).get(feature, False)
