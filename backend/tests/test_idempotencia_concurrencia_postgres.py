"""Concurrencia real del registro de producción sobre PostgreSQL (T-159).

SQLite no reproduce los bloqueos de fila ni el UNIQUE de la base de datos,
así que este test solo corre si TEST_POSTGRES_URL apunta a un PostgreSQL
(en CI lo da el servicio postgres, como test_concurrencia_postgres.py).

Escenarios:
1. Dos hilos con el MISMO client_request_id sobre la misma línea:
   un solo registro de producción y una sola respuesta (duplicate en la otra).
2. Dos hilos con ids DISTINTOS sobre la misma línea: las piezas suman bien
   (el bloqueo de fila FOR UPDATE evita la actualización perdida).
"""

import os
import threading
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, OrderLine

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


def _setup_linea(db):
    from app.services.inventory import link_coil
    from tests.helpers import (
        make_material,
        make_order,
        make_order_line,
        make_stock_item,
        make_tenant,
        make_user,
    )

    tenant = make_tenant(db, name="Conc Idem")
    user = make_user(db, tenant, email=f"op-{uuid.uuid4().hex[:6]}@conc.local")
    material = make_material(db, tenant, code="CONC-IDEM", cost=2.0)
    bobina = make_stock_item(
        db,
        tenant,
        material,
        cantidad=800.0,
        lote="L-CONC-IDEM",
        fecha_entrada=datetime.now(UTC) - timedelta(days=1),
        coste=2.0,
        ancho=122.0,
        espesor=0.5,
    )
    orden = make_order(db, tenant, numero="OP-CONC-IDEM")
    linea = make_order_line(db, orden, workstation="LINEA-1", total_quantity=1000.0)
    linea.meters_per_piece = Decimal("2.0")
    db.commit()
    link_coil(db, tenant.id, user.id, stock_item_id=bobina.id, order_id=orden.id, line_id=linea.id)
    return dict(tenant=tenant.id, user=user.id, orden=orden.id, linea=linea.id)


def test_dos_hilos_mismo_client_request_id_un_solo_registro(pg_sessionmaker):
    from sqlalchemy import select

    from app.models import ProductionLog
    from app.services.production import record_production

    with pg_sessionmaker() as db:
        ids = _setup_linea(db)

    client_request_id = uuid.uuid4()
    resultados: list[dict] = []
    errores: list[Exception] = []

    def registrar():
        try:
            with pg_sessionmaker() as s:
                r = record_production(
                    s,
                    ids["tenant"],
                    ids["user"],
                    order_id=ids["orden"],
                    line_id=ids["linea"],
                    incremental_quantity=5,
                    client_request_id=client_request_id,
                )
                resultados.append(r)
        except Exception as exc:  # noqa: BLE001
            errores.append(exc)

    hilos = [threading.Thread(target=registrar) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(60)

    assert not errores, errores
    assert len(resultados) == 2
    # Una respuesta es el registro real; la otra, el duplicado guardado
    assert sorted(bool(r.get("duplicate")) for r in resultados) == [False, True]
    assert resultados[0]["produced_quantity"] == resultados[1]["produced_quantity"]

    with pg_sessionmaker() as db:
        logs = db.scalars(
            select(ProductionLog).where(
                ProductionLog.order_id == ids["orden"], ProductionLog.action == "produce"
            )
        ).all()
        assert len(logs) == 1
        linea = db.get(OrderLine, ids["linea"])
        assert linea.produced_quantity == 5  # no 10


def test_dos_hilos_ids_distintos_suman_bien(pg_sessionmaker):
    from app.services.production import record_production

    with pg_sessionmaker() as db:
        ids = _setup_linea(db)

    errores: list[Exception] = []

    def registrar(cantidad: int):
        try:
            with pg_sessionmaker() as s:
                record_production(
                    s,
                    ids["tenant"],
                    ids["user"],
                    order_id=ids["orden"],
                    line_id=ids["linea"],
                    incremental_quantity=cantidad,
                    client_request_id=uuid.uuid4(),
                )
        except Exception as exc:  # noqa: BLE001
            errores.append(exc)

    primero = threading.Thread(target=registrar, args=(5,))
    segundo = threading.Thread(target=registrar, args=(7,))
    primero.start()
    segundo.start()
    primero.join(60)
    segundo.join(60)

    assert not errores, errores
    with pg_sessionmaker() as db:
        linea = db.get(OrderLine, ids["linea"])
        assert linea.produced_quantity == 12  # 5 + 7, sin actualización perdida
