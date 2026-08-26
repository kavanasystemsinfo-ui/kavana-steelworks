"""Asistentes RAG de KAVANA Steelworks (patrón RouteAI, portado a Python).

Dos bots sobre el MISMO corpus (documentación real del repo):
- ask: bot de USUARIO. Explica el producto y su uso desde la perspectiva del
  operario/supervisor (qué es, cómo se usa, qué flujos hay).
- ask-tech: bot TÉCNICO para reclutadores. Responde arquitectura, decisiones
  (ADRs), tests, seguridad y limitaciones con tono de entrevista técnica.

Regla de honestidad (no negociable): solo responde con lo documentado; si la
pregunta no está en el corpus, lo dice y remite a Jorge. Nunca inventa.

Búsqueda TF-IDF en memoria (sin embeddings ni coste). LLM vía OpenRouter.
El corpus se copia al contenedor en el build (Dockerfile COPY docs/).
"""

import logging
import math
import os
import re
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# En local: la raíz del repo (backend/app/services -> repo). En producción:
# /docs (el Dockerfile copia README/SECURITY/docs allí) señalado por env.
REPO_ROOT = Path(os.getenv("STEELWORKS_DOCS_ROOT") or Path(__file__).resolve().parents[3])

MODELO_FREE = os.getenv("ASSISTANT_MODEL_FREE", "nvidia/nemotron-3-super-120b-a12b:free")
MODELO_PRO = os.getenv("ASSISTANT_MODEL_PRO", "nvidia/nemotron-3-super-120b-a12b:free")

# Protección del asistente público (decisión Jorge 2026-08-25):
# - por IP: 15 preguntas / hora (evita el martilleo de un visitante)
# - global: 300 preguntas / día (evita abuso de coste del LLM)
# - longitud: 500 caracteres por pregunta (validada también en el router)
MAX_PREGUNTAS_VENTANA = 15
VENTANA_SEGUNDOS = 60 * 60
MAX_PREGUNTAS_DIA = 300
_preguntas_ip: dict[str, list[float]] = {}
_dia_actual: str = ""
_preguntas_dia = 0


class RateLimitExceeded(Exception):
    pass


def enforce_rate_limit(ip: str) -> None:
    global _preguntas_dia, _dia_actual
    hoy = time.strftime("%Y-%m-%d")
    if hoy != _dia_actual:
        _dia_actual = hoy
        _preguntas_dia = 0
    if _preguntas_dia >= MAX_PREGUNTAS_DIA:
        raise RateLimitExceeded(
            "El asistente alcanzó su límite diario de preguntas. Vuelve mañana."
        )
    ahora = time.time()
    vivas = {
        ip: [t for t in ts if ahora - t < VENTANA_SEGUNDOS]
        for ip, ts in _preguntas_ip.items()
    }
    _preguntas_ip.clear()
    _preguntas_ip.update(vivas)
    recientes = [t for t in _preguntas_ip.get(ip, []) if ahora - t < VENTANA_SEGUNDOS]
    if len(recientes) >= MAX_PREGUNTAS_VENTANA:
        raise RateLimitExceeded(
            f"Demasiadas preguntas. Límite {MAX_PREGUNTAS_VENTANA}/hora por visitante."
        )
    recientes.append(ahora)
    _preguntas_ip[ip] = recientes
    _preguntas_dia += 1


# ---------------------------------------------------------------- corpus


def _fuentes_corpus() -> list[str]:
    fuentes = [
        "README.md",
        "SECURITY.md",
        "docs/decisions-log.md",
        "docs/plan-reconstruccion-v4.md",
        "docs/audit/changelog.md",
    ]
    for subdir in ("docs/adr", "docs/specs"):
        d = REPO_ROOT / subdir
        if d.is_dir():
            fuentes.extend(
                f"{subdir}/{f.name}"
                for f in sorted(d.glob("*.md"))
                if "template" not in f.name.lower()
            )
    return fuentes


def cargar_corpus() -> list[dict]:
    chunks: list[dict] = []
    for rel in _fuentes_corpus():
        abs_path = REPO_ROOT / rel
        if not abs_path.exists():
            continue
        texto = abs_path.read_text(encoding="utf-8", errors="replace")
        # Chunks por secciones markdown (## / ###) para recuperación temática
        secciones = re.split(r"\n(?=#{1,3} )", texto)
        for sec in secciones:
            m = re.search(r"^#{1,3} (.+)$", sec, re.M)
            titulo = m.group(1) if m else rel
            if len(sec.strip()) < 60:
                continue
            chunks.append(
                {"fuente": rel, "titulo": titulo.strip(), "texto": sec.strip()[:6000]}
            )
    return chunks


# ---------------------------------------------------------------- TF-IDF

_STOPWORDS = set(
    """para por con los las el la un una que como del al se su sus en de y o a
    este esta estos estas eso esa donde cuando cual cuales sobre entre mediante
    desde hasta tiene tienen hacer hace sido ser está estan fue eran puede
    kavana steelworks sistema aplicacion app proyecto datos""".split()
)


def tokenizar(texto: str) -> list[str]:
    return [
        w
        for w in re.sub(r"[^a-záéíóúñü0-9]", " ", texto.lower()).split()
        if len(w) > 2 and w not in _STOPWORDS
    ]


def construir_indice(chunks: list[dict]) -> dict:
    df: dict[str, int] = {}
    for c in chunks:
        for t in set(tokenizar(c["texto"])):
            df[t] = df.get(t, 0) + 1
    n = len(chunks)
    idf = {t: math.log(1 + n / d) for t, d in df.items()}
    vectores = []
    for c in chunks:
        tf: dict[str, int] = {}
        for t in tokenizar(c["texto"]):
            tf[t] = tf.get(t, 0) + 1
        vectores.append({t: cnt * idf.get(t, 0) for t, cnt in tf.items()})
    return {"chunks": chunks, "vectores": vectores}


