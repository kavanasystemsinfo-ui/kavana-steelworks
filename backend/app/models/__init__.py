"""Registro de todos los modelos para Alembic y metadata."""
from app.core.database import Base  # noqa: F401
from app.models.coil_link import CoilLink  # noqa: F401
from app.models.material import Material, StockItem  # noqa: F401
from app.models.order import Order, OrderLine  # noqa: F401
from app.models.tenant import Tenant, User  # noqa: F401
from app.models.transaction import MaterialConsumo, MaterialTransaction  # noqa: F401

__all__ = [
    "Base",
    "CoilLink",
    "Material",
    "StockItem",
    "Order",
    "OrderLine",
    "Tenant",
    "User",
    "MaterialConsumo",
    "MaterialTransaction",
]
