"""T-033 H4: el operario no puede registrar más kg de los que quedan (decisión de Jorge).

Bobina de 1000 kg, se consumen 400, quedan 600: medir 700 se rechaza con un tip;
600 o menos se acepta.
"""

from decimal import Decimal

import pytest

from app.services import coil_math
from app.services.inventory import create_retal
from app.services.medicion import medir_bobina, prever_medida
from tests.helpers import make_material, make_order, make_order_line, make_stock_item


def _montada(db_session, tenant):
    material = make_material(db_session, tenant, code="M-TOPE", cost=2.0)
    bobina = make_stock_item(
        db_session, tenant, material, cantidad=1000.0, lote="L-TOPE", ancho=122, espesor=0.5
    )
    orden = make_order(db_session, tenant, numero="OP-TOPE")
    linea = make_order_line(db_session, orden, workstation="LINEA-1")
    linea.active_coil_id = bobina.id
    linea.active_coil_code = bobina.coil_id
    bobina.cantidad_disponible = Decimal("600")  # el FIFO ya consumió 400
    db_session.commit()
    return bobina, orden, linea


def _mide(monkeypatch, kg):
    monkeypatch.setattr(coil_math, "peso_desde_radio_mm", lambda **_: kg)


def test_fin_de_bobina_rechaza_700_con_600_disponibles(db_session, tenant, user, monkeypatch):
    bobina, orden, linea = _montada(db_session, tenant)
    _mide(monkeypatch, 700.0)
    with pytest.raises(ValueError, match=r"600,0 kg o inferior|600\.0 kg o inferior"):
        create_retal(
            db_session, tenant.id, user.id,
            stock_item_id=bobina.id, radio_mm=50.0, order_id=orden.id, line_id=linea.id,
        )
    db_session.refresh(bobina)
    db_session.refresh(linea)
    assert bobina.cantidad_disponible == Decimal("600")
    assert linea.active_coil_id == bobina.id


def test_cierre_de_turno_rechaza_700_con_600_disponibles(db_session, tenant, user, monkeypatch):
    bobina, orden, linea = _montada(db_session, tenant)
    _mide(monkeypatch, 700.0)
    with pytest.raises(ValueError, match="vuelve a medir"):
        medir_bobina(
            db_session, tenant.id, user.id,
            stock_item_id=bobina.id, radio_mm=50.0, order_id=orden.id, line_id=linea.id,
        )
    db_session.refresh(bobina)
    assert bobina.cantidad_disponible == Decimal("600")


def test_acepta_600_y_menos(db_session, tenant, user, monkeypatch):
    bobina, orden, linea = _montada(db_session, tenant)
    _mide(monkeypatch, 600.0)
    medir_bobina(
        db_session, tenant.id, user.id,
        stock_item_id=bobina.id, radio_mm=50.0, order_id=orden.id, line_id=linea.id,
    )
    _mide(monkeypatch, 550.0)
    res = create_retal(
        db_session, tenant.id, user.id,
        stock_item_id=bobina.id, radio_mm=50.0, order_id=orden.id, line_id=linea.id,
    )
    assert res["success"] is True


def test_prevision_avisa_antes_de_confirmar(db_session, tenant, monkeypatch):
    bobina, _, _ = _montada(db_session, tenant)
    _mide(monkeypatch, 700.0)
    p = prever_medida(db_session, tenant.id, stock_item_id=bobina.id, radio_mm=50.0)
    assert p["supera_saldo"] is True
    assert "600" in p["mensaje_supera_saldo"]
    _mide(monkeypatch, 590.0)
    p = prever_medida(db_session, tenant.id, stock_item_id=bobina.id, radio_mm=50.0)
    assert p["supera_saldo"] is False
    assert p["mensaje_supera_saldo"] is None

def test_h4_medida_dentro_de_tolerancia_se_acepta(db_session, tenant, user, monkeypatch):
    """Con 600 kg disponibles, 600.005 kg se aceptan y 600.02 kg se rechazan
    con ValueError, tanto en create_retal como en medir_bobina.
    La tolerancia es TOLERANCIA_EXCESO_KG = 0.01 kg.
    """
    from app.services import coil_math
    from app.services.inventory import create_retal, link_coil
    from app.services.medicion import medir_bobina
    from tests.helpers import make_material, make_order, make_order_line, make_stock_item

    def _montada_con_codigo(db_session, tenant, codigo):
        material = make_material(db_session, tenant, code=codigo, cost=2.0)
        bobina = make_stock_item(
            db_session, tenant, material, cantidad=1000.0, lote=f"L-{codigo}", ancho=122, espesor=0.5
        )
        orden = make_order(db_session, tenant, numero=f"OP-{codigo}")
        linea = make_order_line(db_session, orden, workstation="LINEA-1")
        linea.active_coil_id = bobina.id
        linea.active_coil_code = bobina.coil_id
        bobina.cantidad_disponible = Decimal("600")
        db_session.commit()
        return bobina, orden, linea

    # Test 1: 600.005 kg en create_retal -> aceptado
    bobina, orden, linea = _montada_con_codigo(db_session, tenant, "M-TOPE-1")
    _mide(monkeypatch, 600.005)
    res = create_retal(
        db_session, tenant.id, user.id,
        stock_item_id=bobina.id, radio_mm=50.0, order_id=orden.id, line_id=linea.id,
    )
    assert res["success"] is True, f"600.005 kg debería aceptarse: {res}"

    # Test 2: 600.02 kg en create_retal -> rechazado
    bobina, orden, linea = _montada_con_codigo(db_session, tenant, "M-TOPE-2")
    _mide(monkeypatch, 600.02)
    with pytest.raises(ValueError, match=r"600.*kg o inferior|vuelve a medir"):
        create_retal(
            db_session, tenant.id, user.id,
            stock_item_id=bobina.id, radio_mm=50.0, order_id=orden.id, line_id=linea.id,
        )
    db_session.refresh(bobina)
    assert bobina.cantidad_disponible == Decimal("600")

    # Test 3: 600.005 kg en medir_bobina -> aceptado
    bobina, orden, linea = _montada_con_codigo(db_session, tenant, "M-TOPE-3")
    _mide(monkeypatch, 600.005)
    res = medir_bobina(
        db_session, tenant.id, user.id,
        stock_item_id=bobina.id, radio_mm=50.0, order_id=orden.id, line_id=linea.id,
    )
    assert res["success"] is True, f"medir_bobina 600.005 kg debería aceptarse: {res}"

    # Test 4: 600.02 kg en medir_bobina -> rechazado
    bobina, orden, linea = _montada_con_codigo(db_session, tenant, "M-TOPE-4")
    _mide(monkeypatch, 600.02)
    with pytest.raises(ValueError, match=r"600.*kg o inferior|vuelve a medir"):
        medir_bobina(
            db_session, tenant.id, user.id,
            stock_item_id=bobina.id, radio_mm=50.0, order_id=orden.id, line_id=linea.id,
        )
    db_session.refresh(bobina)
    assert bobina.cantidad_disponible == Decimal("600")

