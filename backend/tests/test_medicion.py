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
