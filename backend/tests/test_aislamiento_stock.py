"""Aislamiento multiempresa en stock y fin de bobina (auditoría externa 2026-11-06).

- GET /stock-items/materials, /picos y "" solo devuelven datos del tenant del token.
- POST /stock-items ignora el tenant_id del body y usa el del token.
- receive_coil, move_coil, create_retal y retirar_pico rechazan ids de otra empresa.
- create_retal exige que la bobina esté vinculada a la línea indicada.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import auth as auth_router
from app.routers import stock as stock_router
from app.services.inventory import create_retal, retirar_pico
from app.services.receiving import move_coil, receive_coil
from tests.helpers import (
    auth_headers,
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
    make_tenant,
)


def _override_get_db(db_session):
    def _gen():
        yield db_session

    return _gen


@pytest.fixture()
def otra(db_session):
    return make_tenant(db_session, name="Otra Empresa")


def _client(db_session, tenant, role="materials"):
    app.dependency_overrides[auth_router.get_db] = _override_get_db(db_session)
    app.dependency_overrides[stock_router.get_db] = _override_get_db(db_session)
    client = TestClient(app)
    client.headers.update(auth_headers(db_session, tenant, role=role))
    return client


@pytest.fixture(autouse=True)
def _limpiar_overrides():
    yield
    app.dependency_overrides.clear()


def test_materials_solo_del_propio_tenant(db_session, tenant, otra):
    make_material(db_session, tenant, code="PROPIO")
    make_material(db_session, otra, code="AJENO")
    r = _client(db_session, tenant).get("/api/v1/stock-items/materials")
    assert r.status_code == 200
    assert {m["code"] for m in r.json()} == {"PROPIO"}


def test_picos_solo_del_propio_tenant(db_session, tenant, otra):
    m1 = make_material(db_session, tenant, code="PROPIO")
    m2 = make_material(db_session, otra, code="AJENO")
    make_stock_item(db_session, tenant, m1, lote="L-P", estado="pico", ubicacion="Retales")
    make_stock_item(db_session, otra, m2, lote="L-A", estado="pico", ubicacion="Retales")
    r = _client(db_session, tenant, role="operator").get("/api/v1/stock-items/picos")
    assert r.status_code == 200
    assert {p["lote"] for p in r.json()} == {"L-P"}


def test_listado_de_bobinas_solo_del_propio_tenant(db_session, tenant, otra):
    m1 = make_material(db_session, tenant, code="PROPIO")
    m2 = make_material(db_session, otra, code="AJENO")
    make_stock_item(db_session, tenant, m1, lote="L-P")
    make_stock_item(db_session, otra, m2, lote="L-A")
    r = _client(db_session, tenant).get("/api/v1/stock-items")
    assert r.status_code == 200
    assert {b["lote"] for b in r.json()} == {"L-P"}


def test_recepcion_ignora_tenant_del_body(db_session, tenant, otra):
    material = make_material(db_session, tenant, code="PROPIO")
    r = _client(db_session, tenant).post(
        "/api/v1/stock-items",
        json={
            "tenant_id": str(otra.id),
            "material_id": str(material.id),
            "lote": "L-BODY",
            "peso": "500",
        },
    )
    assert r.status_code == 201 or r.status_code == 200, r.text
    from app.models import StockItem

    item = db_session.query(StockItem).filter_by(lote="L-BODY").one()
    assert item.tenant_id == tenant.id


def test_recepcion_rechaza_material_de_otra_empresa(db_session, tenant, user, otra):
    material_ajeno = make_material(db_session, otra, code="AJENO")
    with pytest.raises(ValueError, match="no existe"):
        receive_coil(
            db_session, tenant.id, user.id,
            material_id=material_ajeno.id, lote="L-X", peso=100.0,
        )


def test_move_coil_rechaza_bobina_de_otra_empresa(db_session, tenant, user, otra):
    material = make_material(db_session, otra, code="AJENO")
    bobina = make_stock_item(db_session, otra, material, lote="L-A")
    with pytest.raises(ValueError, match="no existe"):
        move_coil(
            db_session, tenant.id, user.id,
            stock_item_id=bobina.id, nueva_ubicacion="LINEA-9",
        )


def _montada(db_session, tenant, lote="L-M"):
    material = make_material(db_session, tenant, code=f"M-{lote}")
    bobina = make_stock_item(db_session, tenant, material, lote=lote, ancho=122, espesor=0.5)
    orden = make_order(db_session, tenant, numero=f"OP-{lote}")
    linea = make_order_line(db_session, orden)
    linea.active_coil_id = bobina.id
    db_session.commit()
    return bobina, orden, linea


def test_create_retal_exige_tenant(db_session, tenant, user):
    bobina, orden, linea = _montada(db_session, tenant)
    with pytest.raises(ValueError, match="tenant_id"):
        create_retal(
            db_session, None, user.id,
            stock_item_id=bobina.id, radio_mm=0, order_id=orden.id, line_id=linea.id,
        )


def test_create_retal_rechaza_bobina_de_otra_empresa(db_session, tenant, user, otra):
    bobina, orden, linea = _montada(db_session, otra, lote="L-A")
    with pytest.raises(ValueError, match="no encontrada"):
        create_retal(
            db_session, tenant.id, user.id,
            stock_item_id=bobina.id, radio_mm=0, order_id=orden.id, line_id=linea.id,
        )


def test_create_retal_rechaza_orden_de_otra_empresa(db_session, tenant, user, otra):
    bobina, _, _ = _montada(db_session, tenant, lote="L-P")
    orden_ajena = make_order(db_session, otra, numero="OP-AJENA")
    linea_ajena = make_order_line(db_session, orden_ajena)
    with pytest.raises(ValueError, match="no existe"):
        create_retal(
            db_session, tenant.id, user.id,
            stock_item_id=bobina.id, radio_mm=0,
            order_id=orden_ajena.id, line_id=linea_ajena.id,
        )


def test_create_retal_exige_bobina_vinculada_a_la_linea(db_session, tenant, user):
    bobina, orden, linea = _montada(db_session, tenant)
    linea.active_coil_id = None
    db_session.commit()
    with pytest.raises(ValueError, match="no está vinculada"):
        create_retal(
            db_session, tenant.id, user.id,
            stock_item_id=bobina.id, radio_mm=0, order_id=orden.id, line_id=linea.id,
        )


def test_retirar_pico_rechaza_bobina_de_otra_empresa(db_session, tenant, user, otra):
    material = make_material(db_session, otra, code="AJENO")
    bobina = make_stock_item(db_session, otra, material, lote="L-A", estado="pico")
    with pytest.raises(ValueError, match="no encontrada"):
        retirar_pico(db_session, tenant.id, user.id, stock_item_id=bobina.id)
