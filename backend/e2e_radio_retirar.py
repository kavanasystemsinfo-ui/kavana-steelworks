"""E2E contra PostgreSQL real: fin de bobina con radio (fórmula v2) + Retirar.

Verifica los CHECK/NOT NULL de PostgreSQL real que SQLite no detecta:
- create_retal recibe radio_mm, convierte con la fórmula v2 (densidad calibrada)
- el sobrante queda en el puesto como pico (no Retales)
- retirar_pico lo mueve a 'Retales' y aparece en /picos
- la merma invisible se registra en material_consumos
"""

import os
import subprocess
import uuid
from datetime import UTC, datetime, timedelta

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

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.database import Base  # noqa: E402
from app.models import MaterialConsumo, MaterialTransaction, Order, OrderLine, StockItem, Tenant, User  # noqa: E402
from app.services.inventory import consume_stock_fifo, create_retal, link_coil, retirar_pico  # noqa: E402
from app.services.coil_math import peso_desde_radio_mm  # noqa: E402

engine = create_engine(os.environ["STEELWORKS_DATABASE_URL"], pool_pre_ping=True)


def reset_schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def main():
    reset_schema()
    from sqlalchemy.orm import Session

    session = Session(engine)

    try:
        # Datos base
        tenant = Tenant(name="E2E Steelworks Radio")
        session.add(tenant)
        session.flush()
        user = User(
            tenant_id=tenant.id,
            email="e2e@test.local",
            name="E2E",
            password_hash="x",
            role="operator",
        )
        session.add(user)
        session.flush()

        from tests.helpers import make_material, make_order, make_order_line, make_stock_item

        material = make_material(session, tenant, code="ACERO-RADIO", cost=2.0)
        bobina = make_stock_item(
            session,
            tenant,
            material,
            cantidad=800.0,
            lote="L-E2E-RADIO",
            fecha_entrada=datetime.now(UTC) - timedelta(days=1),
            coste=2.0,
            ancho=122.0,
            espesor=0.5,
        )
        order = make_order(session, tenant, numero="OP-E2E-RADIO")
        line = make_order_line(session, order, workstation="LINEA-1")

        link_coil(session, tenant.id, user.id, stock_item_id=bobina.id, order_id=order.id, line_id=line.id)
        consume_stock_fifo(
            session,
            tenant.id,
            user.id,
            material_id=material.id,
            cantidad_requerida=300.0,
            order_id=order.id,
            order_line_id=line.id,
        )
        session.refresh(bobina)
        assert float(bobina.cantidad_disponible) == 500.0, "setup FIFO"

        # ── Fin de bobina: radio 200 mm → ~422,27 kg → merma ~77,73 kg
        resultado = create_retal(
            session,
            tenant.id,
            user.id,
            stock_item_id=bobina.id,
            radio_mm=200.0,
            order_id=order.id,
            line_id=line.id,
        )
        session.refresh(bobina)
        peso_esperado = peso_desde_radio_mm(radio_mm=200.0, width_mm=122.0)
        assert abs(resultado["peso_restante_kg"] - peso_esperado) < 0.01, resultado
        assert abs(resultado["merma_kg"] - (500.0 - peso_esperado)) < 0.01, resultado
        assert bobina.estado == "pico", bobina.estado
        assert bobina.es_pico is True
        assert bobina.ubicacion == "LINEA-1", "el pico queda en el puesto"
        print(f"  ✓ Fin de bobina por radio: quedan {resultado['peso_restante_kg']} kg, "
              f"merma {resultado['merma_kg']:.2f} kg")

        # Merma registrada en PG real (CHECK del modelo)
        merma = (
            session.query(MaterialConsumo)
            .filter(MaterialConsumo.stock_item_id == bobina.id, MaterialConsumo.tipo == "merma_puntas")
            .all()
        )
        assert len(merma) == 1, "merma invisible registrada"
        print(f"  ✓ Merma invisible en material_consumos: {float(merma[0].consumed_quantity):.2f} kg")

        # ── Antes de retirar: NO está en /picos (sigue en la máquina)
        from app.routers.stock import sugerencias_picos

        assert len(sugerencias_picos(session)) == 0, "pico en puesto no se sugiere"
        print("  ✓ Pico en el puesto NO aparece en sugerencias")

        # ── Botón Retirar: vuelve al inventario y aparece como sugerido
        retirado = retirar_pico(
            session,
            tenant.id,
            user.id,
            stock_item_id=bobina.id,
            order_id=order.id,
            line_id=line.id,
        )
        session.refresh(bobina)
        assert retirado["success"] is True
        assert bobina.ubicacion == "Retales", bobina.ubicacion
        assert bobina.estado == "pico"
        sugeridos = sugerencias_picos(session)
        assert len(sugeridos) == 1, f"esperado 1 sugerido, hay {len(sugeridos)}"
        assert sugeridos[0].stock_item_id == bobina.id
        print(f"  ✓ Retirar: pico en 'Retales' ({float(retirado['peso_kg']):.2f} kg) y sugerido")

        # Kardex en PG real
        ajustes = (
            session.query(MaterialTransaction)
            .filter(MaterialTransaction.stock_item_id == bobina.id)
            .all()
        )
        assert len(ajustes) >= 2, "kardex: ajuste_inventario + traslado"
        print(f"  ✓ Kardex en PG real: {len(ajustes)} movimientos")

        print("\nE2E OK: fin de bobina por radio + Retirar contra PostgreSQL real")
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    main()
