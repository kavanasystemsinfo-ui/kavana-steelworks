"""Aplicación FastAPI de KAVANA Steelworks.

Fase 2: core con auth JWT, health, y endpoints base. Los routers de
inventario/recepción se exponen en la Fase 3 (frontend) o según necesidad.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import auth as auth_router
from app.routers import production as production_router
from app.routers import stock as stock_router
from app.routers import supervisor as supervisor_router
from app.routers import trace as trace_router
from app.services.events import broker

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="MES/MOM para el sector metalúrgico: bobinas, FIFO, "
    "reconciliación industrial, OEE y trazabilidad ISO 9001.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(stock_router.router)
app.include_router(production_router.router)
app.include_router(supervisor_router.router)
app.include_router(trace_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


@app.get("/api/v1/events/{tenant_id}")
def get_events(tenant_id: str) -> dict:
    """Eventos pendientes del tenant (polling; WebSocket en la Fase 3)."""
    eventos = broker.get_events(tenant_id)
    return {"tenant_id": tenant_id, "count": len(eventos), "events": eventos}
