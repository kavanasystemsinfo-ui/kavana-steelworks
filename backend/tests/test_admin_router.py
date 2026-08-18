"""Tests del router de Administración multi-tenant (spec 07, ADR-015).

Patrones del proyecto: TestClient + dependency_overrides del get_db del
router + JWT real a través de helpers.auth_headers_for. El rol admin del
JWT se valida en require_roles (capa de seguridad).
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import TenantRole
from app.routers import admin as admin_router
from app.services.auth import verify_password
from app.services.sequences import next_sequence
from tests.helpers import auth_headers_for, make_tenant, make_user


def _override_get_db(db_session):
    def _gen():
        yield db_session

    return _gen


@pytest.fixture()
def admin_user(db_session, tenant):
    return make_user(db_session, tenant, email="admin@test.local", role="admin")


def _client(db, user):
    app.dependency_overrides[admin_router.get_db] = _override_get_db(db)
    return TestClient(app)


def _do(db, user, method, path, **kwargs):
    client = _client(db, user)
    client.headers.update(auth_headers_for(db, user))
    try:
        return getattr(client, method)(path, **kwargs)
    finally:
        app.dependency_overrides.clear()


# ── Tenant ──────────────────────────────────────────────────────────────────


def test_get_tenant_denegado_sin_admin(db_session, tenant, user):
    """El endpoint exige rol admin: un operario recibe 403."""
    r = _do(db_session, user, "get", "/api/v1/admin/tenant")
    assert r.status_code == 403, r.text


def test_get_tenant_devuelve_config(db_session, tenant, admin_user):
    r = _do(db_session, admin_user, "get", "/api/v1/admin/tenant")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Aceros Test"
    assert body["slug"] == "aceros-test"
    assert body["status"] == "active"
    assert body["id"] == str(tenant.id)


def test_update_tenant_cambia_campos_permitidos(db_session, tenant, admin_user):
    r = _do(
        db_session,
        admin_user,
        "put",
        "/api/v1/admin/tenant",
        json={
            "name": "Aceros Renovado",
            "status": "trial",
            "theme": {"colors": {"primary": "#ff0000"}},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Aceros Renovado"
    assert body["status"] == "trial"
    assert body["theme"]["colors"]["primary"] == "#ff0000"


def test_update_tenant_slug_unico_global(db_session, tenant, admin_user):
    """El slug es único global: si otro tenant lo usa → 409."""
    otro = make_tenant(db_session, name="Otra Empresa", slug="otra-empresa")
    r = _do(
        db_session,
        admin_user,
        "put",
        "/api/v1/admin/tenant",
        json={"slug": otro.slug},
    )
    assert r.status_code == 409, r.text


def test_update_tenant_rechaza_campos_no_editables(db_session, tenant, admin_user):
    r = _do(
        db_session,
        admin_user,
        "put",
        "/api/v1/admin/tenant",
        json={"sequences_config": {"order": {"prefix": "X-"}}},
    )
    assert r.status_code == 400, r.text


# ── Users ───────────────────────────────────────────────────────────────────


def test_list_users_solo_del_tenant(db_session, tenant, admin_user):
    make_user(db_session, tenant, email="pepe@test.local", role="operator")
    otro_tenant = make_tenant(db_session, name="Otro", slug="otro-tenant")
    make_user(db_session, otro_tenant, email="ajeno@test.local", role="operator")

    r = _do(db_session, admin_user, "get", "/api/v1/admin/users")
    assert r.status_code == 200, r.text
    mails = [u["email"] for u in r.json()]
    assert "admin@test.local" in mails
    assert "pepe@test.local" in mails
    assert "ajeno@test.local" not in mails


def test_create_user_y_login_funciona(db_session, tenant, admin_user):
    r = _do(
        db_session,
        admin_user,
        "post",
        "/api/v1/admin/users",
        json={
            "email": "nuevo@test.local",
            "name": "Nuevo",
            "password": "secreto1",
            "role": "supervisor",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["role"] == "supervisor"
    assert body["is_active"] is True


def test_create_user_email_duplicado_409(db_session, tenant, admin_user):
    make_user(db_session, tenant, email="dupe@test.local", role="operator")
    r = _do(
        db_session,
        admin_user,
        "post",
        "/api/v1/admin/users",
        json={
            "email": "dupe@test.local",
            "name": "Duplicado",
            "password": "secreto1",
            "role": "operator",
        },
    )
    assert r.status_code == 409, r.text


def test_create_user_valida_puesto_existente(db_session, tenant, admin_user):
    r = _do(
        db_session,
        admin_user,
        "post",
        "/api/v1/admin/users",
        json={
            "email": "con-puesto@test.local",
            "name": "Con Puesto",
            "password": "secreto1",
            "role": "operator",
            "default_workstation_code": "LINEA-INEXISTENTE",
        },
    )
    assert r.status_code == 400, r.text


def test_patch_user_cambia_password(db_session, tenant, admin_user, user):
    r = _do(
        db_session,
        admin_user,
        "patch",
        f"/api/v1/admin/users/{user.id}",
        json={"password": "nueva-pass"},
    )
    assert r.status_code == 200, r.text
    db_session.refresh(user)
    assert verify_password("nueva-pass", user.password_hash)


def test_no_puedes_desactivar_tu_propio_usuario(db_session, tenant, admin_user):
    r = _do(
        db_session,
        admin_user,
        "delete",
        f"/api/v1/admin/users/{admin_user.id}",
    )
    assert r.status_code == 400, r.text


def test_delete_user_soft_desactiva(db_session, tenant, admin_user):
    victima = make_user(db_session, tenant, email="victima@test.local", role="operator")
    r = _do(db_session, admin_user, "delete", f"/api/v1/admin/users/{victima.id}")
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False
    db_session.refresh(victima)
    assert victima.is_active is False


# ── Sequences ───────────────────────────────────────────────────────────────


def test_get_sequences_devuelve_defaults_si_no_hay_config(db_session, tenant, admin_user):
    r = _do(db_session, admin_user, "get", "/api/v1/admin/sequences")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["order"]["prefix"] == "OP-{MM}{YY}-"
    assert body["order"]["padding"] == 3
    assert body["lot"]["padding"] == 3


def test_update_sequences_y_next_peek_no_consume(db_session, tenant, admin_user):
    r = _do(
        db_session,
        admin_user,
        "put",
        "/api/v1/admin/sequences",
        json={
            "order": {"prefix": "OP-{MM}{YY}-", "padding": 4},
            "lot": {"prefix": "LT-", "padding": 3},
        },
    )
    assert r.status_code == 200, r.text

    # peek antes de consumir: devuelve 0001 sin crear fila
    r = _do(db_session, admin_user, "get", "/api/v1/admin/sequences/next/order")
    assert r.status_code == 200, r.text
    assert r.json()["next"].endswith("0001")

    # consumimos una vez: la siguiente llamada al servicio devuelve 0002
    numero = next_sequence(db_session, tenant.id, "order")
    assert numero.endswith("0001")

    r = _do(db_session, admin_user, "get", "/api/v1/admin/sequences/next/order")
    assert r.status_code == 200, r.text
    assert r.json()["next"].endswith("0002")


def test_next_sequence_tipo_invalido_400(db_session, tenant, admin_user):
    r = _do(db_session, admin_user, "get", "/api/v1/admin/sequences/next/factura")
    assert r.status_code == 400, r.text


# ── Workstations ────────────────────────────────────────────────────────────


def test_create_workstation_y_listar(db_session, tenant, admin_user):
    r = _do(
        db_session,
        admin_user,
        "post",
        "/api/v1/admin/workstations",
        json={
            "code": "linea-9",
            "name": "Línea 9",
            "registration_method": "quantity",
            "hourly_cost": 40,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["code"] == "LINEA-9"  # se normaliza a mayúsculas

    r = _do(db_session, admin_user, "get", "/api/v1/admin/workstations")
    assert r.status_code == 200, r.text
    assert any(w["code"] == "LINEA-9" for w in r.json())


def test_create_workstation_codigo_duplicado_409(db_session, tenant, admin_user):
    _do(
        db_session,
        admin_user,
        "post",
        "/api/v1/admin/workstations",
        json={"code": "LINEA-1", "name": "Línea 1"},
    )
    r = _do(
        db_session,
        admin_user,
        "post",
        "/api/v1/admin/workstations",
        json={"code": "LINEA-1", "name": "Línea 1 duplicada"},
    )
    assert r.status_code == 409, r.text


def test_patch_workstation_y_delete_soft(db_session, tenant, admin_user):
    creado = _do(
        db_session,
        admin_user,
        "post",
        "/api/v1/admin/workstations",
        json={"code": "LINEA-7", "name": "Línea 7"},
    ).json()

    r = _do(
        db_session,
        admin_user,
        "patch",
        f"/api/v1/admin/workstations/{creado['id']}",
        json={"hourly_cost": 55, "is_active": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["hourly_cost"] == 55
    assert r.json()["is_active"] is False

    r = _do(db_session, admin_user, "delete", f"/api/v1/admin/workstations/{creado['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False


def test_workstation_con_grupo_invalido_400(db_session, tenant, admin_user):
    r = _do(
        db_session,
        admin_user,
        "post",
        "/api/v1/admin/workstations",
        json={"code": "LINEA-X", "name": "Línea X", "group_id": str(uuid.uuid4())},
    )
    assert r.status_code == 400, r.text


# ── Roles ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def roles_tenant(db_session, tenant):
    """Siembra los roles del sistema (el seed demo los crea en despliegues)."""
    from app.models.admin import PERMISOS_ADMIN, PERMISOS_CATALOGO

    roles = [
        ("operator", "Operario", [p for p in PERMISOS_CATALOGO if p.startswith("stock.")], True),
        ("supervisor", "Supervisor", [p for p in PERMISOS_CATALOGO if p.startswith("oee.")], True),
        ("admin", "Admin", PERMISOS_ADMIN, True),
    ]
    for key, name, perms, is_system in roles:
        db_session.add(
            TenantRole(
                tenant_id=tenant.id,
                role_key=key,
                name=name,
                permissions=perms,
                is_system=is_system,
            )
        )
    db_session.commit()
    return tenant


def test_list_roles_incluye_permisos(db_session, tenant, admin_user, roles_tenant):
    r = _do(db_session, admin_user, "get", "/api/v1/admin/roles")
    assert r.status_code == 200, r.text
    roles = {x["role_key"]: x for x in r.json()}
    assert "admin" in roles
    assert roles["admin"]["is_system"] is True
    assert "admin.users" in roles["admin"]["permissions"]


def test_update_rol_sistema_bloqueado(db_session, tenant, admin_user, roles_tenant):
    r = _do(
        db_session,
        admin_user,
        "put",
        "/api/v1/admin/roles/operator",
        json={"permissions": ["admin.users"]},
    )
    assert r.status_code == 400, r.text


def test_update_rol_custom_permisos_validados(db_session, tenant, admin_user):
    rol = TenantRole(
        tenant_id=tenant.id,
        role_key="jefe_turno",
        name="Jefe de Turno",
        permissions=["stock.scan"],
        is_system=False,
    )
    db_session.add(rol)
    db_session.commit()

    r = _do(
        db_session,
        admin_user,
        "put",
        "/api/v1/admin/roles/jefe_turno",
        json={"permissions": ["stock.scan", "stock.link"], "name": "Jefe Turno Edición"},
    )
    assert r.status_code == 200, r.text
    assert set(r.json()["permissions"]) == {"stock.scan", "stock.link"}
    assert r.json()["name"] == "Jefe Turno Edición"


def test_update_rol_permiso_desconocido_400(db_session, tenant, admin_user):
    rol = TenantRole(
        tenant_id=tenant.id,
        role_key="custom1",
        name="Custom",
        permissions=[],
        is_system=False,
    )
    db_session.add(rol)
    db_session.commit()

    r = _do(
        db_session,
        admin_user,
        "put",
        "/api/v1/admin/roles/custom1",
        json={"permissions": ["no.existe"]},
    )
    assert r.status_code == 400, r.text


def test_update_rol_no_existe_404(db_session, tenant, admin_user):
    r = _do(
        db_session,
        admin_user,
        "put",
        "/api/v1/admin/roles/no-existe",
        json={"permissions": []},
    )
    assert r.status_code == 404, r.text
