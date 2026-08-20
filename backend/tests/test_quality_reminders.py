"""Recordatorios de autocontrol — endpoint de estado (spec 04 §3.2.5).

El backend NO impone cadencia (regla de la spec: los recordatorios son
puramente de UI). Solo expone el estado que el frontend necesita para
calcular los 15 min del primer aviso y el ciclo de 2 h:

    GET /api/v1/quality/reminder-state
    → { shift_started_at: ISO | null, last_check_at: ISO | null }

- shift_started_at: login_time del UserShift ACTIVO del operario (null
  si no tiene turno abierto).
- last_check_at: created_at del último QualityRecord del operario
  (null si nunca ha registrado un autocontrol).
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models import ManufacturingModel, QualityRecord, UserShift
from app.routers import quality as quality_router
from tests.helpers import (
    authed_client_for,
    make_order,
    make_order_line,
    make_tenant,
    make_user,
)


def _make_model(db, tenant, code="PERFIL-REM-001"):
    """Crea una plantilla mínima (sin plan de controles)."""
    modelo = ManufacturingModel(
        tenant_id=tenant.id,
        code=code,
        name=f"Modelo {code}",
        is_active=True,
    )
    db.add(modelo)
    db.commit()
    db.refresh(modelo)
    return modelo


def _override_get_db(db_session):
    def _gen():
        yield db_session

    return _gen


def _cliente(db, user):
    app.dependency_overrides[quality_router.get_db] = _override_get_db(db)
    return authed_client_for(db, user)


def _crear_registro(db, tenant, operario, order, model, workstation="LINEA-1"):
    """Crea un QualityRecord mínimo válido (sin measurements)."""
    rec = QualityRecord(
        tenant_id=tenant.id,
        order_id=order.id,
        workstation_id=workstation,
        operator_id=operario.id,
        manufacturing_model_id=model.id,
        overall_status="approved",
        notes="test recordatorios",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def test_requiere_token(db_session):
    client = TestClient(app)
    res = client.get("/api/v1/quality/reminder-state")
    assert res.status_code == 401


def test_requiere_rol_operator(db_session):
    tenant = make_tenant(db_session)
    supervisor = make_user(db_session, tenant, email="sup-rem@test.local", role="supervisor")
    client = _cliente(db_session, supervisor)
    res = client.get("/api/v1/quality/reminder-state")
    assert res.status_code == 403


def test_sin_controles_devuelve_last_check_null(db_session):
    tenant = make_tenant(db_session)
    operario = make_user(db_session, tenant, email="op-rem-1@test.local")
    client = _cliente(db_session, operario)
    res = client.get("/api/v1/quality/reminder-state")
    assert res.status_code == 200
    data = res.json()
    assert "shift_started_at" in data
    assert "last_check_at" in data
    assert data["last_check_at"] is None


def test_con_turno_activo_devuelve_shift_started_at(db_session):
    tenant = make_tenant(db_session)
    operario = make_user(db_session, tenant, email="op-rem-2@test.local")
    ahora = datetime.now(UTC)
    db_session.add(
        UserShift(
            tenant_id=tenant.id,
            operator_id=operario.id,
            login_time=ahora - timedelta(minutes=10),
            status="active",
        )
    )
    db_session.commit()
    client = _cliente(db_session, operario)
    res = client.get("/api/v1/quality/reminder-state")
    assert res.status_code == 200
    data = res.json()
    assert data["shift_started_at"] is not None


def test_con_autocontrol_devuelve_last_check_at(db_session):
    tenant = make_tenant(db_session)
    operario = make_user(db_session, tenant, email="op-rem-3@test.local")
    orden = make_order(db_session, tenant, numero="OP-REM-001")
    make_order_line(db_session, orden, workstation="LINEA-1")
    modelo = _make_model(db_session, tenant, code="PERFIL-REM-001")

    _crear_registro(db_session, tenant, operario, orden, modelo)

    client = _cliente(db_session, operario)
    res = client.get("/api/v1/quality/reminder-state")
    assert res.status_code == 200
    data = res.json()
    assert data["last_check_at"] is not None
