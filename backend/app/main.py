"""Aplicación FastAPI de KAVANA Steelworks.

Fase 2: core con auth JWT, health, y endpoints base. Los routers de
inventario/recepción se exponen en la Fase 3 (frontend) o según necesidad.
"""

from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import autenticar
from app.routers import admin as admin_router
from app.routers import assistant as assistant_router
from app.routers import auth as auth_router
from app.routers import health as health_router
from app.routers import incidencias as incidencias_router
from app.routers import orders as orders_router
from app.routers import production as production_router
from app.routers import quality as quality_router
from app.routers import stock as stock_router
from app.routers import supervisor as supervisor_router
from app.routers import trace as trace_router
from app.routers import ws as ws_router
from app.services.events import broker

settings = get_settings()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Cabeceras de seguridad básicas en cada respuesta de la API."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
        return response


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

app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth_router.router)
app.include_router(admin_router.router)
app.include_router(incidencias_router.router)
app.include_router(orders_router.router)
app.include_router(production_router.router)
app.include_router(quality_router.router)
app.include_router(stock_router.router)
app.include_router(supervisor_router.router)
app.include_router(trace_router.router)
app.include_router(ws_router.router)
app.include_router(health_router.router)
app.include_router(assistant_router.router)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


@app.get("/api/v1/events/{tenant_id}")
def get_events(
    tenant_id: str,
    authorization: str | None = Header(default=None),
    db: Annotated[Session, Depends(get_db)] = None,
):
    """Eventos pendientes del tenant (polling; WebSocket en la Fase 3).

    Autorización (no solo autenticación): el tenant autorizado sale del JWT.
    Un token válido de otro tenant recibe 403 aunque el path apunte a un
    tenant existente (auditoría 2026-08-24, hallazgo 1).
    """
    usuario = autenticar(db, authorization)  # 401 si no hay token válido
    if str(usuario.tenant_id) != str(tenant_id):
        raise HTTPException(status_code=403, detail="Tenant ajeno")
    eventos = broker.get_events(tenant_id)
    return {"tenant_id": tenant_id, "count": len(eventos), "events": eventos}
