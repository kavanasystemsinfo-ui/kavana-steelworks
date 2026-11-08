"""Tests de la ficha de trazabilidad de una orden (T-045).

GET /api/v1/trace/orders/{id}/ficha devuelve el resumen y una línea de tiempo
unificada (producción, calidad, bobina, parada, incidencia, estado) de más
reciente a más antiguo.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.main import app
from app.models import Incidencia, MaterialConsumo, MaterialTransaction, Parada
from app.routers import trace as trace_router
from app.services import traceability
from app.services.ficha_orden import ficha_orden
from tests.helpers import (
    authed_client,
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
    make_tenant,
)

BASE = datetime(2026, 11, 8, 8, 0, tzinfo=UTC)


def _log(db, tenant, user, orden, linea, action, minuto, cantidad=0, metadata=None):
    traceability.log_event(
        db,
        tenant_id=tenant.id,
        order_id=orden.id,
        line_id=linea.id,
        operator_id=user.id,
        action=action,
        quantity=cantidad,
        timestamp=BASE + timedelta(minutes=minuto),
        metadata=metadata,
    )


def _escenario(db, tenant, user):
    material = make_material(db, tenant)
    orden = make_order(db, tenant, numero="OP-FICHA")
    linea = make_order_line(db, orden, total_quantity=100, material=material)
    linea.produced_quantity = 40
    db.commit()
    bobina = make_stock_item(db, tenant, material, cantidad=500, lote="L-FICHA", coil_id="B-FICHA")
    db.add(
        MaterialTransaction(
            tenant_id=tenant.id, material_id=material.id, stock_item_id=bobina.id,
            orden_id=orden.id, linea_orden_id=linea.id, tipo="salida_produccion",
            cantidad=500, cantidad_anterior=500, cantidad_nueva=500,
            motivo="Bobina vinculada a la Línea. Carga total de Entrada: 500.00kg",
            realizado_por=user.id,
        )
    )
    db.commit()

    _log(db, tenant, user, orden, linea, "start", 1)
    _log(
        db, tenant, user, orden, linea, "produce", 10, 40,
        {"activeCoilCode": "B-FICHA", "consumedAmount": 120.5, "efficiency": 80.0},
    )
    _log(db, tenant, user, orden, linea, "quality_check", 20, 0,
         {"status": "ok", "manufacturingModel": "Perfil C", "measurementsCount": 3})
    _log(
        db, tenant, user, orden, linea, "scrap", 30, 4.2,
        {"reason": "fin_bobina", "activeCoilCode": "B-FICHA", "merma_cost": 3.5},
    )

    db.add(
        MaterialConsumo(
            tenant_id=tenant.id, order_id=orden.id, order_line_id=linea.id,
            workstation_id="LINEA-1", material_id=material.id, stock_item_id=bobina.id,
            lote="L-FICHA", consumed_quantity=120.5, unit="kg", produced_quantity=40,
            kg_por_pieza=3.0, calculation_method="density_formula", cost_per_unit=1,
            total_cost=120.5,
        )
    )
    db.add(
        Parada(
            tenant_id=tenant.id, puesto="LINEA-1", operario_id=user.id, order_id=orden.id,
            line_id=linea.id, motivo="averia", nota="cuchilla",
            inicio=BASE + timedelta(minutes=15), fin=BASE + timedelta(minutes=25),
        )
    )
    db.add(
        Incidencia(
            tenant_id=tenant.id, order_id=orden.id, puesto="LINEA-1", operario_id=user.id,
            descripcion="Bobina con óxido", tipo="material", estado="abierta",
        )
    )
    db.commit()
    return orden, bobina


def test_ficha_une_fuentes_y_ordena_de_mas_reciente_a_mas_antiguo(db_session, tenant, user):
    orden, _ = _escenario(db_session, tenant, user)

    ficha = ficha_orden(db_session, tenant.id, orden.id)

    tiempos = [e["timestamp"] for e in ficha["linea_tiempo"]]
    assert tiempos == sorted(tiempos, reverse=True)
    categorias = {e["categoria"] for e in ficha["linea_tiempo"]}
    assert {"produccion", "calidad", "bobina", "parada", "incidencia", "estado"} <= categorias
    titulos = [e["titulo"] for e in ficha["linea_tiempo"]]
    assert "Bobina B-FICHA vinculada" in titulos
    vinculada = next(e for e in ficha["linea_tiempo"] if e["titulo"] == "Bobina B-FICHA vinculada")
    assert vinculada["quien"] == user.name
    assert "Merma de bobina B-FICHA" in titulos
    assert "Autocontrol de calidad: ok" in titulos
    assert "Parada en LINEA-1" in titulos
    assert "Orden creada" in titulos


def test_resumen_calcula_piezas_merma_kilos_personas_y_paradas(db_session, tenant, user):
    orden, _ = _escenario(db_session, tenant, user)

    r = ficha_orden(db_session, tenant.id, orden.id)["resumen"]

    assert r["piezas_producidas"] == 40
    assert r["piezas_objetivo"] == 100
    assert r["merma_kg"] == 4.2
    assert r["kg_consumidos"] == 120.5
    assert r["kg_por_bobina"][0]["coil_id"] == "B-FICHA"
    assert r["kg_por_bobina"][0]["kg"] == 120.5
    assert r["paradas_minutos"] == 10.0
    assert r["paradas_abiertas"] == 0
    assert r["incidencias"] == 1
    assert r["eficiencia_media_uds_h"] == 80.0
    assert r["personas"][0]["nombre"] == user.name
    assert r["personas"][0]["piezas"] == 40


def test_alta_manual_de_bobina_aparece_con_quien_donde_y_estado(db_session, tenant, user):
    orden, bobina = _escenario(db_session, tenant, user)
    bobina.origen = "alta_manual"
    bobina.creada_por_user_id = user.id
    bobina.alta_ubicacion = "LINEA-1"
    bobina.pendiente_verificacion = True
    db_session.commit()

    ficha = ficha_orden(db_session, tenant.id, orden.id)

    alta = next(e for e in ficha["linea_tiempo"] if e["titulo"].endswith("dada de alta a mano"))
    assert alta["quien"] == user.name
    assert "LINEA-1" in alta["detalle"]
    assert "pendiente de verificar" in alta["detalle"]
    fila = ficha["resumen"]["kg_por_bobina"][0]
    assert fila["origen"] == "alta_manual"
    assert fila["pendiente_verificacion"] is True


def test_verificacion_de_la_bobina_queda_en_la_linea_de_tiempo(db_session, tenant, user):
    orden, bobina = _escenario(db_session, tenant, user)
    bobina.origen = "alta_manual"
    bobina.creada_por_user_id = user.id
    bobina.pendiente_verificacion = False
    bobina.verificada_por_user_id = user.id
    bobina.verificada_en = BASE + timedelta(minutes=40)
    db_session.commit()

    ficha = ficha_orden(db_session, tenant.id, orden.id)

    verif = next(e for e in ficha["linea_tiempo"] if e["titulo"].endswith("verificada"))
    assert verif["quien"] == user.name
    ids = [e["id"] for e in ficha["linea_tiempo"]]
    merma = next(e for e in ficha["linea_tiempo"] if e["titulo"].startswith("Merma"))
    assert ids.index(verif["id"]) < ids.index(merma["id"])  # la verificación es posterior


def test_orden_de_otro_tenant_no_se_ve(db_session, tenant, user):
    orden, _ = _escenario(db_session, tenant, user)
    otro = make_tenant(db_session, name="Otra", slug="otra")

    assert ficha_orden(db_session, otro.id, orden.id) is None
    assert ficha_orden(db_session, tenant.id, uuid.uuid4()) is None


def test_endpoint_ficha_solo_supervisor_y_404(db_session, tenant, user):
    orden, _ = _escenario(db_session, tenant, user)

    def _override_get_db():
        yield db_session

    app.dependency_overrides[trace_router.get_db] = _override_get_db
    try:
        supervisor = authed_client(db_session, tenant, role="supervisor")
        ok = supervisor.get(f"/api/v1/trace/orders/{orden.id}/ficha")
        falta = supervisor.get(f"/api/v1/trace/orders/{uuid.uuid4()}/ficha")
        operario = authed_client(db_session, tenant, role="operator")
        prohibido = operario.get(f"/api/v1/trace/orders/{orden.id}/ficha")
    finally:
        app.dependency_overrides.clear()

    assert ok.status_code == 200, ok.text
    assert ok.json()["resumen"]["numero"] == "OP-FICHA"
    assert falta.status_code == 404
    assert prohibido.status_code == 403


def test_orden_sin_actividad_devuelve_ficha_vacia_sin_romper(db_session, tenant, user):
    orden = make_order(db_session, tenant, numero="OP-VACIA")

    ficha = ficha_orden(db_session, tenant.id, orden.id)

    assert ficha["resumen"]["piezas_producidas"] == 0
    assert ficha["resumen"]["kg_por_bobina"] == []
    assert ficha["resumen"]["eficiencia_media_uds_h"] is None
    assert [e["titulo"] for e in ficha["linea_tiempo"]] == ["Orden creada"]
