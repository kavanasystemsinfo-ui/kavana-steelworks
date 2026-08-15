"""Registro de todos los modelos para Alembic y metadata."""

from app.core.database import Base  # noqa: F401
from app.models.coil_link import CoilLink  # noqa: F401
from app.models.incidencia import Incidencia, IncidenciaHistorial  # noqa: F401
from app.models.material import Material, StockItem  # noqa: F401
from app.models.order import Order, OrderLine  # noqa: F401
from app.models.quality import (  # noqa: F401
    ManufacturingModel,
    QualityMeasurement,
    QualityPlanCheck,
    QualityRecord,
)
from app.models.revoked_token import RevokedToken  # noqa: F401
from app.models.tenant import Tenant, User  # noqa: F401
from app.models.tenant_feature import TenantFeature  # noqa: F401
from app.models.traceability import ProductionLog  # noqa: F401
from app.models.transaction import MaterialConsumo, MaterialTransaction  # noqa: F401
from app.models.user_shift import UserShift  # noqa: F401

__all__ = [
    "Base",
    "CoilLink",
    "Incidencia",
    "IncidenciaHistorial",
    "Material",
    "StockItem",
    "Order",
    "OrderLine",
    "Tenant",
    "User",
    "TenantFeature",
    "ProductionLog",
    "ManufacturingModel",
    "QualityPlanCheck",
    "QualityRecord",
    "QualityMeasurement",
    "MaterialConsumo",
    "MaterialTransaction",
    "RevokedToken",
    "UserShift",
]
