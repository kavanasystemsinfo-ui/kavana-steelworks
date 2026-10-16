"""Tests TDD del cierre de jornada y los turnos A/B/C (Fase 1).

Contrato closeShift (spec 02 §3.11 portado al v2):
- POST /api/v1/auth/close-shift: 404 si no hay turno activo (el segundo
  cierre también devuelve 404).
- total_hours = horas de reloj del turno; si superan 14 h se cierra a 8.0
  (tope legacy). Hoy el campo existe pero nunca se escribía.
- status = completed, logout_time = now.
- Turno A/B/C derivado del login_time en horario de planta (America/Bogota,
  UTC-05:00): A 06-14, B 14-22, C 22-06 (spec 02: "derivación horaria del
  timestamp", el legacy lo declaraba y nunca lo poblaba).
- El login con turno huérfano también calcula total_hours del turno
  anterior (antes solo cerraba status/logout_time).
"""

from datetime import UTC, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import UserShift
from app.routers import auth as auth_router
from tests.helpers import authed_client_for

TZ_PLANTA_TEST = timezone(timedelta(hours=-5))


def _override_get_db(db_session):
    def _gen():
        yield db_session

    return _gen


def _cliente(db, user):
    """TestClient con token real (el login crea el turno activo)."""
    app.dependency_overrides[auth_router.get_db] = _override_get_db(db)
    return authed_client_for(db, user)


def _turno_activo(db, user):
    return db.scalar(
        select(UserShift).where(
            UserShift.operator_id == user.id,
            UserShift.status == "active",
        )
    )


def test_turno_desde_deriva_por_horario_de_planta():
    from zoneinfo import ZoneInfo

    from app.services.shifts import turno_desde

    bog = ZoneInfo("America/Bogota")
    assert turno_desde(datetime(2026, 10, 16, 6, 0, tzinfo=bog)) == "A"
    assert turno_desde(datetime(2026, 10, 16, 13, 59, tzinfo=bog)) == "A"
    assert turno_desde(datetime(2026, 10, 16, 14, 0, tzinfo=bog)) == "B"
    assert turno_desde(datetime(2026, 10, 16, 21, 59, tzinfo=bog)) == "B"
    assert turno_desde(datetime(2026, 10, 16, 22, 0, tzinfo=bog)) == "C"
    assert turno_desde(datetime(2026, 10, 16, 5, 59, tzinfo=bog)) == "C"
    # Un timestamp UTC se convierte al horario de planta (06:00 local = 11:00 UTC)
    assert turno_desde(datetime(2026, 10, 16, 11, 0, tzinfo=UTC)) == "A"
    # Naive se trata como UTC
    assert turno_desde(datetime(2026, 10, 16, 4, 0)) == "C"


def test_close_shift_sin_turno_activo_devuelve_404(db_session, tenant, user):
    cliente = _cliente(db_session, user)
    turno = _turno_activo(db_session, user)
    turno.status = "completed"
    db_session.commit()

    r = cliente.post("/api/v1/auth/close-shift")

    assert r.status_code == 404
    assert "turno" in r.json()["detail"].lower()


def test_close_shift_calcula_horas_y_completa_el_turno(db_session, tenant, user):
    cliente = _cliente(db_session, user)
    turno = _turno_activo(db_session, user)
    turno.login_time = datetime.now(UTC) - timedelta(hours=3, minutes=30)
    db_session.commit()

    r = cliente.post("/api/v1/auth/close-shift")

    assert r.status_code == 200
    data = r.json()
    assert abs(data["total_hours"] - 3.5) < 0.05
    assert data["status"] == "completed"
    assert data["turno"] in ("A", "B", "C")

    db_session.refresh(turno)
    assert turno.status == "completed"
    assert turno.logout_time is not None
    assert abs(float(turno.total_hours) - 3.5) < 0.05


def test_close_shift_cap_mayor_14h_a_8_horas(db_session, tenant, user):
    cliente = _cliente(db_session, user)
    turno = _turno_activo(db_session, user)
    turno.login_time = datetime.now(UTC) - timedelta(hours=20)
    db_session.commit()

    r = cliente.post("/api/v1/auth/close-shift")

    assert r.status_code == 200
    assert r.json()["total_hours"] == 8.0


def test_close_shift_segunda_vez_devuelve_404(db_session, tenant, user):
    cliente = _cliente(db_session, user)

    assert cliente.post("/api/v1/auth/close-shift").status_code == 200
    assert cliente.post("/api/v1/auth/close-shift").status_code == 404


def test_close_shift_requiere_token(db_session):
    app.dependency_overrides[auth_router.get_db] = _override_get_db(db_session)

    r = TestClient(app).post("/api/v1/auth/close-shift")

    assert r.status_code == 401


def test_login_huerfano_calcula_total_hours_del_turno_anterior(db_session, tenant, user):
    from app.services.auth import login

    _cliente(db_session, user)  # crea el turno activo con login real
    turno = _turno_activo(db_session, user)
    turno.login_time = datetime.now(UTC) - timedelta(hours=2)
    db_session.commit()

    login(db_session, tenant.id, user.email, "kavana")

    db_session.refresh(turno)
    assert turno.status == "completed"
    assert turno.logout_time is not None
    assert abs(float(turno.total_hours) - 2.0) < 0.05
    nuevo = _turno_activo(db_session, user)
    assert nuevo is not None
    assert nuevo.id != turno.id
