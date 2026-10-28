"""Tests de la ficha de orden del panel de operario y las horas automáticas
(services/ficha_operario.py, rediseño aprobado por Jorge el 28-10)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.main import app
from app.models import ProductionLog, UserShift, Workstation
from app.routers import production as production_router
from app.services.inventory import link_coil
from tests.helpers import (
    authed_client_for,
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
)


def _cliente(db, user):
    def _gen():
        yield db

    app.dependency_overrides[production_router.get_db] = _gen
    return authed_client_for(db, user)


def _escenario(db, tenant, user):
    material = make_material(db, tenant, code="GALVA-182")
    material.dimension_ancho_mm = Decimal("182")
    material.dimension_espesor_mm = Decimal("1.2")
    db.add(
        Workstation(tenant_id=tenant.id, code="LINEA-1", name="Línea 1", piezas_hora_nominal=600)
    )
    orden = make_order(db, tenant, numero="OF-SOL-01")
    orden.cliente = "Nova Solar"
    orden.fecha_entrega = datetime.now(UTC) + timedelta(days=3)
    linea = make_order_line(db, orden, material=material, total_quantity=115)
    linea.meters_per_piece = Decimal("0.212")
    linea.produced_quantity = Decimal("54")
    db.commit()
    bobina = make_stock_item(
        db, tenant, material, cantidad=600, lote="B-182", ancho=182, espesor=1.2
    )
    link_coil(db, tenant.id, user.id, stock_item_id=bobina.id, order_id=orden.id, line_id=linea.id)
    return orden, linea, bobina


def test_la_ficha_trae_los_datos_clave_de_la_orden(db_session, tenant, user):
    orden, linea, bobina = _escenario(db_session, tenant, user)
    cliente = _cliente(db_session, user)

    r = cliente.get(
        "/api/v1/production/ficha", params={"order_id": str(orden.id), "line_id": str(linea.id)}
    )
    assert r.status_code == 200, r.text
    f = r.json()
    assert (f["numero"], f["cliente"], f["material"]) == ("OF-SOL-01", "Nova Solar", "GALVA-182")
    assert (f["ancho_mm"], f["espesor_mm"], f["largo_mm"]) == (182.0, 1.2, 212)
    assert (f["total"], f["hechas"], f["faltan"], f["ritmo"]) == (115.0, 54.0, 61.0, 600.0)
    assert f["plazo"] == "a_tiempo"
    # 600 kg / (0,212 m × 0,182 m × 0,0012 m × 7850 kg/m³ ≈ 0,363 kg) ≈ 1651 piezas
    assert f["bobina"]["codigo"] == bobina.coil_id
    assert 1600 < f["bobina"]["piezas_estimadas"] < 1700
    assert f["tramo_desde"] is not None  # el login abrió el turno


def test_las_horas_se_cuentan_solas_desde_el_inicio_de_sesion(db_session, tenant, user):
    orden, linea, _ = _escenario(db_session, tenant, user)
    cliente = _cliente(db_session, user)
    turno = db_session.scalar(select(UserShift).where(UserShift.operator_id == user.id))
    turno.login_time = datetime.now(UTC) - timedelta(hours=2)
    db_session.commit()

    r = cliente.post(
        "/api/v1/production/record",
        json={"order_id": str(orden.id), "line_id": str(linea.id), "incremental_quantity": 10},
    )
    assert r.status_code == 200, r.text

    log = db_session.scalar(select(ProductionLog).where(ProductionLog.action == "produce"))
    # 10 piezas en ≈ 2 h → eficiencia ≈ 5 piezas/h (antes, sin horas, no había)
    assert 4.5 < log.metadata_["efficiency"] < 5.5


def test_calculadoras_del_puesto(db_session, tenant, user):
    """El operario crea calculadoras en su puesto y las ve cualquiera de él."""
    cliente = _cliente(db_session, user)
    datos = {
        "puesto": "LINEA-1", "nombre": "Palet celda M10",
        "piezas_paquete": 5, "paquetes_fila": 2, "filas_palet": 4,
    }
    r = cliente.post("/api/v1/production/calculadoras", json=datos)
    assert r.status_code == 201, r.text
    assert (r.json()["piezas_fila"], r.json()["piezas_palet"]) == (10, 40)
    assert cliente.post("/api/v1/production/calculadoras", json=datos).status_code == 409

    lista = cliente.get("/api/v1/production/calculadoras", params={"puesto": "LINEA-1"}).json()
    assert [c["nombre"] for c in lista] == ["Palet celda M10"]
    otro = cliente.get("/api/v1/production/calculadoras", params={"puesto": "LINEA-2"}).json()
    assert otro == []


def test_el_registro_guarda_el_desglose_de_la_calculadora(db_session, tenant, user):
    orden, linea, _ = _escenario(db_session, tenant, user)
    cliente = _cliente(db_session, user)
    desglose = {
        "calculadora": "Palet celda M10", "palets": 1, "filas": 0, "paquetes": 2, "piezas": 0,
    }

    r = cliente.post(
        "/api/v1/production/record",
        json={
            "order_id": str(orden.id), "line_id": str(linea.id),
            "incremental_quantity": 50, "desglose": desglose,
        },
    )
    assert r.status_code == 200, r.text
    log = db_session.scalar(select(ProductionLog).where(ProductionLog.action == "produce"))
    assert log.metadata_["desglose"] == desglose
