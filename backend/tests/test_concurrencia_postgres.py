"""Concurrencia real del consumo FIFO sobre PostgreSQL (auditoría 2026-11-06).

SQLite no reproduce los bloqueos de fila, así que este test solo corre si
TEST_POSTGRES_URL apunta a un PostgreSQL (en CI lo da el servicio postgres).

Escenario: dos puestos consumen 30 kg cada uno de la MISMA bobina de 100 kg.
El primero retiene la transacción un rato antes de confirmar. Con el bloqueo
de filas (FOR UPDATE) el segundo espera y parte del saldo ya descontado
(final 40 kg). Sin bloqueo leería 100 y se perdería uno de los dos
descuentos (final 70 kg).
"""

import os
import threading
import time
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, StockItem

PG_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(not PG_URL, reason="TEST_POSTGRES_URL no definido")


@pytest.fixture()
def pg_sessionmaker():
    engine = create_engine(PG_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_dos_puestos_consumen_la_misma_bobina_sin_perder_descuentos(pg_sessionmaker):
    from app.services.inventory import consume_stock_fifo
    from tests.helpers import (
        make_material,
        make_order,
        make_order_line,
        make_stock_item,
        make_tenant,
        make_user,
    )

    with pg_sessionmaker() as db:
        tenant = make_tenant(db, name="Concurrencia")
        user = make_user(db, tenant, email="op@conc.local")
        material = make_material(db, tenant, code="CONC", cost=2.0)
        bobina = make_stock_item(
            db, tenant, material, cantidad=100, lote="L-CONC", fecha_entrada=datetime.now(UTC)
        )
        orden = make_order(db, tenant, numero="OP-CONC")
        linea = make_order_line(db, orden)
        ids = dict(
            tenant=tenant.id, user=user.id, material=material.id,
            bobina=bobina.id, orden=orden.id, linea=linea.id,
        )

    errores: list[Exception] = []

    def consumir(retener_segundos: float):
        try:
            with pg_sessionmaker() as s:
                consume_stock_fifo(
                    s, ids["tenant"], ids["user"],
                    material_id=ids["material"], cantidad_requerida=30,
                    order_id=ids["orden"], order_line_id=ids["linea"],
                    commit=False,
                )
                time.sleep(retener_segundos)  # el primero retiene el bloqueo
                s.commit()
        except Exception as exc:  # noqa: BLE001
            errores.append(exc)

    primero = threading.Thread(target=consumir, args=(1.5,))
    segundo = threading.Thread(target=consumir, args=(0,))
    primero.start()
    time.sleep(0.5)  # el segundo llega con el primero aún sin confirmar
    segundo.start()
    primero.join(30)
    segundo.join(30)

    assert not errores, errores
    with pg_sessionmaker() as db:
        final = db.get(StockItem, ids["bobina"]).cantidad_disponible
    assert final == Decimal("40")
