"""E2E de administración multi-tenant contra PostgreSQL real (spec 07).

Valida el flujo completo: seed demo -> login admin -> tenant GET/PUT ->
users CRUD -> workstations CRUD -> sequences config + next -> roles ->
CONCURRENCIA de secuencias (SELECT FOR UPDATE, el pitfall de la fase).

Se ejecuta con:  uv run python e2e_admin.py
"""

import os
import subprocess
import threading
from datetime import datetime

from fastapi.testclient import TestClient

# Password del contenedor en runtime (nunca literal, quirk de credenciales)
def _pg_password() -> str:
    out = subprocess.check_output(
        [
            "docker",
            "inspect",
            "kavana-busroad-pg-test",
            "--format",
            "{{range .Config.Env}}{{println .}}{{end}}",
        ],
        text=True,
    )
    for linea in out.splitlines():
        if linea.startswith("POSTGRES_PASSWORD="):
            return linea.split("=", 1)[1].strip()
    raise RuntimeError("POSTGRES_PASSWORD no encontrada")


os.environ["STEELWORKS_DATABASE_URL"] = (
    f"postgresql+psycopg://kavana:{_pg_password()}@localhost:5436/kavana_steelworks"
)

from app.core.database import Base, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.services.seed_demo import seed_demo  # noqa: E402
from app.services.auth import login  # noqa: E402
from app.services.sequences import next_sequence  # noqa: E402
from sqlalchemy import text  # noqa: E402


def preparar_bd() -> None:
    """Recrea la BD de E2E con el esquema completo vía create_all + seed."""
    db = SessionLocal()
    try:
        Base.metadata.drop_all(bind=db.get_bind())
        Base.metadata.create_all(bind=db.get_bind())
        db.commit()
        resumen = seed_demo(db)
        print(f"[1] Seed demo OK (created={resumen['created']})")
    finally:
        db.close()


