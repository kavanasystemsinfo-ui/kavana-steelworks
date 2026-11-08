"""El material de una línea sale del par (modelo, puesto), como en el legacy."""

import pytest
from fastapi import HTTPException

from app.models import Workstation
from app.models.quality import ManufacturingModel, ModelWorkstationMaterial
from app.routers.orders import LineIn, _validar_lineas
from tests.helpers import make_material


def _puesto(db, tenant, code):
    db.add(Workstation(tenant_id=tenant.id, code=code, name=code))
    db.commit()


def _modelo(db, tenant):
    m = ManufacturingModel(tenant_id=tenant.id, code="MOD-1", name="Modelo 1")
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


def test_el_material_de_la_linea_sale_del_modelo_y_el_puesto(db_session, tenant):
    _puesto(db_session, tenant, "P-1")
    _puesto(db_session, tenant, "P-2")
    modelo = _modelo(db_session, tenant)
    a = make_material(db_session, tenant, code="MAT-A")
    b = make_material(db_session, tenant, code="MAT-B")
    _fijar(db_session, tenant, modelo, "P-1", a)
    _fijar(db_session, tenant, modelo, "P-2", b)
    l1 = LineIn(workstation_id="P-1", total_quantity=5, modelo_id=modelo.id)
    l2 = LineIn(workstation_id="P-2", total_quantity=5, modelo_id=modelo.id)
    _validar_lineas(db_session, tenant.id, [l1, l2])
    assert l1.material_id == a.id and l2.material_id == b.id


def test_un_material_distinto_al_del_modelo_se_rechaza(db_session, tenant):
    _puesto(db_session, tenant, "P-1")
    modelo = _modelo(db_session, tenant)
    a = make_material(db_session, tenant, code="MAT-A")
    otro = make_material(db_session, tenant, code="MAT-X")
    _fijar(db_session, tenant, modelo, "P-1", a)
    ln = LineIn(workstation_id="P-1", total_quantity=5, modelo_id=modelo.id, material_id=otro.id)
    with pytest.raises(HTTPException) as exc:
        _validar_lineas(db_session, tenant.id, [ln])
    assert exc.value.status_code == 400


def test_sin_mapeo_la_linea_conserva_su_material(db_session, tenant):
    _puesto(db_session, tenant, "P-1")
    modelo = _modelo(db_session, tenant)
    m = make_material(db_session, tenant, code="MAT-L")
    ln = LineIn(workstation_id="P-1", total_quantity=5, modelo_id=modelo.id, material_id=m.id)
    _validar_lineas(db_session, tenant.id, [ln])
    assert ln.material_id == m.id
