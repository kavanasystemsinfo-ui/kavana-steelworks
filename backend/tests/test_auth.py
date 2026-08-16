"""Tests TDD del servicio de autenticación (spec 05, sección 2.4/2.5).

Contrato:
- Login: devuelve JWT con expiración de 8 horas (un turno estándar).
- Logout: revoca el token server-side (lista negra RevokedToken).
- Verificación: un token revocado no pasa; uno válido sí.
- Turno: un operario tiene un solo turno activo a la vez.
"""

from datetime import UTC, datetime

import pytest

from app.models import RevokedToken, User, UserShift
from tests.helpers import make_material  # noqa: F401 (no usado, solo convención)


def _make_user(db, tenant, email="operario@test.local", password="clave123"):
    from app.services.auth import hash_password

    u = User(
        tenant_id=tenant.id,
        email=email,
        name="Operario Test",
        password_hash=hash_password(password),
        role="operator",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_login_devuelve_token_de_8_horas(db_session, tenant):
    from app.services.auth import login, verify_token

    _make_user(db_session, tenant)
    token = login(db_session, tenant.id, "operario@test.local", "clave123")
    assert token is not None

    payload = verify_token(token)
    assert payload is not None
    assert payload["tenant_id"] == str(tenant.id)

    exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
    ahora = datetime.now(UTC)
    horas = (exp - ahora).total_seconds() / 3600
    assert 7.5 <= horas <= 8.5  # ~8 horas = un turno


def test_login_con_password_incorrecto_falla(db_session, tenant):
    from app.services.auth import login

    _make_user(db_session, tenant)
    with pytest.raises(ValueError, match="[Cc]redenciales"):
        login(db_session, tenant.id, "operario@test.local", "incorrecta")


def test_logout_revoca_token_y_verificacion_lo_rechaza(db_session, tenant):
    from app.services.auth import is_revoked, login, logout, verify_token

    _make_user(db_session, tenant)
    token = login(db_session, tenant.id, "operario@test.local", "clave123")

    logout(db_session, token)

    revocados = db_session.query(RevokedToken).count()
    assert revocados == 1
    # Firma válida pero revocado → el middleware lo rechaza (is_revoked)
    assert verify_token(token) is not None
    assert is_revoked(db_session, token) is True


def test_operario_tiene_un_solo_turno_activo(db_session, tenant):
    from app.services.auth import login

    _make_user(db_session, tenant)
    login(db_session, tenant.id, "operario@test.local", "clave123")

    turnos_activos = db_session.query(UserShift).filter(UserShift.status == "active").count()
    assert turnos_activos == 1


def test_logout_es_idempotente(db_session, tenant):
    from app.services.auth import login, logout

    _make_user(db_session, tenant)
    token = login(db_session, tenant.id, "operario@test.local", "clave123")

    logout(db_session, token)
    # Un segundo logout del mismo token no debe lanzar IntegrityError (unique)
    logout(db_session, token)

    assert db_session.query(RevokedToken).count() == 1
