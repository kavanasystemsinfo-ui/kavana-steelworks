"""Routers de los asistentes RAG (auditoría Paso 7, 2026-08-24).

- POST /api/v1/assistant/ask       → bot de USUARIO (producto y uso).
- POST /api/v1/assistant/ask-tech  → bot TÉCNICO para reclutadores.
- GET  /api/v1/assistant/stats     → tamaño del corpus (transparencia).

Públicos (sin JWT): el objetivo es que un reclutador interrogue al sistema
sin crear cuenta. Protegidos con rate limit por IP (15 preguntas / hora),
tope global diario (300) y longitud máxima por pregunta (500 caracteres).
Nunca exponen la API key.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services import assistant
from app.services.assistant import RateLimitExceeded

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])
logger = logging.getLogger(__name__)


class Pregunta(BaseModel):
    pregunta: str = Field(min_length=5, max_length=500)


@router.post("/ask")
async def ask_usuario(body: Pregunta, request: Request):
    return await _responder(body, request, modo="user")


@router.post("/ask-tech")
async def ask_tecnico(body: Pregunta, request: Request):
    return await _responder(body, request, modo="tech")


@router.get("/stats")
async def stats():
    return assistant.estadisticas_corpus()


async def _responder(body: Pregunta, request: Request, modo: str) -> dict:
    ip = request.client.host if request.client else "unknown"
    try:
        assistant.enforce_rate_limit(ip)
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from None

    api_key = __import__("os").getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Asistente no disponible: falta configuración del modelo",
        )
    try:
        return await assistant.responder(api_key, body.pregunta, modo=modo)
    except RuntimeError as exc:
        logger.warning("Assistant (%s) fallo LLM: %s", modo, exc)
        raise HTTPException(
            status_code=502, detail="El asistente no está disponible ahora mismo"
        ) from None
