"""Tests de etiqueta QR y putaway (spec 06, pasos 4 y 6).

- La etiqueta de bobina codifica los datos escaneables (coil_id, lote,
  material, peso, dimensiones, ubicación).
- La ubicación (putaway) se puede actualizar y el cambio queda en Kardex
  como traslado (tipo 'traslado', cantidad 0, patrón del v2).
"""

import json

from app.models import MaterialTransaction
from app.services.receiving import receive_coil
from tests.helpers import make_material


def test_etiqueta_qr_codifica_datos_de_bobina(db_session, tenant, user):
    """La etiqueta QR contiene los datos necesarios para el escaneo."""
    material = make_material(db_session, tenant, cost=1.5)
    bobina = receive_coil(
        db_session,
        tenant.id,
        user.id,
        material_id=material.id,
        lote="L-ETIQ",
        peso=700.0,
        width_mm=122.0,
        thickness_mm=0.5,
        ubicacion="ALMACEN-1",
    )

    from app.services.receiving import build_label

    label = build_label(bobina)
    datos = json.loads(label["qr_data"])

    assert datos["coil_id"] == "COIL-L-ETIQ"
    assert datos["lote"] == "L-ETIQ"
    assert datos["material_id"] == str(material.id)
    assert datos["peso"] == "700.0000"
    assert datos["ancho_mm"] == "122.000"
    assert datos["espesor_mm"] == "0.500"
    assert datos["ubicacion"] == "ALMACEN-1"
    assert "qr_svg" in label  # representación para imprimir


def test_putaway_actualiza_ubicacion_con_kardex(db_session, tenant, user):
    """Cambiar la ubicación registra un traslado en el Kardex."""
    material = make_material(db_session, tenant, cost=1.5)
    bobina = receive_coil(
        db_session,
        tenant.id,
        user.id,
        material_id=material.id,
        lote="L-UBI",
        peso=600.0,
        ubicacion="ALMACEN-1",
    )

    from app.services.receiving import move_coil

    move_coil(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        nueva_ubicacion="LINEA-2",
    )

    db_session.refresh(bobina)
    assert bobina.ubicacion == "LINEA-2"

    traslados = (
        db_session.query(MaterialTransaction)
        .filter(
            MaterialTransaction.stock_item_id == bobina.id,
            MaterialTransaction.tipo == "traslado",
        )
        .all()
    )
    assert len(traslados) == 1
    assert traslados[0].cantidad == 0
    assert "LINEA-2" in traslados[0].motivo
