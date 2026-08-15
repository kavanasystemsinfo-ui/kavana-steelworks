"""E2E contra PostgreSQL real: validación de material por características.

Verifica la regla de Jorge (anexo A, punto 8) sobre PostgreSQL real:
1. Vincular bobina del material correcto → OK (cobro BULK normal).
2. Vincular bobina de OTRO material (galva vs decapado) → BLOQUEADO.
3. Vincular bobina de ancho incompatible → BLOQUEADO.
4. Vincular bobina de espesor fuera de tolerancia → BLOQUEADO.
5. Tolerancia comercial de espesor (±10 %) → permitido.
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
from app.models import Material, Tenant, User  # noqa: E402
from app.services.inventory import link_coil  # noqa: E402
from tests.helpers import make_order, make_order_line, make_stock_item  # noqa: E402

engine = create_engine(os.environ["STEELWORKS_DATABASE_URL"], pool_pre_ping=True)


def reset_schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _material_con_dimensiones(db, tenant, code, ancho=1220.0, espesor=1.2):
    m = Material(
        tenant_id=tenant.id,
        code=code,
        name=f"Bobina acero {espesor}x{ancho}",
        cost_per_unit=2.0,
        dimension_ancho_mm=Decimal(str(ancho)),
        dimension_espesor_mm=Decimal(str(espesor)),
        unit="kg",
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def main():
    reset_schema()
    session = Session(engine)
    try:
        tenant = Tenant(name="E2E Material Compat")
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

        # Material requerido por la orden (decapado 1.2x1220)
        decapado = _material_con_dimensiones(session, tenant, "ACERO-DC01")
        galva = _material_con_dimensiones(session, tenant, "GALVA-01", ancho=1220.0, espesor=0.8)

        def bobina(material, ancho=1220.0, espesor=1.2, lote="L-OK"):
            return make_stock_item(
                session,
                tenant,
                material,
                cantidad=800.0,
                lote=lote,
                fecha_entrada=datetime.now(UTC) - timedelta(days=1),
                coste=2.0,
                ancho=ancho,
                espesor=espesor,
            )

        order = make_order(session, tenant)
        line = make_order_line(session, order, material=decapado)

        # 1) Material correcto → vincula
        ok = bobina(decapado, lote="L-CORRECTO")
        r = link_coil(
            session, tenant.id, user.id, stock_item_id=ok.id,
            order_id=order.id, line_id=line.id,
        )
        assert r["success"] is True, "bobina correcta debería vincular"
        print("✓ bobina del material correcto vincula")

        # 2) Otro material → bloquea
        otra = bobina(galva, ancho=1220.0, espesor=0.8, lote="L-GALVA")
        try:
            link_coil(
                session, tenant.id, user.id, stock_item_id=otra.id,
                order_id=order.id, line_id=line.id,
            )
            raise SystemExit("ERROR: bobina de otro material NO debería vincular")
        except ValueError as exc:
            assert "Material incompatible" in str(exc), f"mensaje inesperado: {exc}"
            print(f"✓ otro material bloqueado: {exc}")

        # 3) Ancho incompatible → bloquea
        ancha = bobina(decapado, ancho=950.0, espesor=1.2, lote="L-ANCHO")
        try:
            link_coil(
                session, tenant.id, user.id, stock_item_id=ancha.id,
                order_id=order.id, line_id=line.id,
            )
            raise SystemExit("ERROR: ancho incompatible NO debería vincular")
        except ValueError as exc:
            assert "Ancho incompatible" in str(exc), f"mensaje inesperado: {exc}"
            print(f"✓ ancho incompatible bloqueado: {exc}")

        # 4) Espesor fuera de tolerancia → bloquea
        gruesa = bobina(decapado, ancho=1220.0, espesor=3.0, lote="L-GRUESA")
        try:
            link_coil(
                session, tenant.id, user.id, stock_item_id=gruesa.id,
                order_id=order.id, line_id=line.id,
            )
            raise SystemExit("ERROR: espesor incompatible NO debería vincular")
        except ValueError as exc:
            assert "Espesor incompatible" in str(exc), f"mensaje inesperado: {exc}"
            print(f"✓ espesor incompatible bloqueado: {exc}")

        # 5) Tolerancia comercial (±10 %) → permite
        tol = bobina(decapado, ancho=1220.0, espesor=1.24, lote="L-TOL")
        r = link_coil(
            session, tenant.id, user.id, stock_item_id=tol.id,
            order_id=order.id, line_id=line.id,
        )
        assert r["success"] is True, "tolerancia comercial debería permitirse"
        print("✓ tolerancia comercial de espesor permitida")

        print("\nE2E validación de material: 5/5 OK")
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    main()
