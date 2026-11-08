"""Tests de «picos primero» (T-046, D-019).

Elegir una bobina nueva habiendo picos del mismo material no se impide, pero
pide un motivo de un toque que queda registrado en la trazabilidad. El
supervisor ve los picos acumulados por material.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import OrderLine, ProductionLog
from app.services.ficha_orden import ficha_orden
from tests.helpers import (
    authed_client_for,
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
    make_tenant,
    make_user,
)


def _cliente(db, user):
    from app.main import app
    from app.routers import auth as auth_router
    from app.routers import stock as stock_router

    def _gen():
        yield db

    app.dependency_overrides[stock_router.get_db] = _gen
    app.dependency_overrides[auth_router.get_db] = _gen
    return authed_client_for(db, user)


def _escenario(db, tenant, con_pico=True):
    material = make_material(db, tenant)
    orden = make_order(db, tenant, numero="OP-PICO")
    linea = make_order_line(db, orden, material=material)
    nueva = make_stock_item(
        db, tenant, material, cantidad=800, lote="L-NUEVA", coil_id="B-NUEVA",
        ubicacion="ALMACEN",
    )
    pico = None
    if con_pico:
        pico = make_stock_item(
            db, tenant, material, cantidad=45, lote="L-PICO", coil_id="B-PICO",
            ubicacion="Retales", estado="pico",
            fecha_entrada=datetime.now(UTC) - timedelta(days=12),
        )
    return material, orden, linea, nueva, pico


def _link(client, orden, linea, bobina, motivo=None):
    cuerpo = {
        "stock_item_id": str(bobina.id),
        "order_id": str(orden.id),
        "line_id": str(linea.id),
    }
    if motivo:
        cuerpo["motivo_salto_pico"] = motivo
    return client.post("/api/v1/stock-items/link", json=cuerpo)


def test_bobina_nueva_habiendo_picos_pide_motivo_y_no_vincula(db_session, tenant, user):
    _, orden, linea, nueva, _ = _escenario(db_session, tenant)
    client = _cliente(db_session, user)

    r = _link(client, orden, linea, nueva)

    assert r.status_code == 409, r.text
    detalle = r.json()["detail"]
    assert detalle["codigo"] == "MOTIVO_PICO_REQUERIDO"
    assert detalle["picos"] == [{"coil_id": "B-PICO", "peso_kg": 45.0}]
    db_session.refresh(linea)
    assert linea.active_coil_id is None


def test_con_motivo_vincula_y_queda_registrado_en_la_trazabilidad(db_session, tenant, user):
    _, orden, linea, nueva, _ = _escenario(db_session, tenant)
    client = _cliente(db_session, user)

    r = _link(client, orden, linea, nueva, motivo="pico_corto")

    assert r.status_code == 200, r.text
    db_session.refresh(linea)
    assert linea.active_coil_id == nueva.id
    log = db_session.scalars(
        select(ProductionLog).where(ProductionLog.order_id == orden.id)
    ).one()
    assert log.action == "setup_start"
    meta = dict(log.metadata_)
    assert meta["reason"] == "salto_pico"
    assert meta["motivo"] == "pico_corto"
    assert meta["picos_omitidos"] == ["B-PICO"]
    assert meta["activeCoilCode"] == "B-NUEVA"

    ficha = ficha_orden(db_session, tenant.id, orden.id)
    evento = next(e for e in ficha["linea_tiempo"] if "con picos disponibles" in e["titulo"])
    assert evento["categoria"] == "bobina"
    assert "El pico no llega para la orden" in evento["detalle"]
    assert "B-PICO" in evento["detalle"]


def test_vincular_el_propio_pico_no_pide_motivo(db_session, tenant, user):
    _, orden, linea, _, pico = _escenario(db_session, tenant)
    client = _cliente(db_session, user)

    r = _link(client, orden, linea, pico)

    assert r.status_code == 200, r.text
    assert db_session.scalars(select(ProductionLog)).all() == []


def test_bobina_ya_en_el_puesto_no_pide_motivo(db_session, tenant, user):
    _, orden, linea, nueva, _ = _escenario(db_session, tenant)
    nueva.ubicacion = linea.workstation_id  # la dejó allí el turno anterior (D-007)
    db_session.commit()
    client = _cliente(db_session, user)

    r = _link(client, orden, linea, nueva)

    assert r.status_code == 200, r.text


def test_sin_picos_no_pide_motivo(db_session, tenant, user):
    _, orden, linea, nueva, _ = _escenario(db_session, tenant, con_pico=False)
    client = _cliente(db_session, user)

    r = _link(client, orden, linea, nueva)

    assert r.status_code == 200, r.text


def test_un_pico_de_otro_tenant_no_obliga_a_dar_motivo(db_session, tenant, user):
    _, orden, linea, nueva, _ = _escenario(db_session, tenant, con_pico=False)
    otro = make_tenant(db_session, name="Otra planta", slug="otra-planta")
    material_otro = make_material(db_session, otro, code="ACERO-02")
    make_stock_item(
        db_session, otro, material_otro, cantidad=30, lote="L-AJENO", coil_id="B-AJENO",
        estado="pico",
    )
    client = _cliente(db_session, user)

    r = _link(client, orden, linea, nueva)

    assert r.status_code == 200, r.text


def test_un_motivo_inventado_se_rechaza(db_session, tenant, user):
    _, orden, linea, nueva, _ = _escenario(db_session, tenant)
    client = _cliente(db_session, user)

    r = _link(client, orden, linea, nueva, motivo="porque_si")

    assert r.status_code == 422


def test_disponibles_trae_la_antiguedad_de_cada_bobina(db_session, tenant, user):
    _, orden, linea, nueva, pico = _escenario(db_session, tenant)
    client = _cliente(db_session, user)

    r = client.get(f"/api/v1/stock-items/disponibles?line_id={linea.id}")

    assert r.status_code == 200, r.text
    filas = {b["coil_id"]: b for b in r.json()}
    assert filas["B-PICO"]["antiguedad_dias"] == 12
    assert filas["B-PICO"]["estado"] == "pico"
    assert filas["B-NUEVA"]["antiguedad_dias"] == 0
    # picos primero: el pico va delante de la bobina nueva
    orden_ids = [b["coil_id"] for b in r.json()]
    assert orden_ids.index("B-PICO") < orden_ids.index("B-NUEVA")


def test_supervisor_ve_los_picos_acumulados_por_material(db_session, tenant, user):
    material, _, _, _, _ = _escenario(db_session, tenant)
    make_stock_item(
        db_session, tenant, material, cantidad=20, lote="L-PICO2", coil_id="B-PICO2",
        ubicacion="LINEA-1", estado="pico",
        fecha_entrada=datetime.now(UTC) - timedelta(days=3),
    )
    otro_material = make_material(db_session, tenant, code="ACERO-GALV")
    make_stock_item(
        db_session, tenant, otro_material, cantidad=10, lote="L-GALV", coil_id="B-GALV",
        estado="pico",
    )
    supervisor = make_user(
        db_session, tenant, email="sup@test.local", role="supervisor", name="Sup"
    )
    client = _cliente(db_session, supervisor)

    r = client.get("/api/v1/stock-items/picos-por-material")

    assert r.status_code == 200, r.text
    grupos = {g["material_code"]: g for g in r.json()}
    acero = grupos["ACERO-01"]
    assert acero["picos"] == 2
    assert acero["kg_total"] == 65.0
    assert acero["mas_antiguo_dias"] == 12
    assert {i["coil_id"] for i in acero["items"]} == {"B-PICO", "B-PICO2"}
    assert grupos["ACERO-GALV"]["picos"] == 1
    # primero el material con más kilos de picos
    assert r.json()[0]["material_code"] == "ACERO-01"


def test_picos_por_material_es_solo_del_supervisor_y_de_su_planta(db_session, tenant, user):
    _escenario(db_session, tenant)
    otro = make_tenant(db_session, name="Otra planta", slug="otra-planta-2")
    material_otro = make_material(db_session, otro, code="ACERO-X")
    make_stock_item(
        db_session, otro, material_otro, cantidad=99, lote="L-X", coil_id="B-X", estado="pico"
    )

    operario = _cliente(db_session, user)
    assert operario.get("/api/v1/stock-items/picos-por-material").status_code == 403

    supervisor = make_user(
        db_session, tenant, email="sup2@test.local", role="supervisor", name="Sup 2"
    )
    r = _cliente(db_session, supervisor).get("/api/v1/stock-items/picos-por-material")
    assert [g["material_code"] for g in r.json()] == ["ACERO-01"]


def test_la_linea_conserva_la_bobina_montada_tras_el_aviso(db_session, tenant, user):
    """Un 409 no debe dejar la línea a medias: sigue sin bobina activa."""
    _, orden, linea, nueva, _ = _escenario(db_session, tenant)
    client = _cliente(db_session, user)

    _link(client, orden, linea, nueva)
    db_session.expire_all()

    fila = db_session.scalars(select(OrderLine).where(OrderLine.id == linea.id)).one()
    assert fila.active_coil_id is None
    assert fila.real_material_qty in (0, None)
