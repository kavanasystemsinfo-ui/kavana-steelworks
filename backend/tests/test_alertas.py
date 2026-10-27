"""Tests de las alertas del centro de mando (services/alertas.py)."""

from decimal import Decimal

from app.models import Incidencia
from app.services.alertas import alertas
from tests.helpers import auth_headers, make_material


def test_stock_bajo_minimos_misma_regla_que_el_detalle(db_session, tenant):
    bajo = make_material(db_session, tenant, code="FLEJE-BAJO")
    bajo.stock_current = Decimal("100")
    bajo.stock_minimum = Decimal("400")
    sobra = make_material(db_session, tenant, code="FLEJE-OK")
    sobra.stock_current = Decimal("900")
    sobra.stock_minimum = Decimal("400")
    sin_minimo = make_material(db_session, tenant, code="TORNILLO")  # mínimo 0: no alerta
    sin_minimo.stock_current = Decimal("0")
    inactivo = make_material(db_session, tenant, code="VIEJO")
    inactivo.stock_minimum = Decimal("10")
    inactivo.is_active = False
    db_session.commit()

    resultado = alertas(db_session, tenant.id)

    assert [m["code"] for m in resultado["stock_bajo_minimos"]] == ["FLEJE-BAJO"]
    assert resultado["stock_bajo_minimos"][0]["minimo"] == 400.0


def test_cuenta_solo_incidencias_abiertas(db_session, tenant, user):
    for estado in ("abierta", "en_revision", "resuelta", "cerrada"):
        db_session.add(
            Incidencia(
                tenant_id=tenant.id,
                puesto="PERF-1",
                operario_id=user.id,
                descripcion=estado,
                tipo="otro",
                estado=estado,
            )
        )
    db_session.commit()

    assert alertas(db_session, tenant.id)["incidencias_abiertas"] == 2


def test_endpoint_alertas_solo_supervisor(db_session, tenant, user):
    from tests.test_auth_roles import _client

    operario = _client(db_session, auth_headers(db_session, tenant, role="operator"))
    assert operario.get("/api/v1/supervisor/alertas").status_code == 403

    supervisor = _client(
        db_session, auth_headers(db_session, tenant, role="supervisor", email="sup@test.local")
    )
    r = supervisor.get("/api/v1/supervisor/alertas")
    assert r.status_code == 200, r.text
    assert r.json() == {"stock_bajo_minimos": [], "incidencias_abiertas": 0}
