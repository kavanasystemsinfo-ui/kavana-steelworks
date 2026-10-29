"""Tests de la medición de cierre de turno (services/medicion.py).

Modelo de planta (Jorge, 28-10): la línea carga el peso de la etiqueta al
vincular, las piezas descuentan sus kilos teóricos y, al cerrar el turno, el
operario mide el radio. Lo que el sistema creía que quedaba menos lo medido
es su chatarra; la bobina sigue montada para el relevo. Sin medir no puede
cerrar la jornada ni la sesión.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.main import app
from app.routers import auth as auth_router
from app.routers import stock as stock_router
from app.services.coil_math import peso_desde_radio_mm
from app.services.inventory import link_coil
from app.services.traceability import log_event
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

    app.dependency_overrides[stock_router.get_db] = _gen
    app.dependency_overrides[auth_router.get_db] = _gen
    return authed_client_for(db, user)


def _montada(db, tenant, user, peso=1200.0):
    material = make_material(db, tenant, code="FLEJE-108")
    bobina = make_stock_item(db, tenant, material, cantidad=peso, lote="L-MED", ancho=108)
    orden = make_order(db, tenant, numero="OP-MED")
    linea = make_order_line(db, orden, material=material)
    link_coil(db, tenant.id, user.id, stock_item_id=bobina.id, order_id=orden.id, line_id=linea.id)
    return bobina, orden, linea


def _producir(db, user, bobina, orden, linea, kg, observaciones=None):
    """Lo que dejaría record_production: kilos descontados y evento produce."""
    bobina.cantidad_disponible -= Decimal(str(kg))
    db.commit()
    log_event(
        db,
        tenant_id=orden.tenant_id,
        order_id=orden.id,
        line_id=linea.id,
        operator_id=user.id,
        action="produce",
        quantity=10,
        metadata={
            "consumedMaterial": "kg",
            "consumedAmount": kg,
            "activeCoilId": str(bobina.id),
            "activeCoilCode": bobina.coil_id,
            "observaciones": observaciones,
        },
    )


def _medir(cliente, bobina, orden, linea, radio):
    return cliente.post(
        "/api/v1/stock-items/medir",
        json={
            "stock_item_id": str(bobina.id),
            "order_id": str(orden.id),
            "line_id": str(linea.id),
            "radio_mm": radio,
        },
    )


def test_medir_apunta_la_chatarra_y_deja_la_bobina_montada(db_session, tenant, user):
    bobina, orden, linea = _montada(db_session, tenant, user)
    cliente = _cliente(db_session, user)
    _producir(db_session, user, bobina, orden, linea, kg=700)  # el sistema cree que quedan 500

    r = _medir(cliente, bobina, orden, linea, radio=150)
    assert r.status_code == 200, r.text

    real = peso_desde_radio_mm(radio_mm=150, width_mm=108, densidad_kg_dm3=7.7807)
    assert r.json()["chatarra_kg"] == round(500 - real, 2)
    db_session.refresh(bobina)
    db_session.refresh(linea)
    assert float(bobina.cantidad_disponible) == real
    assert bobina.estado == "activo"
    assert linea.active_coil_id == bobina.id  # sigue en la máquina para el relevo
    assert float(linea.scrap_material_qty) == round(500 - real, 2)


def test_sin_medir_no_puede_cerrar_jornada_ni_sesion(db_session, tenant, user):
    bobina, orden, linea = _montada(db_session, tenant, user)
    cliente = _cliente(db_session, user)
    _producir(db_session, user, bobina, orden, linea, kg=300)

    pendientes = cliente.get("/api/v1/stock-items/mediciones-pendientes").json()
    assert [p["coil_code"] for p in pendientes] == [bobina.coil_id]
    assert cliente.post("/api/v1/auth/close-shift").status_code == 409
    assert cliente.post("/api/v1/auth/logout").status_code == 409

    assert _medir(cliente, bobina, orden, linea, radio=200).status_code == 200
    assert cliente.get("/api/v1/stock-items/mediciones-pendientes").json() == []
    assert cliente.post("/api/v1/auth/close-shift").status_code == 200


def test_la_produccion_del_simulador_no_bloquea_la_salida(db_session, tenant, user):
    bobina, orden, linea = _montada(db_session, tenant, user)
    cliente = _cliente(db_session, user)
    _producir(db_session, user, bobina, orden, linea, kg=300, observaciones="simulador demo")

    assert cliente.get("/api/v1/stock-items/mediciones-pendientes").json() == []
    assert cliente.post("/api/v1/auth/logout").status_code == 204


def test_alta_manual_con_el_peso_de_la_etiqueta(db_session, tenant, user):
    material = make_material(db_session, tenant, code="FLEJE-108")
    cliente = _cliente(db_session, user)

    r = cliente.post(
        "/api/v1/stock-items/alta-manual",
        json={
            "material_id": str(material.id),
            "peso_kg": 1185.5,
            "lote": "PROV-778",
            "width_mm": 108,
            "thickness_mm": 1.2,
            "puesto": "LINEA-1",
        },
    )
    assert r.status_code == 200, r.text
    alta = r.json()
    assert alta["peso_kg"] == 1185.5
    assert alta["coil_id"].startswith("MAN-")
    escaneo = cliente.get("/api/v1/stock-items/scan", params={"coil_id": alta["coil_id"]})
    assert escaneo.json()["id"] == alta["id"]


def test_informe_de_turno_da_la_chatarra_por_operario(db_session, tenant, user):
    from app.services.informe_turno import informe_turno
    from app.services.shifts import TZ_PLANTA

    bobina, orden, linea = _montada(db_session, tenant, user)
    cliente = _cliente(db_session, user)
    _producir(db_session, user, bobina, orden, linea, kg=700)
    chatarra = _medir(cliente, bobina, orden, linea, radio=150).json()["chatarra_kg"]

    local = datetime.now(UTC).astimezone(TZ_PLANTA)
    turno = "A" if 6 <= local.hour < 14 else "B" if 14 <= local.hour < 22 else "C"
    fecha = local.date() if local.hour >= 6 else date.fromordinal(local.date().toordinal() - 1)
    filas = informe_turno(db_session, tenant.id, fecha, turno)["por_operario"]

    assert len(filas) == 1
    fila = filas[0]
    assert (fila["operario"], fila["orden"], fila["material"]) == (user.name, "OP-MED", "FLEJE-108")
    assert fila["chatarra_kg"] == chatarra
    assert fila["consumo_kg"] == round(700 + chatarra, 2)
    assert fila["chatarra_pct"] == round(chatarra / (700 + chatarra) * 100, 1)


def test_bobinas_disponibles_sin_saber_el_codigo(db_session, tenant, user):
    """Lista para tocar y vincular (legacy MaterialScanner): primero lo que
    está en el puesto, luego picos y después la más antigua; nunca una
    bobina montada en otra línea ni otro material de otro sitio."""
    from datetime import timedelta

    material = make_material(db_session, tenant, code="FLEJE-108")
    otro = make_material(db_session, tenant, code="FLEJE-200")
    hace = datetime.now(UTC)
    vieja = make_stock_item(
        db_session, tenant, material, lote="VIEJA", ubicacion="ALMACEN",
        fecha_entrada=hace - timedelta(days=9),
    )
    nueva = make_stock_item(
        db_session, tenant, material, lote="NUEVA", ubicacion="ALMACEN",
        fecha_entrada=hace - timedelta(days=1),
    )
    pico = make_stock_item(
        db_session, tenant, material, lote="PICO", ubicacion="Retales", estado="pico",
        fecha_entrada=hace - timedelta(days=3),
    )
    en_puesto = make_stock_item(db_session, tenant, otro, lote="EN-PUESTO", ubicacion="LINEA-1")
    make_stock_item(db_session, tenant, otro, lote="OTRO-MAT", ubicacion="ALMACEN")
    montada = make_stock_item(db_session, tenant, material, lote="MONTADA", ubicacion="ALMACEN")
    orden = make_order(db_session, tenant, numero="OP-DISP")
    linea = make_order_line(db_session, orden, material=material)
    ajena = make_order_line(db_session, orden, workstation="LINEA-2", linea_numero=2)
    link_coil(
        db_session, tenant.id, user.id,
        stock_item_id=montada.id, order_id=orden.id, line_id=ajena.id,
    )

    cliente = _cliente(db_session, user)
    r = cliente.get("/api/v1/stock-items/disponibles", params={"line_id": str(linea.id)})
    assert r.status_code == 200, r.text
    lotes = [b["lote"] for b in r.json()]
    # Solo el material de la orden (otro material, aunque esté en el puesto, no)
    assert lotes == [pico.lote, vieja.lote, nueva.lote]
    assert en_puesto.lote not in lotes


def test_cambio_de_orden_en_la_misma_maquina_sigue_con_la_bobina(db_session, tenant, user):
    """Jorge 28-10: misma máquina y mismo material, el operario sigue con la
    bobina montada sin medir. Pasa de una orden a otra (reembolso de lo no
    consumido); una bobina montada en otra máquina no se puede coger."""
    material = make_material(db_session, tenant, code="FLEJE-108")
    bobina = make_stock_item(db_session, tenant, material, cantidad=1200, lote="MONTADA")
    anterior = make_order(db_session, tenant, numero="OP-ANT")
    linea_ant = make_order_line(db_session, anterior, material=material)
    link_coil(
        db_session, tenant.id, user.id,
        stock_item_id=bobina.id, order_id=anterior.id, line_id=linea_ant.id,
    )
    nueva = make_order(db_session, tenant, numero="OP-NUEVA")
    linea_nueva = make_order_line(db_session, nueva, material=material)
    otra_maquina = make_order(db_session, tenant, numero="OP-OTRA")
    linea_otra = make_order_line(db_session, otra_maquina, workstation="LINEA-9", material=material)

    cliente = _cliente(db_session, user)
    disp = cliente.get("/api/v1/stock-items/disponibles", params={"line_id": str(linea_nueva.id)})
    assert [(b["lote"], b["en_puesto"]) for b in disp.json()] == [("MONTADA", True)]
    lejos = cliente.get("/api/v1/stock-items/disponibles", params={"line_id": str(linea_otra.id)})
    assert lejos.json() == []

    link_coil(
        db_session, tenant.id, user.id,
        stock_item_id=bobina.id, order_id=nueva.id, line_id=linea_nueva.id,
    )
    db_session.refresh(linea_ant)
    db_session.refresh(linea_nueva)
    assert linea_ant.active_coil_id is None
    assert linea_nueva.active_coil_id == bobina.id
    assert float(linea_ant.real_material_qty) == 0  # se le devolvió lo no consumido


def _prever(cliente, bobina, radio):
    return cliente.get(f"/api/v1/stock-items/{bobina.id}/prevision-medida?radio_mm={radio}")


def test_prevision_da_los_kg_y_la_merma_sin_guardar_nada(db_session, tenant, user):
    bobina, orden, linea = _montada(db_session, tenant, user)
    cliente = _cliente(db_session, user)
    esperado = peso_desde_radio_mm(radio_mm=150, width_mm=108)

    r = _prever(cliente, bobina, 150)

    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["peso_restante_kg"] == esperado
    assert datos["sistema_kg"] == 1200.0
    assert datos["merma_kg"] == round(1200.0 - esperado, 2)
    db_session.refresh(bobina)
    assert bobina.cantidad_disponible == Decimal("1200")
    # Lo que se previó es lo que se registra al medir
    medido = _medir(cliente, bobina, orden, linea, 150).json()
    assert medido["peso_restante_kg"] == datos["peso_restante_kg"]


def test_prevision_sin_merma_si_queda_mas_de_lo_que_cree_el_sistema(db_session, tenant, user):
    bobina, _, _ = _montada(db_session, tenant, user, peso=100.0)
    datos = _prever(_cliente(db_session, user), bobina, 300).json()
    assert datos["merma_kg"] == 0.0


def test_prevision_errores(db_session, tenant, user):
    import uuid

    from tests.helpers import make_tenant

    cliente = _cliente(db_session, user)
    assert _prever(cliente, type("B", (), {"id": uuid.uuid4()}), 100).status_code == 404
    otro = make_tenant(db_session, name="Otra planta")
    material_ajeno = make_material(db_session, otro, code="X")
    ajena = make_stock_item(db_session, otro, material_ajeno, cantidad=10)
    assert _prever(cliente, ajena, 100).status_code == 404
    bobina, _, _ = _montada(db_session, tenant, user)
    assert _prever(cliente, bobina, -1).status_code == 422
