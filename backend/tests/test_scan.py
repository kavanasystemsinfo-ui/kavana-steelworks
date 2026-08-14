"""Tests TDD del escaneo de bobina (anexo A, flujo del operario).

Contrato:
- Buscar por coil_id o lote devuelve la bobina con material, dimensiones
  y peso (modo automático: el sistema auto calcula).
- Si no existe, error claro.
"""


def test_scan_por_coil_id_devuelve_datos_completos(db_session, tenant, user):
    from tests.helpers import make_material, make_stock_item

    material = make_material(db_session, tenant, cost=2.0)
    bobina = make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=800.0,
        lote="L-SCAN",
        ancho=122.0,
        espesor=0.5,
        coste=2.0,
    )

    from app.services.inventory import find_coil

    resultado = find_coil(
        db_session,
        tenant.id,
        coil_id=bobina.coil_id,
    )

    assert resultado is not None
    assert resultado["lote"] == "L-SCAN"
    assert resultado["coil_id"] == bobina.coil_id
    assert resultado["peso_kg"] == 800.0
    assert resultado["ancho_mm"] == 122.0
    assert resultado["espesor_mm"] == 0.5
    assert resultado["material_code"] == "ACERO-01"
    assert resultado["estado"] == "activo"
    # Modo manual: el sistema rellena material y dimensiones, el operario
    # introduce peso y lote desde la etiqueta física.
    assert resultado["modo"] in ("auto", "manual")


def test_scan_por_lote_funciona(db_session, tenant, user):
    from tests.helpers import make_material, make_stock_item

    material = make_material(db_session, tenant, cost=2.0)
    make_stock_item(
        db_session,
        tenant,
        material,
        cantidad=500.0,
        lote="L-ETIQUETA",
        ancho=100.0,
        espesor=0.4,
        coste=2.0,
    )

    from app.services.inventory import find_coil

    resultado = find_coil(
        db_session,
        tenant.id,
        lote="L-ETIQUETA",
    )
    assert resultado is not None
    assert resultado["peso_kg"] == 500.0


def test_scan_bobina_inexistente_devuelve_none(db_session, tenant, user):
    from app.services.inventory import find_coil

    resultado = find_coil(
        db_session,
        tenant.id,
        coil_id="NO-EXISTE",
    )
    assert resultado is None
