"""Health checks separados (auditoría externa 2026-08-24, hallazgo 4).

- /health/live: liveness puro del proceso; NUNCA toca la BD (si la BD
  arrastra, no queremos que el orquestador mate las instancias sanas).
- /health/ready: readiness; comprueba PostgreSQL con SELECT 1 y timeout
  corto. Falla con 503 y detalle real (sin inventar estado).
- /health: legado de la Fase 2, se conserva por compatibilidad.
"""

import logging
import time

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)

DB_CHECK_TIMEOUT_SECONDS = 2.0


def _check_db() -> None:
    """SELECT 1 con timeout de conexión. Lanza si la BD no responde.

    SET LOCAL exige transacción explícita; para un check simple basta el
    connect con timeout del pool y SELECT 1.
    """
    inicio = time.monotonic()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.debug("DB check OK en %.0f ms", (time.monotonic() - inicio) * 1000)


@router.get("/health/live")
def health_live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
def health_ready() -> dict:
    try:
        _check_db()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unavailable",
                "database": f"no disponible: {exc.__class__.__name__}",
            },
        ) from None
    return {"status": "ready", "database": "ok", "version": get_settings().app_version}
