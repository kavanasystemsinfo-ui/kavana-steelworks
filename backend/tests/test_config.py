"""Tests de configuración: fail-fast del secret JWT en producción.

El JWT secret tiene un default de desarrollo que no debe usarse en
producción: cualquiera que lo conozca podría forjar tokens. La app debe
negarse a arrancar si production no tiene un secreto fuerte.
"""

import pytest
from pydantic import ValidationError


def _limpiar_env(monkeypatch):
    for var in ("STEELWORKS_JWT_SECRET", "JWT_SECRET", "STEELWORKS_ENVIRONMENT"):
        monkeypatch.delenv(var, raising=False)


def test_produccion_con_secret_por_defecto_falla(monkeypatch):
    from app.core.config import Settings

    _limpiar_env(monkeypatch)
    with pytest.raises(ValidationError):
        Settings(environment="production")


def test_produccion_con_secret_corto_falla(monkeypatch):
    from app.core.config import Settings

    _limpiar_env(monkeypatch)
    with pytest.raises(ValidationError):
        Settings(environment="production", jwt_secret="corto")


def test_produccion_con_secret_fuerte_ok(monkeypatch):
    from app.core.config import Settings

    _limpiar_env(monkeypatch)
    s = Settings(environment="production", jwt_secret="x" * 64)
    assert s.jwt_secret == "x" * 64


def test_desarrollo_admite_secret_debil(monkeypatch):
    from app.core.config import Settings

    _limpiar_env(monkeypatch)
    s = Settings(environment="development", jwt_secret="corto")
    assert s.jwt_secret == "corto"
