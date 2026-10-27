"""Tests TDD del seed de estanterías (catálogo de productos + BOM)."""

import pytest
from sqlalchemy import select

from app.models import (
    Material,
    Order,
    Product,
    ProductComponent,
    StockItem,
    Tenant,
    Workstation,
    WorkstationGroup,
)
from app.models.quality import ManufacturingModel
from app.services.seed_demo import seed_demo
from app.services.seed_estanterias import seed_estanterias


def _sembrar(db):
    seed_demo(db)
    return seed_estanterias(db)


def test_renombra_tenant_a_kavana_estanterias(db_session):
    _sembrar(db_session)
    tenant = db_session.scalar(select(Tenant).where(Tenant.slug == "demo"))
    assert tenant.name == "Kavana Estanterías"
    assert tenant.theme["branding"]["companyName"] == "Kavana Estanterías"


def test_crea_12_productos_con_bom(db_session):
    _sembrar(db_session)
    productos = db_session.scalars(select(Product)).all()
    assert len(productos) == 12
    codigos = {p.code for p in productos}
    assert "EST-PORTICO" in codigos
    assert "EST-ALTILLO" in codigos

    # Cada producto tiene BOM con al menos 3 componentes
    for p in productos:
        assert len(p.components) >= 3, f"{p.code} sin BOM"


def test_bom_referencia_modelos_y_materiales_reales(db_session):
    _sembrar(db_session)
    modelos = set(db_session.scalars(select(ManufacturingModel.id)).all())
    materiales = set(db_session.scalars(select(Material.id)).all())

    componentes = db_session.scalars(select(ProductComponent)).all()
    assert len(componentes) >= 30

    con_pieza = con_material = 0
    for c in componentes:
        if c.manufacturing_model_id is not None:
            assert c.manufacturing_model_id in modelos
            con_pieza += 1
        else:
            assert c.material_id in materiales
            con_material += 1
        assert c.quantity > 0
    assert con_pieza > 0 and con_material > 0, "BOM debe mezclar piezas y materiales"


def test_crea_piezas_con_plan_de_calidad(db_session):
    _sembrar(db_session)
    piezas = db_session.scalars(select(ManufacturingModel)).all()
    assert len(piezas) >= 12
    codes = {m.code for m in piezas}
    assert {"MONTANTE-P50", "LARGUERO-E27", "BANDEJA-P45"} <= codes
    for m in piezas:
        assert len(m.quality_plan) >= 2, f"{m.code} sin autocontroles"


def test_crea_materias_primas_con_stock(db_session):
    _sembrar(db_session)
    tenant = db_session.scalar(select(Tenant).where(Tenant.slug == "demo"))
    materiales = db_session.scalars(select(Material).where(Material.tenant_id == tenant.id)).all()
    assert len(materiales) >= 8

    bobinas = db_session.scalars(select(StockItem).where(StockItem.tenant_id == tenant.id)).all()
    assert len(bobinas) >= 12
    for b in bobinas:
        assert b.cantidad_disponible > 0
        assert b.estado == "activo"


def test_crea_grupos_y_puestos_de_trabajo(db_session):
    _sembrar(db_session)
    tenant = db_session.scalar(select(Tenant).where(Tenant.slug == "demo"))
    grupos = db_session.scalars(
        select(WorkstationGroup).where(WorkstationGroup.tenant_id == tenant.id)
    ).all()
    nombres = {g.name for g in grupos}
    assert {"Corte", "Punzonado", "Doblado", "Soldadura", "Montaje"} <= nombres

    puestos = db_session.scalars(
        select(Workstation).where(Workstation.tenant_id == tenant.id)
    ).all()
    # 3 existentes (LINEA-1..3) + nuevas
    assert len(puestos) >= 10
    # Todas las líneas existentes siguen intactas
    codes = {w.code for w in puestos}
    assert {"LINEA-1", "LINEA-2", "LINEA-3"} <= codes
    # Los puestos nuevos tienen grupo (proceso)
    nuevos = [w for w in puestos if w.code not in {"LINEA-1", "LINEA-2", "LINEA-3"}]
    assert len(nuevos) >= 7
    assert all(w.group_id is not None for w in nuevos)


def test_crea_ordenes_activas_con_lineas(db_session):
    _sembrar(db_session)
    tenant = db_session.scalar(select(Tenant).where(Tenant.slug == "demo"))
    ordenes = db_session.scalars(select(Order).where(Order.tenant_id == tenant.id)).all()
    activas = [o for o in ordenes if o.estado == "active"]
    assert len(ordenes) >= 3
    assert len(activas) >= 2
    for o in activas:
        assert len(o.lines) >= 1
        for ln in o.lines:
            assert ln.workstation_id is not None
            assert ln.material_id is not None


