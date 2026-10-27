"""Tests de los objetivos de planta (services/objetivos.py y /supervisor/objetivos)."""

import pytest

from app.services.objetivos import OBJETIVOS_POR_DEFECTO, guardar_objetivos, objetivos_tenant
from tests.helpers import auth_headers, make_tenant


def test_sin_configurar_devuelve_los_valores_por_defecto(db_session, tenant):
    assert objetivos_tenant(tenant) == OBJETIVOS_POR_DEFECTO


def test_lo_configurado_sobrescribe_y_el_resto_queda_por_defecto(db_session, tenant):
    tenant.finances = {"overhead_hourly_cost": 30, "objetivos": {"oee": 80}}
    objetivos = objetivos_tenant(tenant)
    assert objetivos["oee"] == 80
    assert objetivos["calidad"] == OBJETIVOS_POR_DEFECTO["calidad"]


def test_guardar_conserva_el_resto_de_finances(db_session, tenant):
    tenant.finances = {"overhead_hourly_cost": 30}
    guardar_objetivos(tenant, {"chatarra_max_pct": 2.5})
    db_session.commit()
    db_session.refresh(tenant)
    assert tenant.finances["overhead_hourly_cost"] == 30
    assert tenant.finances["objetivos"] == {"chatarra_max_pct": 2.5}


@pytest.mark.parametrize("cambios", [{"oee": -1}, {"oee": 101}, {"velocidad": 50}])
def test_guardar_rechaza_valores_invalidos(db_session, tenant, cambios):
    with pytest.raises(ValueError):
        guardar_objetivos(tenant, cambios)


def test_endpoint_get_para_supervisor_y_put_solo_admin(db_session, tenant):
    from tests.test_auth_roles import _client

    supervisor = _client(
        db_session, auth_headers(db_session, tenant, role="supervisor", email="sup@test.local")
    )
    r = supervisor.get("/api/v1/supervisor/objetivos")
    assert r.status_code == 200, r.text
    assert r.json() == OBJETIVOS_POR_DEFECTO
    assert supervisor.put("/api/v1/supervisor/objetivos", json={"oee": 80}).status_code == 403

    admin = _client(
        db_session, auth_headers(db_session, tenant, role="admin", email="adm@test.local")
    )
    r = admin.put("/api/v1/supervisor/objetivos", json={"oee": 80})
    assert r.status_code == 200, r.text
    assert r.json()["oee"] == 80
    assert admin.put("/api/v1/supervisor/objetivos", json={"oee": 150}).status_code == 400

    operario = _client(db_session, auth_headers(db_session, tenant, role="operator"))
    assert operario.get("/api/v1/supervisor/objetivos").status_code == 403


def test_objetivos_aislados_por_empresa(db_session, tenant):
    from tests.test_auth_roles import _client

    otra = make_tenant(db_session, name="Otra", slug="otra")
    guardar_objetivos(otra, {"oee": 60})
    db_session.commit()

    supervisor = _client(
        db_session, auth_headers(db_session, tenant, role="supervisor", email="sup@test.local")
    )
    assert supervisor.get("/api/v1/supervisor/objetivos").json()["oee"] == 75
