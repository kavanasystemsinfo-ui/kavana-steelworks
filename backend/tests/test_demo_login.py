"""Tests para demo-login (Fase 2 - entrada sin credenciales a la demo)."""

import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.models import Tenant, User
from app.services.auth import hash_password
from app.routers import auth as auth_router
from app.core.database import Base


def _make_demo_tenant(db):
    """Crea el tenant demo con usuarios por rol (idempotente)."""
    existing = db.query(Tenant).filter(Tenant.slug == "demo").first()
    if existing:
        return existing

    t = Tenant(
        name="Demo Aceros",
        slug="demo",
        status="active",
        is_active=True,
        auth={"login_method": "username_password", "require_line_number": True},
        theme={"colors": {"primary": "#e56b2e"}},
        finances={},
        sequences_config={},
    )
    db.add(t)
    db.commit()
    db.refresh(t)

    # Usuarios demo por rol
    roles = [
        ("operario@demo.local", "Operario Demo", "operator"),
        ("supervisor@demo.local", "Supervisor Demo", "supervisor"),
        ("materias@demo.local", "Materias Primas Demo", "materials"),
        ("admin@demo.local", "Admin Demo", "admin"),
    ]
    for email, name, role in roles:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                tenant_id=t.id,
                email=email,
                name=name,
                password_hash=hash_password("kavana"),
                role=role,
            )
            db.add(user)
    db.commit()
    return t


def _override_auth_db(db):
    """Override del get_db del router de auth para usar la sesión de test."""
    def _gen():
        try:
            yield db
        finally:
            pass
    app.dependency_overrides[auth_router.get_db] = _gen


def _cleanup_overrides():
    app.dependency_overrides.clear()


def test_demo_login_disabled_returns_404(db_session):
    """Si DEMO_LOGIN_ENABLED no es 'true', demo-login devuelve 404."""
    os.environ["DEMO_LOGIN_ENABLED"] = "false"
    _make_demo_tenant(db_session)
    _override_auth_db(db_session)

    client = TestClient(app)
    response = client.post("/api/v1/auth/demo-login", json={"role": "operator"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"
    _cleanup_overrides()


def test_demo_login_valid_role_returns_session(db_session):
    """Rol válido devuelve sesión del tenant demo."""
    os.environ["DEMO_LOGIN_ENABLED"] = "true"
    demo_tenant = _make_demo_tenant(db_session)
    _override_auth_db(db_session)

    client = TestClient(app)
    response = client.post("/api/v1/auth/demo-login", json={"role": "operator"})

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Verificar que el token pertenece al tenant demo
    from app.services.auth import verify_token
    payload = verify_token(data["access_token"])
    assert payload is not None
    assert payload["tenant_id"] == str(demo_tenant.id)
    assert payload["demo"] is True  # Marca demo en el token
    _cleanup_overrides()


def test_demo_login_invalid_role_returns_400(db_session):
    """Rol no permitido devuelve 400."""
    os.environ["DEMO_LOGIN_ENABLED"] = "true"
    _make_demo_tenant(db_session)
    _override_auth_db(db_session)

    client = TestClient(app)
    response = client.post("/api/v1/auth/demo-login", json={"role": "superadmin"})

    assert response.status_code == 400
    assert "Rol no permitido" in response.json()["detail"]
    _cleanup_overrides()


def test_demo_login_rate_limit_works(db_session):
    """Límite de 20 req/min por IP funciona."""
    os.environ["DEMO_LOGIN_ENABLED"] = "true"
    _make_demo_tenant(db_session)
    _override_auth_db(db_session)

    client = TestClient(app)
    headers = {"X-Forwarded-For": "192.168.1.100"}

    # 20 requests OK
    for i in range(20):
        response = client.post(
            "/api/v1/auth/demo-login",
            json={"role": "operator"},
            headers=headers
        )
        assert response.status_code == 200, f"Request {i+1} failed: {response.text}"

    # 21st request → 429
    response = client.post(
        "/api/v1/auth/demo-login",
        json={"role": "operator"},
        headers=headers
    )
    assert response.status_code == 429
    assert "Demasiados intentos" in response.json()["detail"]
    _cleanup_overrides()


def test_demo_login_never_returns_non_demo_tenant(db_session):
    """demo-login nunca devuelve sesión de un tenant que no sea el demo."""
    os.environ["DEMO_LOGIN_ENABLED"] = "true"
    demo_tenant = _make_demo_tenant(db_session)
    _override_auth_db(db_session)

    # Crear otro tenant (empresa real)
    real_tenant = Tenant(
        name="Empresa Real",
        slug="empresa-real",
        status="active",
        is_active=True,
        auth={"login_method": "username_password"},
        theme={},
        finances={},
        sequences_config={},
    )
    db_session.add(real_tenant)
    db_session.commit()
    db_session.refresh(real_tenant)

    client = TestClient(app)
    response = client.post("/api/v1/auth/demo-login", json={"role": "operator"})

    assert response.status_code == 200
    from app.services.auth import verify_token
    payload = verify_token(response.json()["access_token"])
    assert payload["tenant_id"] == str(demo_tenant.id)
    assert payload["tenant_id"] != str(real_tenant.id)
    _cleanup_overrides()


def test_demo_login_unknown_role_user_not_found(db_session):
    """Si no existe usuario demo para el rol, devuelve 400."""
    os.environ["DEMO_LOGIN_ENABLED"] = "true"
    # Tenant demo SIN usuarios
    t = Tenant(
        name="Demo Aceros",
        slug="demo",
        status="active",
        is_active=True,
        auth={}, theme={}, finances={}, sequences_config={},
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    _override_auth_db(db_session)

    client = TestClient(app)
    response = client.post("/api/v1/auth/demo-login", json={"role": "operator"})

    assert response.status_code == 400
    assert "Usuario demo no encontrado" in response.json()["detail"]
    _cleanup_overrides()


def test_demo_login_tenant_not_configured_returns_400(db_session):
    """Si no hay tenant demo, devuelve 400."""
    os.environ["DEMO_LOGIN_ENABLED"] = "true"
    # No crear tenant demo
    _override_auth_db(db_session)

    client = TestClient(app)
    response = client.post("/api/v1/auth/demo-login", json={"role": "operator"})

    assert response.status_code == 400
    assert "Tenant demo no configurado" in response.json()["detail"]
    _cleanup_overrides()