"""Tests TDD: validación de material por características al vincular bobina.

Visión de Jorge (anexo A, punto 8): el sistema sabe qué material gasta el
modelo según la orden y NO deja vincular una bobina de características
incompatibles (ancho, espesor y tipo de material: decapado, galva, aluminio).

Reglas:
- Si la línea de orden declara material_id, la bobina DEBE ser de ese material.
- Si el material requerido tiene dimensiones nominales y la bobina las tiene,
  ancho y espesor deben casar dentro de la tolerancia industrial.
- Línea SIN material declarado: no valida (compatibilidad hacia atrás).
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import Material
from tests.helpers import make_material, make_order, make_order_line, make_stock_item


def _bobina(db, tenant, material, peso=800.0, lote="L-COMP", ancho=1220.0, espesor=1.2):
    return make_stock_item(
        db,
        tenant,
        material,
        cantidad=peso,
        lote=lote,
        fecha_entrada=datetime.now(UTC) - timedelta(days=1),
        coste=2.0,
        ancho=ancho,
        espesor=espesor,
    )


def _material_con_dimensiones(db, tenant, code="ACERO-DC01", ancho=1220.0, espesor=1.2):
    m = Material(
        tenant_id=tenant.id,
        code=code,
        name=f"Bobina acero decapado {espesor}x{ancho}",
        cost_per_unit=2.0,
        dimension_ancho_mm=ancho,
        dimension_espesor_mm=espesor,
        unit="kg",
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def test_link_rechaza_bobina_de_otro_material(db_session, tenant, user):
    """La línea requiere material A; una bobina de material B NO vincula."""
    from app.services.inventory import link_coil

    requerido = _material_con_dimensiones(db_session, tenant, code="DECAPADO-01")
    otro = _material_con_dimensiones(db_session, tenant, code="GALVA-01")
    bobina = _bobina(db_session, tenant, otro)
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order, material=requerido)

    with pytest.raises(ValueError, match="[Mm]aterial"):
        link_coil(
            db_session,
            tenant.id,
            user.id,
            stock_item_id=bobina.id,
            order_id=order.id,
            line_id=line.id,
        )


def test_link_acepta_bobina_del_mismo_material(db_session, tenant, user):
    """La bobina del material requerido vincula con normalidad."""
    from app.services.inventory import link_coil

    requerido = _material_con_dimensiones(db_session, tenant)
    bobina = _bobina(db_session, tenant, requerido)
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order, material=requerido)

    resultado = link_coil(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        order_id=order.id,
        line_id=line.id,
    )

    assert resultado["success"] is True


def test_link_rechaza_ancho_incompatible(db_session, tenant, user):
    """Mismo material pero ancho de banda fuera de tolerancia → bloquea."""
    from app.services.inventory import link_coil

    requerido = _material_con_dimensiones(db_session, tenant, ancho=1220.0, espesor=1.2)
    bobina = _bobina(db_session, tenant, requerido, ancho=950.0, espesor=1.2)
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order, material=requerido)

    with pytest.raises(ValueError, match="[Aa]ncho"):
        link_coil(
            db_session,
            tenant.id,
            user.id,
            stock_item_id=bobina.id,
            order_id=order.id,
            line_id=line.id,
        )


def test_link_rechaza_espesor_incompatible(db_session, tenant, user):
    """Mismo material pero espesor fuera de tolerancia → bloquea."""
    from app.services.inventory import link_coil

    requerido = _material_con_dimensiones(db_session, tenant, ancho=1220.0, espesor=1.2)
    bobina = _bobina(db_session, tenant, requerido, ancho=1220.0, espesor=3.0)
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order, material=requerido)

    with pytest.raises(ValueError, match="[Ee]spesor"):
        link_coil(
            db_session,
            tenant.id,
            user.id,
            stock_item_id=bobina.id,
            order_id=order.id,
            line_id=line.id,
        )


def test_link_acepta_dimensiones_dentro_de_tolerancia(db_session, tenant, user):
    """Variación de espesor por tolerancia comercial de laminación no bloquea."""
    from app.services.inventory import link_coil

    requerido = _material_con_dimensiones(db_session, tenant, ancho=1220.0, espesor=1.2)
    bobina = _bobina(db_session, tenant, requerido, ancho=1220.0, espesor=1.24)
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order, material=requerido)

    resultado = link_coil(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        order_id=order.id,
        line_id=line.id,
    )

    assert resultado["success"] is True


def test_link_sin_material_declarado_no_valida(db_session, tenant, user):
    """Línea sin material_id (compatibilidad): vincula cualquier bobina."""
    from app.services.inventory import link_coil

    material = make_material(db_session, tenant)
    bobina = _bobina(db_session, tenant, material)
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order)  # sin material

    resultado = link_coil(
        db_session,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        order_id=order.id,
        line_id=line.id,
    )

    assert resultado["success"] is True
