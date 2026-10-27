"""CORS del asistente: la landing (www.kavanasystems.com) debe poder llamar a la API.

Sin esto, el widget de chat funciona por curl pero el navegador lo bloquea:
el preflight OPTIONS de un origen no permitido devuelve 400 sin cabecera
access-control-allow-origin y el JS cae en el catch genérico "no disponible".
"""

from fastapi.testclient import TestClient

from app.main import app


def test_preflight_permite_origin_landing():
    client = TestClient(app)
    r = client.options(
        "/api/v1/assistant/ask-tech",
        headers={
            "Origin": "https://www.kavanasystems.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200
    allow = r.headers.get("access-control-allow-origin")
    assert allow and "kavanasystems.com" in allow


def test_cors_incluye_landing_en_settings():
    from app.core.config import get_settings

    origins = get_settings().cors_origins
    assert "https://www.kavanasystems.com" in origins