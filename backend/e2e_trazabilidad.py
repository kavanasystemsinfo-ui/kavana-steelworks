"""E2E de trazabilidad ISO 9001 contra PostgreSQL real (spec 04).

Cubre el contrato completo:
1. record_production escribe el evento 'produce' con metadata real.
2. create_retal (fin de bobina) escribe 'scrap' con la reconciliación.
3. GET /api/v1/trace/orders/{id} devuelve la serie completa ordenada.
4. INMUTABILIDAD: UPDATE y DELETE sobre production_logs lanzan excepción
   (trigger BEFORE UPDATE OR DELETE, regla 1 de la spec).

Se ejecuta con: uv run python e2e_trazabilidad.py
"""

import subprocess
from datetime import UTC, datetime
from decimal import Decimal

# 1) Password en runtime (nunca literal, quirk de secrets)
pw = (
    subprocess.check_output(
        "docker inspect kavana-busroad-pg-test --format "
        "'{{range .Config.Env}}{{println .}}{{end}}'",
        shell=True,
    )
    .decode()
    .split("POSTGRES_PASSWORD=")[1]
    .split("\n")[0]
)
import os

os.environ["STEELWORKS_DATABASE_URL"] = (
    f"postgresql+psycopg://kavana:{pw}@localhost:5436/kavana_steelworks_mig"
)

from sqlalchemy import text  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    Material,
    Order,
    OrderLine,
    ProductionLog,
    StockItem,
    Tenant,
    User,
)
from app.services import inventory, production, traceability  # noqa: E402

print("1/7 drop_all + create_all + trigger inmutabilidad")
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
# El trigger vive en la migración Alembic (validada aparte con upgrade head);
# el E2E con create_all lo recrea para verificar el comportamiento real.
with engine.begin() as conn:
    conn.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION production_logs_block_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'production_logs es inmutable (ISO 9001): no se permite %',
                    TG_OP;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TRIGGER trg_production_logs_immutable
            BEFORE UPDATE OR DELETE ON production_logs
            FOR EACH ROW EXECUTE FUNCTION production_logs_block_mutation();
            """
        )
    )

db = SessionLocal()
try:
    print("2/7 seed tenant/usuario/material/bobina/orden")
    tenant = Tenant(name="E2E Trazabilidad")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    user = User(
        tenant_id=tenant.id,
        email="e2e.traz@test.local",
        name="Operario E2E",
        password_hash="x",
        role="operator",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    material = Material(
        tenant_id=tenant.id,
        code="ACERO-E2E",
        name="Acero E2E",
        cost_per_unit=Decimal("1.2"),
        density=Decimal("7850"),
        unit="kg",
        density_calibrada=Decimal("7.7807"),
    )
    db.add(material)
    db.commit()
    db.refresh(material)

    bobina = StockItem(
        tenant_id=tenant.id,
        material_id=material.id,
        lote="E2E-1",
        coil_id="COIL-E2E-001",
        cantidad_inicial=Decimal("800"),
        cantidad_disponible=Decimal("800"),
        unit="kg",
        coste_por_unidad=Decimal("1.2"),
        fecha_entrada=datetime.now(UTC),
        ubicacion="LINEA-1",
        estado="activo",
        es_pico=False,
        width_mm=Decimal("1000"),
        thickness_mm=Decimal("1.5"),
    )
    db.add(bobina)
    db.commit()
    db.refresh(bobina)

    orden = Order(tenant_id=tenant.id, numero="OP-E2E-TRAZ", estado="active")
    db.add(orden)
    db.commit()
    db.refresh(orden)
    linea = OrderLine(
        order_id=orden.id,
        linea_numero=1,
        workstation_id="LINEA-1",
        material_id=material.id,
        total_quantity=Decimal("100"),
        estado="pending",
        meters_per_piece=Decimal("1.0"),
    )
    db.add(linea)
    db.commit()
    db.refresh(linea)

    print("3/7 vincular bobina (cobro bulk)")
    res = inventory.link_coil(
        db,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        order_id=orden.id,
        line_id=linea.id,
    )
    assert res["success"] is True, res
    print(f"    bobina vinculada: {bobina.coil_id}")

    print("4/7 record_production (debe escribir log produce)")
    res = production.record_production(
        db,
        tenant.id,
        user.id,
        order_id=orden.id,
        line_id=linea.id,
        incremental_quantity=Decimal("10"),
        hours_worked=Decimal("1"),
        observaciones="Lote E2E trazabilidad",
    )
    assert res["success"] is True, res
    logs = db.query(ProductionLog).filter_by(order_id=orden.id).all()
    produce = [e for e in logs if e.action == "produce"]
    assert len(produce) == 1, f"esperado 1 log produce, hay {len(produce)}"
    p = produce[0]
    assert float(p.quantity) == 10, p.quantity
    assert p.metadata_["activeCoilCode"] == "COIL-E2E-001"
    assert p.metadata_["observaciones"] == "Lote E2E trazabilidad"
    assert p.metadata_["calculationMethod"] == "density_formula"
    print(f"    log produce: qty={p.quantity}, coil={p.metadata_['activeCoilCode']}")

    print("5/7 fin de bobina (debe escribir log scrap)")
    res = inventory.create_retal(
        db,
        tenant.id,
        user.id,
        stock_item_id=bobina.id,
        radio_mm=250,
        order_id=orden.id,
        line_id=linea.id,
    )
    assert res["success"] is True, res
    logs = db.query(ProductionLog).filter_by(order_id=orden.id).all()
    scrap = [e for e in logs if e.action == "scrap"]
    assert len(scrap) == 1, f"esperado 1 log scrap, hay {len(scrap)}"
    s = scrap[0]
    assert s.metadata_["reason"] == "fin_bobina"
    assert s.metadata_["radio_mm"] == 250
    print(f"    log scrap: merma={res['merma_kg']}kg, radio={s.metadata_['radio_mm']}mm")

    print("6/7 get_order_trace: serie completa ascendente")
    traza = traceability.get_order_trace(db, tenant.id, orden.id)
    acciones = [e.action for e in traza]
    ts_asc = [e.timestamp for e in traza] == sorted(e.timestamp for e in traza)
    assert ts_asc, "traza no ordenada por timestamp asc"
    assert set(acciones) >= {"produce", "scrap"}, acciones
    assert all(e.operator is not None for e in traza), "operario no poblado"
    print(f"    acciones: {acciones}")

    print("7/7 INMUTABILIDAD: UPDATE y DELETE deben lanzar excepción")
    log_id = traza[0].id
    try:
        db.execute(
            text("UPDATE production_logs SET action='scrap' WHERE id=:i"),
            {"i": log_id},
        )
        db.commit()
        raise AssertionError("UPDATE debería haber fallado por el trigger")
    except Exception as exc:
        msg = str(exc)
        assert "inmutable" in msg, f"error inesperado: {msg}"
        db.rollback()
        print("    UPDATE bloqueado OK")

    try:
        db.execute(text("DELETE FROM production_logs WHERE id=:i"), {"i": log_id})
        db.commit()
        raise AssertionError("DELETE debería haber fallado por el trigger")
    except Exception as exc:
        msg = str(exc)
        assert "inmutable" in msg, f"error inesperado: {msg}"
        db.rollback()
        print("    DELETE bloqueado OK")

    print("\n✅ E2E TRAZABILIDAD 7/7 PASADO")
finally:
    db.close()
