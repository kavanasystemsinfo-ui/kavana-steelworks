"""Tests TDD de los modelos Product y ProductComponent (BOM)."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Material, Product, ProductComponent, Tenant
from app.models.quality import ManufacturingModel


def _tenant(db_session, slug="test-products") -> Tenant:
    t = Tenant(
        name="Test",
        slug=slug,
        status="active",
        is_active=True,
        auth={},
        theme={},
        finances={},
        sequences_config={},
    )
    db_session.add(t)
    db_session.commit()
    return t


def _pieza(db_session, tenant, code="MONTANTE-P50") -> ManufacturingModel:
    m = ManufacturingModel(tenant_id=tenant.id, code=code, name="Montante", is_active=True)
    db_session.add(m)
    db_session.commit()
    return m


def _material(db_session, tenant) -> Material:
    mat = Material(
        tenant_id=tenant.id,
        code="TORN-M8",
        name="Tornillo M8",
        unit="uds",
        density=7850,
    )
    db_session.add(mat)
    db_session.commit()
    return mat


def test_product_crea_con_componente_de_pieza(db_session):
    tenant = _tenant(db_session)
    pieza = _pieza(db_session, tenant)

    prod = Product(tenant_id=tenant.id, code="EST-PORTICO", name="Rack Portico")
    db_session.add(prod)
    db_session.flush()
    db_session.add(
        ProductComponent(
            product_id=prod.id,
            manufacturing_model_id=pieza.id,
            quantity=8,
            unit="uds",
            position=1,
        )
    )
    db_session.commit()

    guardado = db_session.scalar(select(Product).where(Product.code == "EST-PORTICO"))
    assert guardado is not None
    assert len(guardado.components) == 1
    assert guardado.components[0].manufacturing_model_id == pieza.id
    assert float(guardado.components[0].quantity) == 8.0


def test_componente_admite_material_directo(db_session):
    tenant = _tenant(db_session)
    mat = _material(db_session, tenant)

    prod = Product(tenant_id=tenant.id, code="EST-X", name="X")
    db_session.add(prod)
    db_session.flush()
    db_session.add(
        ProductComponent(product_id=prod.id, material_id=mat.id, quantity=64, unit="uds")
    )
    db_session.commit()

    comp = db_session.scalar(select(ProductComponent).where(ProductComponent.material_id == mat.id))
    assert comp is not None
    assert comp.manufacturing_model_id is None


def test_componente_con_ambos_refes_viola_check(db_session):
    """XOR: o pieza o material, nunca ambos."""
    tenant = _tenant(db_session)
    pieza = _pieza(db_session, tenant)
    mat = _material(db_session, tenant)

    prod = Product(tenant_id=tenant.id, code="EST-Y", name="Y")
    db_session.add(prod)
    db_session.flush()
    db_session.add(
        ProductComponent(
            product_id=prod.id,
            manufacturing_model_id=pieza.id,
            material_id=mat.id,
            quantity=1,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_componente_sin_ningun_ref_viola_check(db_session):
    tenant = _tenant(db_session)
    prod = Product(tenant_id=tenant.id, code="EST-Z", name="Z")
    db_session.add(prod)
    db_session.flush()
    db_session.add(ProductComponent(product_id=prod.id, quantity=1))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_code_de_producto_unico_por_tenant(db_session):
    tenant = _tenant(db_session, slug="t1")
    otro = _tenant(db_session, slug="t2")

    db_session.add(Product(tenant_id=tenant.id, code="EST-UNO", name="A"))
    db_session.commit()
    # Mismo code en OTRO tenant: permitido (unicidad por tenant)
    db_session.add(Product(tenant_id=otro.id, code="EST-UNO", name="B"))
    db_session.commit()

    db_session.add(Product(tenant_id=tenant.id, code="EST-UNO", name="C"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_borrar_producto_borra_componentes(db_session):
    tenant = _tenant(db_session)
    pieza = _pieza(db_session, tenant)

    prod = Product(tenant_id=tenant.id, code="EST-DEL", name="D")
    db_session.add(prod)
    db_session.flush()
    db_session.add(
        ProductComponent(product_id=prod.id, manufacturing_model_id=pieza.id, quantity=1)
    )
    db_session.commit()

    db_session.delete(prod)
    db_session.commit()
    assert db_session.scalar(select(ProductComponent)) is None
