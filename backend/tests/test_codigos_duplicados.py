"""Reparación de códigos de bobina del simulador (SIM-…) repetidos (T-050).

Antes de que el código fuese único, el simulador dejó pares con el mismo código en
la demo. La reparación renombra los repetidos sin borrar nada y es idempotente.
"""

from datetime import UTC, datetime, timedelta

from app.models import StockItem
from app.services.inventory import reparar_codigos_duplicados_demo
from tests.helpers import (
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
    make_tenant,
)

HOY = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def _bobina(db, tenant, material, codigo, dias_atras, lote):
    return make_stock_item(
        db, tenant, material, cantidad=100, lote=lote, coil_id=codigo,
        fecha_entrada=HOY - timedelta(days=dias_atras),
    )


def test_renombra_los_repetidos_y_conserva_el_codigo_de_la_mas_antigua(db_session, tenant):
    material = make_material(db_session, tenant)
    vieja = _bobina(db_session, tenant, material, "SIM-ACERO-20261106105955", 5, "L1")
    media = _bobina(db_session, tenant, material, "SIM-ACERO-20261106105955", 3, "L2")
    nueva = _bobina(db_session, tenant, material, "SIM-ACERO-20261106105955", 1, "L3")

    n = reparar_codigos_duplicados_demo(db_session)

    assert n == 2
    for b in (vieja, media, nueva):
        db_session.refresh(b)
    assert vieja.coil_id == "SIM-ACERO-20261106105955"
    assert media.coil_id == "SIM-ACERO-20261106105955-2"
    assert nueva.coil_id == "SIM-ACERO-20261106105955-3"
    codigos = [c for (c,) in db_session.query(StockItem.coil_id).all()]
    assert len(codigos) == len(set(codigos))


def test_es_idempotente_y_no_toca_bobinas_sin_repetir(db_session, tenant):
    material = make_material(db_session, tenant)
    _bobina(db_session, tenant, material, "SIM-A-1", 4, "L1")
    _bobina(db_session, tenant, material, "SIM-A-1", 2, "L2")
    suelta = _bobina(db_session, tenant, material, "SIM-B-1", 2, "L3")

    assert reparar_codigos_duplicados_demo(db_session) == 1
    assert reparar_codigos_duplicados_demo(db_session) == 0
    db_session.refresh(suelta)
    assert suelta.coil_id == "SIM-B-1"


def test_solo_toca_codigos_del_simulador(db_session, tenant):
    material = make_material(db_session, tenant)
    a = _bobina(db_session, tenant, material, "REAL-001", 4, "L1")
    b = _bobina(db_session, tenant, material, "REAL-001", 2, "L2")

    assert reparar_codigos_duplicados_demo(db_session) == 0
    db_session.refresh(a)
    db_session.refresh(b)
    assert a.coil_id == b.coil_id == "REAL-001"


def test_no_pisa_un_sufijo_que_ya_existe(db_session, tenant):
    material = make_material(db_session, tenant)
    _bobina(db_session, tenant, material, "SIM-X", 6, "L1")
    _bobina(db_session, tenant, material, "SIM-X", 4, "L2")
    ocupada = _bobina(db_session, tenant, material, "SIM-X-2", 2, "L3")

    reparar_codigos_duplicados_demo(db_session)

    db_session.refresh(ocupada)
    assert ocupada.coil_id == "SIM-X-2"
    codigos = [c for (c,) in db_session.query(StockItem.coil_id).all()]
    assert sorted(codigos) == ["SIM-X", "SIM-X-2", "SIM-X-3"]


def test_una_linea_con_la_bobina_montada_sigue_el_nuevo_codigo(db_session, tenant):
    material = make_material(db_session, tenant)
    _bobina(db_session, tenant, material, "SIM-M-1", 6, "L1")
    montada = _bobina(db_session, tenant, material, "SIM-M-1", 2, "L2")
    orden = make_order(db_session, tenant, numero="OP-REP")
    linea = make_order_line(db_session, orden, material=material)
    linea.active_coil_id = montada.id
    linea.active_coil_code = "SIM-M-1"
    db_session.commit()

    reparar_codigos_duplicados_demo(db_session)

    db_session.refresh(linea)
    assert linea.active_coil_code == "SIM-M-1-2"


def test_con_tenant_solo_repara_esa_planta(db_session, tenant):
    material = make_material(db_session, tenant)
    _bobina(db_session, tenant, material, "SIM-T-1", 4, "L1")
    _bobina(db_session, tenant, material, "SIM-T-1", 2, "L2")
    otra = make_tenant(db_session, name="Otra planta", slug="otra-planta-rep")
    material_otra = make_material(db_session, otra, code="ACERO-OT")
    o1 = _bobina(db_session, otra, material_otra, "SIM-O-1", 4, "M1")
    o2 = _bobina(db_session, otra, material_otra, "SIM-O-1", 2, "M2")

    assert reparar_codigos_duplicados_demo(db_session, tenant_id=tenant.id) == 1

    db_session.refresh(o1)
    db_session.refresh(o2)
    assert o1.coil_id == o2.coil_id == "SIM-O-1"

