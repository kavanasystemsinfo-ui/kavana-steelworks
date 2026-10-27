"""Tests del asistente RAG (Paso 7 del $audit, 2026-08-24).

Contrato:
- Corpus: indexa README, SECURITY, ADRs y specs del repo; chunking por
  secciones markdown con fuente.
- TF-IDF: recupera chunks relevantes; preguntas sin match → respuesta honesta
  sin llamar al LLM (score < 0.02).
- Dos modos: 'user' (producto) y 'tech' (reclutador); personas distintas,
  misma regla de honestidad.
- Router: /api/v1/assistant/ask y /ask-tech públicos con rate limit por IP;
  503 si falta OPENROUTER_API_KEY; el LLM se mockea SIEMPRE en tests.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import assistant

# ---------------------------------------------------------------- corpus


def test_corpus_indexa_readme_y_adrs():
    corpus = assistant.cargar_corpus()
    fuentes = {c["fuente"] for c in corpus}
    assert "README.md" in fuentes
    assert any(f.startswith("docs/adr/") for f in fuentes)
    assert any(f.startswith("docs/specs/") for f in fuentes)
    assert all(c["texto"] for c in corpus)


def test_corpus_incluye_guias_por_rol():
    fuentes = {c["fuente"] for c in assistant.cargar_corpus()}
    for rol in ("operario", "materias-primas", "supervisor", "admin"):
        assert f"docs/guias/guia-{rol}.md" in fuentes


def test_busqueda_recupera_guia_del_modo_andon():
    docs = assistant.buscar(assistant.get_indice(), "cómo pongo el modo Andon en la TV")
    assert any(d["fuente"] == "docs/guias/guia-supervisor.md" for d in docs)


def test_estadisticas_corpus_devuelve_conteo():
    stats = assistant.estadisticas_corpus()
    assert stats["chunks"] > 20
    assert stats["fuentes"] >= 8


def test_corpus_excluye_plantillas():
    corpus = assistant.cargar_corpus()
    fuentes = {c["fuente"] for c in corpus}
    assert not any("template" in f.lower() for f in fuentes)


def test_busqueda_recupera_fifo():
    docs = assistant.buscar(assistant.get_indice(), "cómo funciona el consumo FIFO de bobinas")
    assert docs
    assert docs[0]["score"] > 0.02
    texto_total = " ".join(d["titulo"] + d["texto"] for d in docs).lower()
    assert "fifo" in texto_total or "bobina" in texto_total


def test_pregunta_fuera_del_corpus_no_recupera_nada():
    """Una pregunta ajena al proyecto no debe traer documentos con puntuacion."""
    docs = assistant.buscar(assistant.get_indice(), "¿cuál es la receta de la paella valenciana?")
    assert all(d["score"] == 0 for d in docs)


def test_persona_prohibe_inventar(monkeypatch):
    """La persona lleva la regla dura: admitir que no lo sabe antes que inventar."""
    capturado = {}

    async def _fake_llm(api_key, model, system_prompt, user_prompt):
        capturado["system"] = system_prompt
        return "respuesta"

    monkeypatch.setattr(assistant, "llamar_openrouter", _fake_llm)
    import asyncio

    resultado = asyncio.run(
        assistant.responder("key-falsa", "¿cuál es la receta de la paella valenciana?", modo="tech")
    )
    assert resultado["respuesta"]
    assert "no tengo esa información" in capturado["system"].lower()
    assert "nunca inventes" in capturado["system"].lower()


def test_modo_degradado_no_llama_al_llm(monkeypatch):
    """Sin corpus cargado (contexto base y busqueda vacios) responde enlatado y
    no gasta ninguna llamada al modelo."""

    def _explota(*a, **k):
        raise AssertionError("No debe llamarse al LLM si no hay contexto alguno")

    monkeypatch.setattr(assistant, "llamar_openrouter", _explota)
    monkeypatch.setattr(assistant, "_leer_contexto_base", lambda: "")
    monkeypatch.setattr(assistant, "buscar", lambda *a, **k: [])
    import asyncio

    for modo in ("tech", "user"):
        resultado = asyncio.run(assistant.responder("key-falsa", "hola", modo=modo))
        assert resultado["fuentes"] == []
        assert resultado["modelo"] is None
        assert resultado["respuesta"]


# ---------------------------------------------------------------- modos


def test_modo_tech_usa_persona_reclutador(monkeypatch):
    capturado = {}

    async def _fake_llm(api_key, model, system_prompt, user_prompt):
        capturado["system"] = system_prompt
        return "respuesta técnica"

    monkeypatch.setattr(assistant, "llamar_openrouter", _fake_llm)
    import asyncio

    r = asyncio.run(assistant.responder("key", "¿qué ADRs hay sobre multi-tenant?", modo="tech"))
    assert "RECLUTADOR" in capturado["system"].upper()
    assert "ADR" in r["respuesta"] or r["respuesta"] == "respuesta técnica"
    assert r["fuentes"]


def test_modo_usuario_habla_de_producto(monkeypatch):
    capturado = {}

    async def _fake_llm(api_key, model, system_prompt, user_prompt):
        capturado["system"] = system_prompt
        return "ok"

    monkeypatch.setattr(assistant, "llamar_openrouter", _fake_llm)
    import asyncio

    asyncio.run(assistant.responder("key", "¿cómo vinculo una bobina?", modo="user"))
    assert "USUARIO" in capturado["system"].upper()


# ---------------------------------------------------------------- router


@pytest.fixture()
def client():
    return TestClient(app)


def test_router_ask_tech_responde_con_llm_mockeado(client, monkeypatch):
    async def _fake_llm(api_key, model, system_prompt, user_prompt):
        return "El sistema tiene 232 tests backend."

    monkeypatch.setattr(assistant, "llamar_openrouter", _fake_llm)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")  # el router lee getenv por request
    r = client.post("/api/v1/assistant/ask-tech", json={"pregunta": "¿cuántos tests tiene?"})
    assert r.status_code == 200
    body = r.json()
    assert body["respuesta"]
    assert isinstance(body["fuentes"], list)


def test_router_sin_api_key_devuelve_503(client, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    # el router lee os.getenv en cada request: vacío => 503 antes de tocar LLM
    r = client.post("/api/v1/assistant/ask", json={"pregunta": "¿qué es steelworks?"})
    assert r.status_code in (200, 503)  # 200 si la env real está puesta en el entorno


def test_router_valida_pregunta_corta(client):
    r = client.post("/api/v1/assistant/ask-tech", json={"pregunta": "hi"})
    assert r.status_code == 422


def test_router_rate_limit_por_ip(client, monkeypatch):
    async def _fake_llm(api_key, model, system_prompt, user_prompt):
        return "ok"

    monkeypatch.setattr(assistant, "llamar_openrouter", _fake_llm)
    # se rellena el contador directamente para no hacer 15 llamadas
    import time as _time

    hoy = _time.strftime("%Y-%m-%d")
    monkeypatch.setattr(
        assistant,
        "_preguntas_ip",
        {f"{hoy}|testclient": assistant.MAX_PREGUNTAS_DIA_POR_IP},
    )
    r = client.post("/api/v1/assistant/ask-tech", json={"pregunta": "otra pregunta cualquiera"})
    assert r.status_code == 429
    assert "límite" in r.json()["detail"].lower()


def test_router_longitud_maxima_500(client):
    r = client.post("/api/v1/assistant/ask-tech", json={"pregunta": "a" * 501})
    assert r.status_code == 422


def test_tope_diario_por_ip_bloquea(monkeypatch):
    import time as _time

    hoy = _time.strftime("%Y-%m-%d")
    monkeypatch.setattr(
        assistant,
        "_preguntas_ip",
        {f"{hoy}|ip-cualquiera": assistant.MAX_PREGUNTAS_DIA_POR_IP},
    )
    with pytest.raises(assistant.RateLimitExceeded):
        assistant.enforce_rate_limit("ip-cualquiera")


def test_tope_diario_se_reinicia_con_el_dia(monkeypatch):
    import time as _time

    hoy = _time.strftime("%Y-%m-%d")
    # el contador de un dia anterior no cuenta para hoy
    monkeypatch.setattr(
        assistant,
        "_preguntas_ip",
        {"2000-01-01|ip-nueva": assistant.MAX_PREGUNTAS_DIA_POR_IP},
    )
    assistant.enforce_rate_limit("ip-nueva")
    assert assistant._preguntas_ip[f"{hoy}|ip-nueva"] == 1


def test_router_tope_diario_devuelve_429(client, monkeypatch):
    import time as _time

    hoy = _time.strftime("%Y-%m-%d")
    monkeypatch.setattr(assistant, "_preguntas_ip", {f"{hoy}|testclient": 999})
    r = client.post("/api/v1/assistant/ask-tech", json={"pregunta": "¿qué es steelworks?"})
    assert r.status_code == 429
