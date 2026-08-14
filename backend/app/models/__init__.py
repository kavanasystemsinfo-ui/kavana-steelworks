"""Registro de todos los modelos para Alembic y metadata."""

from app.core.database import Base  # noqa: F401
from app.models.coil_link import CoilLink  # noqa: F401
from app.models.material import Material, StockItem  # noqa: F401
from app.models.order import Order, OrderLine  # noqa: F401
from app.models.revoked_token import RevokedToken  # noqa: F401
from app.models.tenant import Tenant, User  # noqa: F401
from app.models.tenant_feature import TenantFeature  # noqa: F401
from app.models.transaction import MaterialConsumo, MaterialTransaction  # noqa: F401
from app.models.user_shift import UserShift  # noqa: F401

__all__ = [
    "Base",
    "CoilLink",
    "Material",
    "StockItem",
    "Order",
    "OrderLine",
    "Tenant",
    "User",
    "TenantFeature",
    "MaterialConsumo",
    "MaterialTransaction",
    "RevokedToken",
    "UserShift",
]
