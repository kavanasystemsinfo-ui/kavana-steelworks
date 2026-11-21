"""T-162: cerrar la jornada sin medir la bobina (regla de Jorge, 21-11).

- Menos de 20 kg restantes: van a merma directamente y se puede cerrar.
- 20 kg o más: el operario elige entre medir o mandar esos kg a merma.
"""

from decimal import Decimal

import pytest

from app.main import app
from app.models import MaterialConsumo, ProductionLog
from app.services.medicion import mediciones_pendientes
from tests.test_medicion import _cliente, _montada, _producir


@pytest.fixture(autouse=True)
def _limpiar_overrides():
    yield
    app.dependency_overrides.clear()


def _preparar(db, tenant, user, restantes):
    bobina, orden, linea = _montada(db, tenant, user, peso=500.0)
    cliente = _cliente(db, user)
    _producir(db, user, bobina, orden, linea, kg=500 - restantes)
    return cliente, bobina, orden, linea


def _comprobar_merma(db, bobina, linea, kg):
    db.expire_all()
    assert bobina.cantidad_disponible == 0
    assert bobina.estado == "agotado"
    assert linea.active_coil_id is None
    assert linea.scrap_material_qty == Decimal(str(kg))
    consumo = (
        db.query(MaterialConsumo).filter_by(stock_item_id=bobina.id, tipo="merma_puntas").one()
    )
    assert consumo.consumed_quantity == Decimal(str(kg))
    evento = db.query(ProductionLog).filter_by(line_id=linea.id, action="scrap").one()
    assert evento.metadata_["reason"] == "cierre_sin_medir"


def test_pendientes_informan_de_los_kg_restantes(db_session, tenant, user):
    _, bobina, _, _ = _preparar(db_session, tenant, user, 35)
    pendientes = mediciones_pendientes(db_session, tenant.id, user.id)
    assert pendientes[0]["stock_item_id"] == str(bobina.id)
    assert pendientes[0]["kg_restantes"] == 35


def test_menos_de_20_kg_van_a_merma_directamente(db_session, tenant, user):
    cliente, bobina, _, linea = _preparar(db_session, tenant, user, 19.5)
    r = cliente.post("/api/v1/auth/close-shift")
    assert r.status_code == 200, r.text
    assert r.json()["merma_sin_medir_kg"] == 19.5
    _comprobar_merma(db_session, bobina, linea, 19.5)


def test_menos_de_20_kg_tambien_al_cerrar_sesion(db_session, tenant, user):
    cliente, bobina, _, linea = _preparar(db_session, tenant, user, 5)
    assert cliente.post("/api/v1/auth/logout").status_code == 204
    _comprobar_merma(db_session, bobina, linea, 5)


@pytest.mark.parametrize("ruta", ["close-shift", "logout"])
def test_desde_20_kg_pide_elegir_y_no_toca_nada(db_session, tenant, user, ruta):
    cliente, bobina, _, linea = _preparar(db_session, tenant, user, 20)
    r = cliente.post(f"/api/v1/auth/{ruta}")
    assert r.status_code == 409
    detalle = r.json()["detail"]
    assert detalle["codigo"] == "medicion_pendiente"
    assert detalle["kg_total"] == 20
    assert bobina.coil_id in detalle["mensaje"]
    db_session.expire_all()
    assert bobina.cantidad_disponible == 20
    assert linea.active_coil_id == bobina.id


def test_el_operario_elige_mandar_a_merma_al_cerrar_jornada(db_session, tenant, user):
    cliente, bobina, _, linea = _preparar(db_session, tenant, user, 120)
    r = cliente.post("/api/v1/auth/close-shift", json={"mermar_sin_medir": True})
    assert r.status_code == 200, r.text
    assert r.json()["merma_sin_medir_kg"] == 120
    _comprobar_merma(db_session, bobina, linea, 120)


def test_el_operario_elige_mandar_a_merma_al_salir(db_session, tenant, user):
    cliente, bobina, _, linea = _preparar(db_session, tenant, user, 120)
    r = cliente.post("/api/v1/auth/logout", json={"mermar_sin_medir": True})
    assert r.status_code == 204, r.text
    _comprobar_merma(db_session, bobina, linea, 120)


def test_si_mide_no_se_anota_merma_de_lo_restante(db_session, tenant, user):
    cliente, bobina, orden, linea = _preparar(db_session, tenant, user, 120)
    from tests.test_medicion import _medir

    assert _medir(cliente, bobina, orden, linea, radio=30).status_code == 200
    r = cliente.post("/api/v1/auth/close-shift")
    assert r.status_code == 200, r.text
    assert r.json()["merma_sin_medir_kg"] == 0
    db_session.expire_all()
    assert linea.active_coil_id == bobina.id
    assert bobina.cantidad_disponible > 0
