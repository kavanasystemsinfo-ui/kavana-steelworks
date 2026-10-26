"""Alertas del centro de mando, calculadas de la misma fuente que su detalle.

Lección del legacy: el panel decía "6 materiales bajo mínimos" mientras la
pantalla de stock decía 0. Aquí cada contador sale de la misma tabla y con
la misma regla que la pantalla que lo detalla:
- stock bajo mínimos: Material.stock_current < stock_minimum (lo que lista
  Materias Primas), solo materiales activos con mínimo configurado.
- incidencias abiertas: estado abierta/en_revision (lo que lista el panel
  de incidencias).

Sin "coste de reposición": comprar es del ERP (frontera MES/ERP).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Incidencia, Material
from app.services.puestos import ESTADOS_INCIDENCIA_ABIERTA


def alertas(db: Session, tenant_id: uuid.UUID) -> dict:
    bajo_minimos = db.scalars(
        select(Material)
        .where(
            Material.tenant_id == tenant_id,
            Material.is_active.is_(True),
            Material.stock_minimum > 0,
            Material.stock_current < Material.stock_minimum,
        )
        .order_by(Material.code)
    ).all()
    incidencias_abiertas = db.scalar(
        select(func.count(Incidencia.id)).where(
            Incidencia.tenant_id == tenant_id,
            Incidencia.estado.in_(ESTADOS_INCIDENCIA_ABIERTA),
        )
    )
    return {
        "stock_bajo_minimos": [
            {
                "code": m.code,
                "name": m.name,
                "stock": float(m.stock_current),
                "minimo": float(m.stock_minimum),
                "unidad": m.unit,
            }
            for m in bajo_minimos
        ],
        "incidencias_abiertas": incidencias_abiertas or 0,
    }
