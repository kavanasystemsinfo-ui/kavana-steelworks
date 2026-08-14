"""Tests TDD del servicio de recepción de materiales (spec 06).

- Alta de bobina: crea stock_item con atributos estándar (peso, dimensiones,
  heat number, grado, proveedor) y registra Kardex de entrada (GRN).
- Entrada directa: la bobina entra en estado 'activo' (decisión Jorge).
- Coste: soporta coste real de compra y coste estándar (ambos).
- Ubicación (putaway): se asigna la ubicación física al recibir.
"""

from decimal import Decimal

from app.models import MaterialTransaction
from tests.helpers import make_material


def _receive(
    db,
    tenant,
    user,
    material,
    *,
    peso=800.0,
    lote="L-RECEP",
    ancho=122.0,
    espesor=0.5,
    coste_real=None,
    ubicacion="ALMACEN-1",
    heat_number="H-12345",
    grado="DX51D",
    supplier_coil_id="SUP-999",
):
    from app.services.receiving import receive_coil

    return receive_coil(
        db,
        tenant.id,
        user.id,
        material_id=material.id,
        lote=lote,
        coil_id=f"COIL-{lote}",
        peso=peso,
        width_mm=ancho,
        thickness_mm=espesor,
        coste_real=coste_real,
        ubicacion=ubicacion,
        heat_number=heat_number,
        grado_acero=grado,
        supplier_coil_id=supplier_coil_id,
    )


def test_recepcion_crea_bobina_activa(db_session, tenant, user):
    """La bobina entra en estado activo con sus atributos estándar."""
    material = make_material(db_session, tenant, cost=1.5)
    bobina = _receive(db_session, tenant, user, material)

    assert bobina.estado == "activo"  # entrada directa (decisión Jorge)
    assert bobina.cantidad_inicial == 800.0
    assert bobina.cantidad_disponible == 800.0
    assert bobina.heat_number == "H-12345"
    assert bobina.grado_acero == "DX51D"
    assert bobina.supplier_coil_id == "SUP-999"
    assert bobina.ubicacion == "ALMACEN-1"
    assert bobina.material_id == material.id


def test_recepcion_registra_kardex_entrada(db_session, tenant, user):
    """El GRN deja una MaterialTransaction tipo entrada_compra."""
    material = make_material(db_session, tenant, cost=1.5)
    bobina = _receive(db_session, tenant, user, material, peso=500.0)

    tx = (
        db_session.query(MaterialTransaction)
        .filter(MaterialTransaction.stock_item_id == bobina.id)
        .all()
    )
    assert len(tx) == 1
    assert tx[0].tipo == "entrada_compra"
    assert tx[0].cantidad == 500.0
    assert tx[0].cantidad_anterior == 0
    assert tx[0].cantidad_nueva == 500.0


def test_recepcion_soporta_coste_real_y_estandar(db_session, tenant, user):
    """Con coste_real usa costing_method real; sin él, estándar del material."""
    material = make_material(db_session, tenant, cost=1.5)

    con_real = _receive(db_session, tenant, user, material, coste_real=2.1)
    assert con_real.costing_method == "real"
    assert con_real.coste_por_unidad == Decimal("2.1")

    material2 = make_material(db_session, tenant, cost=1.5, code="ACERO-02")
    sin_real = _receive(db_session, tenant, user, material2, lote="L-ESTANDAR", coste_real=None)
    assert sin_real.costing_method == "standard"
    assert sin_real.coste_por_unidad == 1.5


def test_recepcion_actualiza_stock_del_material(db_session, tenant, user):
    """stock_current del material suma el peso recibido."""
    material = make_material(db_session, tenant, cost=1.5)
    material.stock_current = 0
    db_session.commit()

    _receive(db_session, tenant, user, material, peso=300.0)

    db_session.refresh(material)
    assert material.stock_current == 300.0
