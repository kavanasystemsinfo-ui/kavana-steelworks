"""Cascada puesto -> modelos del puesto -> material (lógica del legacy)."""

from app.main import app
from app.models import Workstation
from app.models.quality import ManufacturingModel, ModelWorkstationMaterial
from app.routers import quality as quality_router
from app.services.seed_planta import asegurar_asignaciones_modelo_puesto
from tests.helpers import authed_client_for, make_material, make_user


def _puesto(db, tenant, code):
    db.add(Workstation(tenant_id=tenant.id, code=code, name=code))
    db.commit()


def _modelo(db, tenant, code):
    m = ManufacturingModel(tenant_id=tenant.id, code=code, name=code)
    db.add(m)
    db.commit()
    return m


def _fijar(db, tenant, modelo, puesto, material):
    db.add(
        ModelWorkstationMaterial(
            tenant_id=tenant.id,
            manufacturing_model_id=modelo.id,
            workstation_code=puesto,
            material_id=material.id,
        )
    )
    db.commit()


def test_un_puesto_solo_devuelve_sus_modelos_con_su_material(db_session, tenant):
    _puesto(db_session, tenant, "P-1")
    _puesto(db_session, tenant, "P-2")
    m1 = _modelo(db_session, tenant, "MOD-1")
    m2 = _modelo(db_session, tenant, "MOD-2")
    a = make_material(db_session, tenant, code="MAT-A")
    b = make_material(db_session, tenant, code="MAT-B")
    _fijar(db_session, tenant, m1, "P-1", a)
    _fijar(db_session, tenant, m2, "P-2", b)
    sup = make_user(db_session, tenant, email="sup-mp@test.local", role="supervisor")

    def _gen():
        yield db_session

    app.dependency_overrides[quality_router.get_db] = _gen
    try:
        client = authed_client_for(db_session, sup)
        r1 = client.get("/api/v1/quality/workstations/P-1/models")
        r2 = client.get("/api/v1/quality/workstations/P-2/models")
        r3 = client.get("/api/v1/quality/workstations/P-9/models")
    finally:
        app.dependency_overrides.clear()
    assert [(m["code"], m["material_code"]) for m in r1.json()] == [("MOD-1", "MAT-A")]
    assert [(m["code"], m["material_code"]) for m in r2.json()] == [("MOD-2", "MAT-B")]
    assert r3.json() == []


def test_la_semilla_asigna_modelos_a_puestos_y_es_idempotente(db_session, tenant):
    _modelo(db_session, tenant, "MOD-S")
    make_material(db_session, tenant, code="MAT-S")
    recetas = [("OP-X", "Cli", "PROD", "MOD-S", "MAT-S", "1.0", "10", ["P-1", "P-2"])]
    assert asegurar_asignaciones_modelo_puesto(db_session, tenant.id, recetas) == 2
    assert asegurar_asignaciones_modelo_puesto(db_session, tenant.id, recetas) == 0
