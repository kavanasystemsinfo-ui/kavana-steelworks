"""E2E contra PostgreSQL real: OEE y KPIs tras producción real.

Verifica que el panel Supervisor muestra valores reales tras el flujo:
1. Vincular bobina demo
2. Producir piezas
3. Registrar horas → real_time
4. Calcular OEE y KPIs → valores no cero coherentes
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
    f"postgresql+psycopg://kavana:{pw}@localhost:5436/kavana_steelworks_clean"
)

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import Base  # noqa: E402
from app.models import Tenant, User  # noqa: E402
from app.services.inventory import link_coil  # noqa: E402
from app.services.oee_kpis import calcular_kpis, calcular_oee  # noqa: E402
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
        tenant = Tenant(name="E2E Steelworks Supervisor")
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

        material = make_material(session, tenant, code="ACERO-SUP", cost=2.0)
        bobina = make_stock_item(
            session,
            tenant,
            material,
            cantidad=800.0,
            lote="L-E2E-SUP",
            fecha_entrada=datetime.now(UTC) - timedelta(days=1),
            coste=2.0,
            ancho=122.0,
            espesor=0.5,
        )
        order = make_order(session, tenant, numero="OP-E2E-SUP")
        line = make_order_line(session, order, workstation="LINEA-1", total_quantity=50.0)
        line.meters_per_piece = Decimal("2.0")
        order.estimado_total_cost = Decimal("1000.00")
        session.commit()

        link_coil(session, tenant.id, user.id, stock_item_id=bobina.id, order_id=order.id, line_id=line.id)

        # Producir 10 piezas con 2 h de trabajo
        record_production(
            session,
            tenant.id,
            user.id,
            order_id=order.id,
            line_id=line.id,
            incremental_quantity=10,
            hours_worked=2.0,
        )
        session.refresh(line)

        oee = calcular_oee(session, tenant.id)
        kpis = calcular_kpis(session, tenant.id)

        # OEE: A = 120/480 = 25%, P = 10/50 = 20%, Q = 100% → OEE = 5%
        assert oee["availability"] == 25.0, oee
        assert oee["performance"] == 20.0, oee
        assert oee["quality"] == 100.0, oee
        assert oee["oee"] == 5.0, oee
        assert oee["raw"]["total_pieces"] == 10.0
        assert oee["raw"]["total_tiempo_min"] == 120.0
        print(f"  ✓ OEE real: A={oee['availability']}% P={oee['performance']}% "
              f"Q={oee['quality']}% → OEE={oee['oee']}%")

        assert kpis["orders_total"] == 1
        assert kpis["orders_active"] == 1
        print(f"  ✓ KPIs: {kpis['orders_active']} orden activa, "
              f"coste real {kpis['real_cost']} € vs est. {kpis['estimated_cost']} €")

        print("\nE2E OK: OEE y KPIs del supervisor con producción real en PG")
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    main()