def test_idempotente(db_session):
    primero = _sembrar(db_session)
    segundo = seed_estanterias(db_session)
    db_session.commit()

    assert primero["created"] is True
    assert segundo["created"] is False
    assert db_session.scalar(select(Product)) is not None
    assert db_session.query(Product).count() == 12
    boms_1 = db_session.query(ProductComponent).count()
    assert boms_1 >= 30
    # Sin duplicados de bobina
    bobs_antes = db_session.query(StockItem).count()
    seed_estanterias(db_session)
    assert db_session.query(StockItem).count() == bobs_antes
    assert db_session.query(ProductComponent).count() == boms_1


def test_seed_demo_y_estanterias_encadenados(db_session):
    """seed_demo seguido de seed_estanterias no duplica el tenant."""
    seed_demo(db_session)
    seed_estanterias(db_session)
    seed_demo(db_session)  # segundo arranque del contenedor
    seed_estanterias(db_session)

    tenants = db_session.query(Tenant).filter(Tenant.slug == "demo").all()
    assert len(tenants) == 1
    assert db_session.query(Product).count() == 12


def test_rename_con_slug_legacy_de_produccion(db_session):
    """Produccion real: el tenant se creo con slug demo-aceros, no demo.

    El seed debe encontrarlo por slug legacy o por name, renombrarlo y no
    duplicar el tenant.
    """
    db_session.add(
        Tenant(
            name="Demo Aceros",
            slug="demo-aceros",
            status="active",
            is_active=True,
            auth={},
            theme={"branding": {"companyName": "Demo Aceros"}},
            finances={},
            sequences_config={},
        )
    )
    db_session.commit()

    seed_demo(db_session)
    resultado = seed_estanterias(db_session)

    assert resultado["created"] is True
    tenants = db_session.query(Tenant).all()
    assert len(tenants) == 1, "no debe duplicar el tenant"
    assert tenants[0].name == "Kavana Estanterías"
    assert db_session.query(Product).count() == 12


# ── Costes de la demo: derivados de los datos, nunca escritos a mano ──────


def _orden(db, numero):
    return db.scalar(select(Order).where(Order.numero == numero))


def test_objetivo_de_material_en_kg_no_en_piezas(db_session):
    _sembrar(db_session)
    orden = _orden(db_session, "OP-EST-2600")
    puntal = next(ln for ln in orden.lines if ln.linea_numero == 1)
    # 100 puntales de 265 x 1,8 mm x 3,0 m con densidad calibrada ≈ 11,13 kg/ud
    assert float(puntal.target_material_qty) == pytest.approx(1113.0, abs=1.0)


def test_orden_historica_tiene_coste_en_sus_lineas(db_session):
    from app.services.costes import costes_por_orden

    _sembrar(db_session)
    orden = _orden(db_session, "OP-EST-2600")
    tenant = db_session.scalar(select(Tenant).where(Tenant.slug == "demo"))

    for linea in orden.lines:
        assert float(linea.real_material_cost) > 0
        assert float(linea.real_time) > 0
        assert float(linea.real_cost) > float(linea.real_material_cost)  # + mano de obra

    fila = next(f for f in costes_por_orden(db_session, tenant.id) if f["numero"] == "OP-EST-2600")
    assert fila["real_total"] == pytest.approx(float(orden.real_total_cost), abs=0.01)
    assert fila["estimado_material"] is not None
    assert fila["mano_obra"] > 0


def test_puestos_de_la_demo_tienen_ritmo_nominal_sin_pisar_el_configurado(db_session):
    from app.services.seed_estanterias import RITMOS_DEMO

    _sembrar(db_session)
    puestos = db_session.scalars(select(Workstation)).all()
    for puesto in puestos:
        if puesto.code in RITMOS_DEMO:
            assert float(puesto.piezas_hora_nominal) == float(RITMOS_DEMO[puesto.code])

    # Un ritmo cambiado desde Admin sobrevive a la siguiente siembra
    punz = next(p for p in puestos if p.code == "PUNZ-1")
    punz.piezas_hora_nominal = 55
    db_session.commit()
    seed_estanterias(db_session)
    db_session.refresh(punz)
    assert float(punz.piezas_hora_nominal) == 55


def test_reparar_costes_demo_corrige_siembras_antiguas_y_es_idempotente(db_session):
    from app.services.seed_estanterias import reparar_costes_demo

    _sembrar(db_session)
    tenant = db_session.scalar(select(Tenant).where(Tenant.slug == "demo"))
    orden = _orden(db_session, "OP-EST-2600")
    linea = next(ln for ln in orden.lines if ln.linea_numero == 1)
    esperado = (float(linea.target_material_qty), float(linea.real_cost))

    # Estado de una siembra antigua desplegada: piezas como kg y sin costes
    linea.target_material_qty = linea.total_quantity
    linea.real_material_cost = 0
    linea.real_material_qty = 0
    linea.real_time = 0
    linea.real_cost = 0
    db_session.commit()

    reparar_costes_demo(db_session, tenant.id)
    reparar_costes_demo(db_session, tenant.id)
    db_session.commit()
    db_session.refresh(linea)

    assert float(linea.target_material_qty) == pytest.approx(esperado[0])
    assert float(linea.real_cost) == pytest.approx(esperado[1])
