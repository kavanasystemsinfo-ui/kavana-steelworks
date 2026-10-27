"""Tests TDD del auto-rellenado de dimensiones en recepción (Fase 0 UX).

- GET /stock-items/materials expone dimension_ancho_mm/dimension_espesor_mm
  para que el formulario de recepción auto-rellenado ancho y espesor.
- receive_coil autocompleta width_mm/thickness_mm desde el material cuando
  no vienen explícitos (consistencia entre API y formulario).
- Los valores explícitos siempre prevalecen sobre los del material.
- Nota: los Decimal salen como string en JSON (contrato real de la API);
  los tests aceptan str o number para no acoplarse al formato exacto.
"""

from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.routers import auth as auth_router
from app.routers import stock as stock_router
from tests.helpers import auth_headers, make_material


def _override_get_db(db_session):
    def _gen():
        yield db_session

    return _gen


def _client(db_session, tenant, role="materials"):
    app.dependency_overrides[auth_router.get_db] = _override_get_db(db_session)
    app.dependency_overrides[stock_router.get_db] = _override_get_db(db_session)
    client = TestClient(app)
    client.headers.update(auth_headers(db_session, tenant, role=role))
    return client


def test_materials_endpoint_expone_dimensiones(db_session, tenant, user):
    """El listado de materiales trae ancho y espesor para auto-rellenar."""
    m = make_material(db_session, tenant, code="FLEJE-G175-12")
    m.dimension_ancho_mm = Decimal("175")
    m.dimension_espesor_mm = Decimal("1.2")
    db_session.commit()

    client = _client(db_session, tenant)
    r = client.get("/api/v1/stock-items/materials")

    assert r.status_code == 200, r.text
    por_code = {x["code"]: x for x in r.json()}
    fleje = por_code["FLEJE-G175-12"]
    assert float(fleje["dimension_ancho_mm"]) == 175.0
    assert float(fleje["dimension_espesor_mm"]) == 1.2


def test_materials_endpoint_dimensiones_ausentes_son_null(db_session, tenant, user):
    """Un material sin dimensiones definidas devuelve null, no error."""
    make_material(db_session, tenant, code="ACERO-S355")

    client = _client(db_session, tenant)
    r = client.get("/api/v1/stock-items/materials")

    assert r.status_code == 200, r.text
    por_code = {x["code"]: x for x in r.json()}
    assert por_code["ACERO-S355"]["dimension_ancho_mm"] is None
    assert por_code["ACERO-S355"]["dimension_espesor_mm"] is None


def test_receive_coil_autocompleta_dimensiones_desde_material(db_session, tenant, user):
    """Sin ancho/espesor explícitos, se toman del material (auto-rellenado)."""
    from app.services.receiving import receive_coil

    m = make_material(db_session, tenant, code="D310-15")
    m.dimension_ancho_mm = Decimal("310")
    m.dimension_espesor_mm = Decimal("1.5")
    db_session.commit()

    bobina = receive_coil(
        db_session,
        tenant.id,
        user.id,
        material_id=m.id,
        lote="L-AUTOFILL",
        peso=900,
        width_mm=None,
        thickness_mm=None,
    )

    assert bobina.width_mm == Decimal("310")
    assert bobina.thickness_mm == Decimal("1.5")


def test_receive_coil_valores_explicitos_prevalecen(db_session, tenant, user):
    """Si la etiqueta trae otras medidas, mandan las explícitas."""
    from app.services.receiving import receive_coil

    m = make_material(db_session, tenant, code="D365-20")
    m.dimension_ancho_mm = Decimal("365")
    m.dimension_espesor_mm = Decimal("2.0")
    db_session.commit()

    bobina = receive_coil(
        db_session,
        tenant.id,
        user.id,
        material_id=m.id,
        lote="L-EXPLICITA",
        peso=700,
        width_mm=200,
        thickness_mm=0.8,
    )

    assert bobina.width_mm == Decimal("200")
    assert bobina.thickness_mm == Decimal("0.8")


def test_receive_coil_sin_dimensiones_en_ninguna_parte_queda_none(db_session, tenant, user):
    """Material sin medidas y sin explícitas: se queda en null (comportamiento previo)."""
    from app.services.receiving import receive_coil

    m = make_material(db_session, tenant, code="SIN-MEDIDAS")

    bobina = receive_coil(
        db_session,
        tenant.id,
        user.id,
        material_id=m.id,
        lote="L-NONE",
        peso=100,
        width_mm=None,
        thickness_mm=None,
    )

    assert bobina.width_mm is None
    assert bobina.thickness_mm is None
