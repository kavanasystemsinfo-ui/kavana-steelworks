"""Tests de health checks (auditoría externa 2026-08-24, hallazgo 4).

Contrato:
- /health se mantiene por compatibilidad (liveness simple, sin BD).
- /health/live: liveness puro, nunca toca la BD.
- /health/ready: readiness; verifica PostgreSQL con SELECT 1 y timeout.
  Si la BD no responde → 503 con detalle. Sin datos inventados.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


def _client():
    return TestClient(app)


def test_health_legacy_sigue_respondiendo():
    r = _client().get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_live_no_toca_bd():
    r = _client().get("/health/live")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "db" not in body


def test_health_ready_con_bd_ok():
    """Requiere una BD real accesible via STEELWORKS_DATABASE_URL (o default).
    En CI unitario puro (solo sqlite de tests) se salta: readiness sin BD
    real no aporta nada."""

    try:
        from app.routers.health import _check_db

        _check_db()
    except Exception:
        pytest.skip("Sin PostgreSQL disponible para el check de readiness")
    r = _client().get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["database"] == "ok"


def test_health_ready_sin_bd_devuelve_503(monkeypatch):
    from app.routers import health as health_router

    def _romper():
        raise Exception("conexion rechazada (simulada)")

    monkeypatch.setattr(health_router, "_check_db", _romper)
    r = _client().get("/health/ready")
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["status"] == "unavailable"
    assert "database" in detail
