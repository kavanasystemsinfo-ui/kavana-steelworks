"""Regresiones de la auditoría del panel de operario (2026-11-07):
coil_id repetido, órdenes ya completadas ofrecidas y bobinas en puestos desactivados."""

import pytest

from app.main import app
from app.routers import orders as orders_router
from app.services.receiving import receive_coil
from app.services.seed_planta import _reubicar_bobinas_de_puestos_antiguos
from app.services.simulador import _reponer_bobina
from tests.helpers import (
    authed_client_for,
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
    make_user,
)


def test_receive_coil_rechaza_un_coil_id_repetido(db_session, tenant):
    mat = make_material(db_session, tenant, code="M-DUP")
    receive_coil(db_session, tenant.id, None, material_id=mat.id, lote="A", coil_id="X-1", peso=10)
    with pytest.raises(ValueError, match="Ya existe"):
        receive_coil(
            db_session, tenant.id, None, material_id=mat.id, lote="B", coil_id="X-1", peso=10
        )


def test_dos_reposiciones_seguidas_no_repiten_coil_id(db_session, tenant):
    mat = make_material(db_session, tenant, code="M-REP")
    make_stock_item(db_session, tenant, mat, lote="BASE", ubicacion="ALMACEN")
    a = _reponer_bobina(db_session, tenant.id, mat.id, None)
    b = _reponer_bobina(db_session, tenant.id, mat.id, None)
    assert a.coil_id != b.coil_id


def test_available_no_ofrece_lineas_ya_completadas(db_session, tenant):
    hecha = make_order(db_session, tenant, numero="OP-HECHA")
    ln = make_order_line(db_session, hecha, workstation="LINEA-1")
    ln.estado = "completed"
    pendiente = make_order(db_session, tenant, numero="OP-PEND")
    make_order_line(db_session, pendiente, workstation="LINEA-1")
    op = make_user(db_session, tenant, email="op-comp@test.local", role="operator")
    op.default_workstation_code = "LINEA-1"
    db_session.commit()
    db_session.refresh(op)

    def _gen():
        yield db_session

    app.dependency_overrides[orders_router.get_db] = _gen
    try:
        r = authed_client_for(db_session, op).get("/api/v1/orders/available")
    finally:
        app.dependency_overrides.clear()
    numeros = {i["numero"] for i in r.json()}
    assert "OP-PEND" in numeros and "OP-HECHA" not in numeros


def test_bobinas_libres_de_puestos_antiguos_vuelven_al_almacen(db_session, tenant):
    mat = make_material(db_session, tenant, code="M-UBI")
    libre = make_stock_item(db_session, tenant, mat, lote="L1", ubicacion="PLEG-220")
    en_puesto = make_stock_item(db_session, tenant, mat, lote="L2", ubicacion="PL-220")
    assert _reubicar_bobinas_de_puestos_antiguos(db_session, tenant.id) == 1
    db_session.refresh(libre)
    db_session.refresh(en_puesto)
    assert libre.ubicacion == "ALMACEN" and en_puesto.ubicacion == "PL-220"
