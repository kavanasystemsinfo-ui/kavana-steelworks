"""E2E contra PostgreSQL real: ciclo completo del operario con producción.

Flujo (anexo A + spec 02 3.4):
1. Recibir bobina (Materias Primas)
2. Escanear y vincular (cobro BULK)
3. Registrar producción: el FIFO consume kg por density_formula
4. Fin de bobina: medir radio → merma real
5. Retirar pico al inventario → sugerencia

Verifica los CHECK/NOT NULL de PostgreSQL real que SQLite no detecta.
"""

import os
import subprocess
from datetime import UTC, datetime, timedelta
from decimal import Decimal

# Password desde el contenedor (nunca en el repo ni en logs)
pw = subprocess.check_output(
    "docker inspect kavana-busroad-pg-test "
    "--format '{{range .Config.Env}}{{println .}}{{end}}'",
    shell=True,
    text=True,
)
pw = next(line.split("=", 1)[1] for line in pw.splitlines() if line.startswith("POSTGRES_PASSWORD="))
os.environ["STEELWORKS_DATABASE_URL"] = (
    f"postgresql+psycopg://kavana:{pw}@localhost:5436/kavana_steelworks"
)

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import Base  # noqa: E402
from app.models import MaterialConsumo, MaterialTransaction, Tenant, User  # noqa: E402
from app.services.inventory import create_retal, link_coil, retirar_pico  # noqa: E402
from app.services.production import record_production  # noqa: E402
from tests.helpers import make_material, make_order, make_order_line, make_stock_item  # noqa: E402

engine = create_engine(os.environ["STEELWORKS_DATABASE_URL"], pool_pre_ping=True)


def reset_schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def main():
    reset_schema()
    session = Session(engine)
    try:
        tenant = Tenant(name="E2E Steelworks Produccion")
        session.add(tenant)
        session.flush()
        user = User(
            tenant_id=tenant.id,
            email="operario@test.local",
            name="Operario E2E",
            password_hash="x",
            role="operator",
        )
        session.add(user)
        session.flush()

        material = make_material(session, tenant, code="ACERO-PROD", cost=2.0)
        bobina = make_stock_item(
            session,
            tenant,
            material,
            cantidad=800.0,
            lote="L-E2E-PROD",
            fecha_entrada=datetime.now(UTC) - timedelta(days=1),
            coste=2.0,
            ancho=122.0,
            espesor=0.5,
        )
        order = make_order(session, tenant, numero="OP-E2E-PROD")
        line = make_order_line(session, order, workstation="LINEA-1", total_quantity=50.0)
        line.meters_per_piece = Decimal("2.0")
        session.commit()

        # 1) Vincular (cobro BULK)
        link_coil(session, tenant.id, user.id, stock_item_id=bobina.id, order_id=order.id, line_id=line.id)
        session.refresh(bobina)
        assert float(bobina.cantidad_disponible) == 800.0
        print("  ✓ Bobina vinculada (cobro BULK 800 kg)")

        # 2) Producir 10 piezas → consume kg por density_formula
        # kg_por_pieza = 2 m × 0,122 × 0,0005 × 7780,7 ≈ 0,949 kg
        result = record_production(
            session,
            tenant.id,
            user.id,
            order_id=order.id,
            line_id=line.id,
            incremental_quantity=10,
            hours_worked=2.0,
        )
        session.refresh(bobina)
        session.refresh(line)
        kg_por_pieza = 2.0 * 0.122 * 0.0005 * 7780.7
        esperado = 10 * kg_por_pieza
        assert result["calculation_method"] == "density_formula", result
        assert abs(float(bobina.cantidad_disponible) - (800.0 - esperado)) < 0.01, bobina.cantidad_disponible
        assert float(line.produced_quantity) == 10.0
        assert float(line.real_time) == 120.0  # 2 h × 60
        print(f"  ✓ Producción: 10 piezas → {esperado:.2f} kg consumidos "
              f"(density_formula, quedan {float(bobina.cantidad_disponible):.2f} kg)")

        # 3) MaterialConsumo auto_audit con trazabilidad real en PG
        consumos = (
            session.query(MaterialConsumo)
            .filter(MaterialConsumo.order_id == order.id)
            .all()
        )
        assert len(consumos) == 1
        assert consumos[0].tipo == "auto_audit"
        assert consumos[0].calculation_method == "density_formula"
        assert consumos[0].produced_quantity == 10
        print(f"  ✓ MaterialConsumo auto_audit: {float(consumos[0].consumed_quantity):.2f} kg")

        # 4) Fin de bobina: medir radio → merma real
        # quedan ~790,51 kg; un radio de ~270 mm con ancho 122 → ~640 kg
        fin = create_retal(
            session,
            tenant.id,
            user.id,
            stock_item_id=bobina.id,
            radio_mm=270.0,
            order_id=order.id,
            line_id=line.id,
        )
        session.refresh(bobina)
        assert bobina.estado == "pico"
        assert bobina.ubicacion == "LINEA-1"  # queda en el puesto
        print(f"  ✓ Fin de bobina: quedan {fin['peso_restante_kg']:.2f} kg "
              f"en el puesto, merma {fin['merma_kg']:.2f} kg")

        # 5) Retirar pico al inventario → sugerencia
        retirado = retirar_pico(
            session,
            tenant.id,
            user.id,
            stock_item_id=bobina.id,
            order_id=order.id,
            line_id=line.id,
        )
        session.refresh(bobina)
        assert bobina.ubicacion == "Retales"
        from app.routers.stock import sugerencias_picos

        sugeridos = sugerencias_picos(session)
        assert any(s.stock_item_id == bobina.id for s in sugeridos)
        print(f"  ✓ Pico retirado a 'Retales' ({float(retirado['peso_kg']):.2f} kg) y sugerido")

        print("\nE2E OK: ciclo completo operario (producir → fin de bobina → retirar) en PG real")
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    main()