def test_flujo_admin() -> None:
    """Login admin + recorrido de endpoints admin."""
    client = TestClient(app)

    # login del admin demo (password kavana, spec 07)
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@demo.local", "password": "kavana"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("[2] Login admin OK")

    # tenant GET
    r = client.get("/api/v1/admin/tenant", headers=headers)
    assert r.status_code == 200, r.text
    tenant = r.json()
    assert tenant["slug"] == "demo"
    assert tenant["status"] == "active"
    print("[3] Tenant GET OK (slug=demo)")

    # tenant PUT (config parcial)
    r = client.put(
        "/api/v1/admin/tenant",
        headers=headers,
        json={"theme": {"colors": {"primary": "#123456"}}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["theme"]["colors"]["primary"] == "#123456"
    print("[4] Tenant PUT OK")

    # sequences GET (defaults del seed: OP-{MM}{YY}- / LT-{DD}{MM}{YY}-)
    r = client.get("/api/v1/admin/sequences", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["order"]["prefix"] == "OP-{MM}{YY}-"
    print("[5] Sequences GET OK")

    # sequences PUT + next (peek)
    r = client.put(
        "/api/v1/admin/sequences",
        headers=headers,
        json={
            "order": {"prefix": "OP-{MM}{YY}-", "padding": 4},
            "lot": {"prefix": "LT-", "padding": 3},
        },
    )
    assert r.status_code == 200, r.text
    r = client.get("/api/v1/admin/sequences/next/order", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["next"].endswith("0001"), r.json()
    print("[6] Sequences PUT + next OK")

    # workstations CRUD
    r = client.post(
        "/api/v1/admin/workstations",
        headers=headers,
        json={"code": "linea-99", "name": "Línea 99", "hourly_cost": 50},
    )
    assert r.status_code == 201, r.text
    ws_id = r.json()["id"]
    assert r.json()["code"] == "LINEA-99"
    r = client.get("/api/v1/admin/workstations", headers=headers)
    assert r.status_code == 200, r.text
    codes = {w["code"] for w in r.json()}
    assert "LINEA-1" in codes and "LINEA-99" in codes
    print("[7] Workstations create+list OK")

    # users CRUD + login del nuevo usuario
    r = client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": "jefe@demo.local",
            "name": "Jefe Demo",
            "password": "clave123",
            "role": "supervisor",
            "default_workstation_code": "LINEA-1",
        },
    )
    assert r.status_code == 201, r.text
    nuevo_id = r.json()["id"]
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "jefe@demo.local", "password": "clave123"},
    )
    assert r.status_code == 200, r.text
    print("[8] Users create + login OK")

    # roles GET (el seed crea los 4 roles del sistema)
    r = client.get("/api/v1/admin/roles", headers=headers)
    assert r.status_code == 200, r.text
    roles = {x["role_key"] for x in r.json()}
    assert {"operator", "materials", "supervisor", "admin"} <= roles
    print("[9] Roles GET OK (4 roles del sistema)")

    # rol custom: crear directamente + editar permisos
    from app.models import TenantRole
    from app.models.admin import PERMISOS_CATALOGO

    db = SessionLocal()
    try:
        tenant_id = tenant["id"]
        from uuid import UUID

        db.add(
            TenantRole(
                tenant_id=UUID(tenant_id),
                role_key="jefe_turno",
                name="Jefe de Turno",
                permissions=["stock.scan"],
                is_system=False,
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.put(
        "/api/v1/admin/roles/jefe_turno",
        headers=headers,
        json={"permissions": ["stock.scan", "stock.link"], "name": "Jefe Turno"},
    )
    assert r.status_code == 200, r.text
    assert set(r.json()["permissions"]) == {"stock.scan", "stock.link"}
    print("[10] Role custom PUT OK")

    # rol del sistema bloqueado
    r = client.put(
        "/api/v1/admin/roles/operator",
        headers=headers,
        json={"permissions": ["admin.users"]},
    )
    assert r.status_code == 400, r.text
    print("[11] Role sistema bloqueado OK")

    # no-admin bloqueado: login operario da 403 en /admin
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "operario@demo.local", "password": "kavana"},
    )
    assert r.status_code == 200, r.text
    r = client.get(
        "/api/v1/admin/tenant",
        headers={"Authorization": f"Bearer {r.json()['access_token']}"},
    )
    assert r.status_code == 403, r.text
    print("[12] No-admin 403 OK")


def test_concurrencia_secuencias() -> None:
    """10 hilos piden next_sequence a la vez: nunca se repite un número.

    El SELECT FOR UPDATE serializa en PostgreSQL; si la implementación
    fallara (dos lecturas del mismo next_number), habría duplicados.
    """
    db = SessionLocal()
    try:
        from app.models import Tenant
        from sqlalchemy import select

        tenant = db.scalar(select(Tenant).where(Tenant.slug == "demo"))
        assert tenant is not None
        tenant_id = tenant.id

        resultados: list[str] = []
        errores: list[Exception] = []

        def worker():
            try:
                s = SessionLocal()
                try:
                    num = next_sequence(s, tenant_id, "order")
                    resultados.append(num)
                finally:
                    s.close()
            except Exception as exc:  # pragma: no cover
                errores.append(exc)

        hilos = [threading.Thread(target=worker) for _ in range(10)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        assert not errores, f"Errores en hilos: {errores}"
        assert len(resultados) == 10, f"Faltan resultados: {len(resultados)}"
        assert len(set(resultados)) == 10, f"Duplicados en secuencias: {resultados}"
        # Los 10 deben tener el mismo prefix y numeración consecutiva
        numeros = sorted(int(r.rsplit("-", 1)[1]) for r in resultados)
        assert numeros == list(range(numeros[0], numeros[0] + 10)), numeros
        print(f"[13] Concurrencia secuencias OK: {len(set(resultados))} números únicos")
    finally:
        db.close()


if __name__ == "__main__":
    t0 = datetime.now()
    preparar_bd()
    test_flujo_admin()
    test_concurrencia_secuencias()
    print(f"\nE2E ADMIN COMPLETO ({datetime.now() - t0})")