def _similitud(a: dict, b: dict) -> float:
    dot = sum(v * b.get(t, 0) for t, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def buscar(indice: dict, pregunta: str, top: int = 6) -> list[dict]:
    qvec: dict[str, int] = {}
    for t in tokenizar(pregunta):
        qvec[t] = qvec.get(t, 0) + 1
    scored = sorted(
        ((i, _similitud(qvec, vec)) for i, vec in enumerate(indice["vectores"])),
        key=lambda x: -x[1],
    )[:top]
    return [{**indice["chunks"][i], "score": s} for i, s in scored]


# ---------------------------------------------------------------- LLM


async def llamar_openrouter(api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    async with httpx.AsyncClient(timeout=45) as client:
        res = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://steelworks.kavanasystems.com",
                "X-Title": "KAVANA Steelworks Assistant",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 900,
            },
        )
    if res.status_code != 200:
        raise RuntimeError(f"OpenRouter {res.status_code}: {res.text[:300]}")
    data = res.json()
    return (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()


_SENALES_COMPLEJA = (
    "compara", "diferencia", "por qué no", "por que no", "alternativas",
    "tradeoff", "desventaja", "ventaja", "decidiste", "elegiste", "descartaste",
    "cómo resolverías", "cómo harías", "mejoraría", "cambiarías",
    "arquitectura", "diseño", "escalabilidad", "seguridad", "multi-tenant",
)


def _es_compleja(pregunta: str) -> bool:
    q = pregunta.lower()
    return any(s in q for s in _SENALES_COMPLEJA)


_PERSONA_USUARIO = [
    "Eres el asistente virtual de KAVANA Steelworks, un MES/MOM para fábricas",
    "metalúrgicas que trabajan con bobinas de acero (control de bobinas, consumo",
    "FIFO, OEE, calidad y trazabilidad ISO 9001). Diriges tu respuesta al USUARIO",
    "del producto (operario, supervisor o personal de planta): explica qué hace el",
    "sistema y cómo funciona desde el punto de vista de uso, sin jerga de",
    "implementación salvo que pregunten.",
]

_PERSONA_TECH = [
    "Eres el asistente técnico de KAVANA Steelworks, un MES/MOM metalúrgico",
    "(FastAPI + PostgreSQL + React/TS, multi-tenant, desplegado en Fly.io+Vercel).",
    "Un RECLUTADOR TÉCNICO te entrevista sobre el proyecto. Responde con precisión",
    "de ingeniero: arquitectura, decisiones (ADRs), tests, concurrencia, seguridad",
    "y limitaciones reconocidas (ADR-016). Si una limitación fue aceptada y",
    "documentada, dilo abiertamente: conocer las fronteras del sistema es una",
    "fortaleza, no un fallo.",
]


async def responder(api_key: str, pregunta: str, modo: str = "tech") -> dict:
    """Responde una pregunta. modo='user' (bot usuario) o 'tech' (reclutador)."""
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY no configurada")
    if modo not in ("user", "tech"):
        raise ValueError(f"Modo desconocido: {modo}")

    indice = get_indice()
    docs = buscar(indice, pregunta)

    if not docs or docs[0]["score"] < 0.02:
        remite = (
            "pregúntaselo directamente a Jorge, el creador de KAVANA Steelworks"
            if modo == "tech"
            else "puedes contactar con el equipo en kavanasystems.info@gmail.com"
        )
        return {
            "respuesta": f"Eso no aparece en la documentación del proyecto. Si quieres, {remite}.",
            "fuentes": [],
            "modelo": None,
        }

    contexto = "\n\n---\n\n".join(
        f"[FUENTE: {d['fuente']} — {d['titulo']}]\n{d['texto']}" for d in docs
    )

    persona = _PERSONA_TECH if modo == "tech" else _PERSONA_USUARIO
    system_prompt = "\n".join(
        [
            *persona,
            "Respondes EXCLUSIVAMENTE con la documentación real del proyecto en el contexto.",
            "Reglas:",
            "- Responde en español, claro y directo.",
            "- Si el contexto contiene la respuesta, explícala apoyándote en sus datos.",
            '- Si NO la contiene, di literalmente: "Eso no está en la documentación '
            'del proyecto." y nada más.',
            "- NUNCA inventes datos, métricas, archivos ni decisiones fuera del contexto.",
            '- Al final añade "Ver: fuente1, fuente2" solo si usaste el contexto.',
        ]
    )
    user_prompt = f"PREGUNTA:\n{pregunta}\n\nCONTEXTO (documentación del proyecto):\n{contexto}"

    model = MODELO_PRO if _es_compleja(pregunta) else MODELO_FREE
    try:
        respuesta = await llamar_openrouter(api_key, model, system_prompt, user_prompt)
    except RuntimeError:
        if not _es_compleja(pregunta):
            respuesta = await llamar_openrouter(api_key, MODELO_PRO, system_prompt, user_prompt)
        else:
            raise

    return {
        "respuesta": respuesta,
        "fuentes": sorted({d["fuente"] for d in docs}),
        "modelo": model,
    }


# ---------------------------------------------------------------- singleton

_indice: dict | None = None


def get_indice() -> dict:
    global _indice
    if _indice is None:
        _indice = construir_indice(cargar_corpus())
    return _indice


def estadisticas_corpus() -> dict:
    idx = get_indice()
    return {
        "chunks": len(idx["chunks"]),
        "fuentes": len({c["fuente"] for c in idx["chunks"]}),
    }
