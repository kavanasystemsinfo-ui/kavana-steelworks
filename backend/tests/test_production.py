"""Tests TDD de record_production (spec 02 3.4 + spec 01 3.12).

Contrato:
- Solo rol operator puede registrar producción.
- incremental_quantity >= 0; si 0 y hours_worked <= 0 → error.
- Auto-consumo: kg por pieza por density_formula (ancho/espesor del lote,
  largo de meters_per_piece, densidad calibrada Kavana), con fallback
  meters_legacy y bom_static.
- Modo auditoría (línea con bobina activa): consume por burbuja de
  vinculación + priority coil; el fallo BLOQUEA la producción.
- Modo simple (sin bobina): FIFO global; el fallo NO bloquea (produce sin
  descuento, nunca consumos fantasma).
- GUARDIA DE SEGURIDAD: kilos teóricos acumulados no pueden superar los
  reales vinculados + max(15%, 150kg).
- produced_quantity >= total_quantity → línea completed.
- WIP waterfall: una línea no puede producir más piezas que las que el paso
  anterior ha entregado.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tests.helpers import make_material, make_order, make_order_line, make_stock_item


def _setup(db, tenant, user, *, peso=800.0, ancho=122.0, espesor=0.5, meters=2.0, total=10.0):
    """Bobina vinculada a la orden + línea (modo auditoría listo)."""
    from app.services.inventory import link_coil

    material = make_material(db, tenant, code="ACERO-PROD", cost=2.0)
    bobina = make_stock_item(
        db,
        tenant,
        material,
        cantidad=peso,
        lote="L-PROD",
        fecha_entrada=datetime.now(UTC) - timedelta(days=1),
        coste=2.0,
        ancho=ancho,
        espesor=espesor,
    )
    order = make_order(db, tenant, numero="OP-PROD")
    line = make_order_line(db, order, workstation="LINEA-1", total_quantity=total)
    line.meters_per_piece = Decimal(str(meters))
    db.commit()

    link_coil(db, tenant.id, user.id, stock_item_id=bobina.id, order_id=order.id, line_id=line.id)
    db.refresh(bobina)
    return material, bobina, order, line


def test_produccion_solo_operario(db_session, tenant, user):
    """Un usuario sin rol operator no puede registrar producción."""
    from app.models import User
    from app.services.production import record_production

    admin = User(
        tenant_id=tenant.id,
        email="admin@test.local",
        name="Admin",
        password_hash="x",
        role="admin",
    )
    db_session.add(admin)
    db_session.commit()

    material, bobina, order, line = _setup(db_session, tenant, user)

    with pytest.raises(ValueError, match="operario"):
        record_production(
            db_session,
            tenant.id,
            admin.id,
            order_id=order.id,
            line_id=line.id,
            incremental_quantity=1,
        )


def test_produccion_requiere_cantidad_o_horas(db_session, tenant, user):
    """Cantidad 0 y horas 0 es un error."""
    from app.services.production import record_production

    material, bobina, order, line = _setup(db_session, tenant, user)

    with pytest.raises(ValueError, match="cantidad u horas"):
        record_production(
            db_session,
            tenant.id,
            user.id,
            order_id=order.id,
            line_id=line.id,
            incremental_quantity=0,
            hours_worked=0,
        )


def test_produccion_auditoria_consume_por_burbuja(db_session, tenant, user):
    """Con bobina activa consume kg por density_formula y FIFO burbuja."""
    from app.models import MaterialConsumo
    from app.services.production import record_production

    material, bobina, order, line = _setup(db_session, tenant, user)

    record_production(
        db_session,
        tenant.id,
        user.id,
        order_id=order.id,
        line_id=line.id,
        incremental_quantity=5,
    )

    db_session.refresh(line)
    db_session.refresh(bobina)
    assert line.produced_quantity == 5
    # kg por pieza = 2 m * 0.122 m * 0.0005 m * 7780,7 kg/m³ ≈ 0,949 kg
    kg_por_pieza = 2.0 * 0.122 * 0.0005 * 7780.7
    consumido = 5 * kg_por_pieza
    assert float(bobina.cantidad_disponible) == pytest.approx(800.0 - consumido, abs=0.01)

    # MaterialConsumo con método density_formula y tipo auto_audit
    consumos = db_session.query(MaterialConsumo).filter(MaterialConsumo.order_id == order.id).all()
    assert len(consumos) == 1
    assert consumos[0].calculation_method == "density_formula"
    assert consumos[0].tipo == "auto_audit"
    assert consumos[0].produced_quantity == 5
    assert float(consumos[0].consumed_quantity) == pytest.approx(consumido, abs=0.01)


def test_produccion_sin_bobina_modo_simple_no_bloquea(db_session, tenant, user):
    """Sin bobina activa: FIFO global; si no hay stock, produce sin descuento."""
    from app.services.production import record_production

    make_material(db_session, tenant, code="ACERO-SIMPLE", cost=2.0)
    order = make_order(db_session, tenant, numero="OP-SIMPLE")
    line = make_order_line(db_session, order, workstation="LINEA-1", total_quantity=10.0)
    line.meters_per_piece = Decimal("2.0")
    db_session.commit()
    # Sin bobina, sin stock de material

    result = record_production(
        db_session,
        tenant.id,
        user.id,
        order_id=order.id,
        line_id=line.id,
        incremental_quantity=3,
    )

    db_session.refresh(line)
    # Produce igual (modo simple tolerante), sin descuento ni coste fantasma
    assert line.produced_quantity == 3
    assert result["consumed_amount"] == 0
    assert result["calculation_method"] == "none"
    assert float(line.real_material_qty) == 0


def test_produccion_completa_la_linea(db_session, tenant, user):
    """produced >= total → línea completed."""
    from app.services.production import record_production

    material, bobina, order, line = _setup(db_session, tenant, user, total=5.0)

    record_production(
        db_session,
        tenant.id,
        user.id,
        order_id=order.id,
        line_id=line.id,
        incremental_quantity=5,
    )

    db_session.refresh(line)
    assert line.produced_quantity == 5
    assert line.estado == "completed"


def test_produccion_guardia_seguridad_bloquea(db_session, tenant, user):
    """Los kilos teóricos acumulados no pueden superar los reales vinculados."""
    from app.services.production import record_production

    material, bobina, order, line = _setup(db_session, tenant, user, peso=100.0, total=1000.0)

    # kg por pieza ≈ 0,949; 100 kg reales + 15% → límite ≈ 250 kg ≈ 264 piezas
    with pytest.raises(ValueError, match="BLOQUEO DE SEGURIDAD"):
        record_production(
            db_session,
            tenant.id,
            user.id,
            order_id=order.id,
            line_id=line.id,
            incremental_quantity=300,
        )


def test_produccion_wip_waterfall(db_session, tenant, user):
    """La línea 2 no puede producir más de lo que entregó la línea 1."""
    from app.services.production import record_production

    make_material(db_session, tenant, code="ACERO-WIP", cost=2.0)
    order = make_order(db_session, tenant, numero="OP-WIP")
    line1 = make_order_line(
        db_session, order, workstation="LINEA-1", total_quantity=10.0, linea_numero=1
    )
    line1.produced_quantity = Decimal("4.0")
    line2 = make_order_line(
        db_session, order, workstation="LINEA-2", total_quantity=10.0, linea_numero=2
    )
    db_session.commit()

    with pytest.raises(ValueError, match="WIP"):
        record_production(
            db_session,
            tenant.id,
            user.id,
            order_id=order.id,
            line_id=line2.id,
            incremental_quantity=5,  # 5 > 4 disponibles del paso anterior
        )


def test_produccion_actualiza_coste_laboral(db_session, tenant, user):
    """hours_worked suma real_time y real_cost de la línea."""
    from app.services.production import record_production

    material, bobina, order, line = _setup(db_session, tenant, user)

    record_production(
        db_session,
        tenant.id,
        user.id,
        order_id=order.id,
        line_id=line.id,
        incremental_quantity=2,
        hours_worked=1.5,
    )

    db_session.refresh(line)
    assert float(line.real_time) == pytest.approx(90.0, abs=0.01)  # 1,5 h × 60
