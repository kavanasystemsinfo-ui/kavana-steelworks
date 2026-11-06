"""Barrido de tenant (T-026, seguimiento de la auditoría 2026-11-06).

Ids de orden/línea que manda el cliente se comprueban contra el tenant del
token en trazabilidad, autocontrol, paradas y medición.
"""

import pytest

from app.main import app
from app.models.quality import ManufacturingModel
from app.routers import trace as trace_router
from app.services.paradas import iniciar_parada
from app.services.quality import registrar_autocontrol
from tests.helpers import (
    authed_client,
    make_order,
    make_order_line,
    make_tenant,
)


@pytest.fixture()
def otra(db_session):
    return make_tenant(db_session, name="Otra Empresa")


def test_traza_de_orden_ajena_da_404(db_session, tenant, otra):
    orden_ajena = make_order(db_session, otra, numero="OP-AJENA")

    def _override_get_db():
        yield db_session

    app.dependency_overrides[trace_router.get_db] = _override_get_db
    try:
        client = authed_client(db_session, tenant, role="supervisor")
        r = client.get(f"/api/v1/trace/orders/{orden_ajena.id}")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 404


def test_parada_rechaza_orden_y_linea_ajenas(db_session, tenant, user, otra):
    orden_ajena = make_order(db_session, otra, numero="OP-AJENA")
    linea_ajena = make_order_line(db_session, orden_ajena)
    with pytest.raises(ValueError, match="no encontrada"):
        iniciar_parada(
            db_session, tenant.id, user.id,
            puesto="LINEA-1", motivo="averia", order_id=orden_ajena.id,
        )
    with pytest.raises(ValueError, match="no encontrada"):
        iniciar_parada(
            db_session, tenant.id, user.id,
            puesto="LINEA-1", motivo="averia", line_id=linea_ajena.id,
        )


def test_autocontrol_rechaza_orden_ajena(db_session, tenant, user, otra):
    modelo = ManufacturingModel(tenant_id=tenant.id, code="MOD-X", name="Modelo X", is_active=True)
    db_session.add(modelo)
    db_session.commit()
    orden_ajena = make_order(db_session, otra, numero="OP-AJENA")
    with pytest.raises(ValueError, match="Orden no encontrada"):
        registrar_autocontrol(
            db_session,
            tenant_id=tenant.id,
            operator_id=user.id,
            order_id=orden_ajena.id,
            workstation_id="LINEA-1",
            manufacturing_model_id=modelo.id,
            mediciones=[],
        )
