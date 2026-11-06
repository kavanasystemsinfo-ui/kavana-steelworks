"""Auditoría T-029 sobre PostgreSQL real: concurrencia y bloqueo de filas.

Solo corren con TEST_POSTGRES_URL (el CI los ejecuta con el servicio postgres).

  H6  Las escrituras al saldo de la bobina en fin de bobina / medición
      (create_retal, medir_bobina) y en retirar_pico NO bloquean la fila,
      mientras consume_stock_fifo sí (FOR UPDATE). Una medición concurrente
      con un registro de producción pisa el saldo con una lectura vieja.
  E1  (evidencia, no hallazgo) El test de concurrencia de la PR #50 tiene
      dientes: sin FOR UPDATE el saldo acaba en 70 en vez de 40.
"""

import os
import threading
import time
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
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


def _montada(db, peso=100.0):
    from tests.helpers import (
        make_material,
        make_order,
        make_order_line,
        make_stock_item,
        make_tenant,
        make_user,
    )

    tenant = make_tenant(db, name="PG Auditoría")
    user = make_user(db, tenant, email="pg@audit.local", role="operator")
    material = make_material(db, tenant, code="PG-M", cost=2.0)
    bobina = make_stock_item(
        db, tenant, material, cantidad=peso, lote="L-PG", ancho=122, espesor=0.5
    )
    orden = make_order(db, tenant, numero="OP-PG")
    linea = make_order_line(db, orden, workstation="LINEA-1")
    linea.active_coil_id = bobina.id
    linea.active_coil_code = bobina.coil_id
    db.commit()
    return tenant, user, material, bobina, orden, linea


def test_h6_create_retal_bloquea_la_bobina(pg_sessionmaker):
    """La medición que sobrescribe cantidad_disponible debe tomar la fila."""
    from app.services import coil_math
    from app.services.inventory import create_retal

    sentencias: list[str] = []

    with pg_sessionmaker() as db:
        tenant, user, _m, bobina, orden, linea = _montada(db)
        engine = db.get_bind()

        def _capturar(conn, cursor, statement, parameters, context, executemany):
            if "stock_items" in statement:
                sentencias.append(statement)

        event.listen(engine, "before_cursor_execute", _capturar)
        try:
            original = coil_math.peso_desde_radio_mm
            coil_math.peso_desde_radio_mm = lambda **_: 90.0
            try:
                create_retal(
                    db, tenant.id, user.id,
                    stock_item_id=bobina.id, radio_mm=50.0,
                    order_id=orden.id, line_id=linea.id,
                )
            finally:
                coil_math.peso_desde_radio_mm = original
        finally:
            event.remove(engine, "before_cursor_execute", _capturar)

    assert any("FOR UPDATE" in s.upper() for s in sentencias), (
        "create_retal leyó stock_items sin FOR UPDATE: "
        f"{len(sentencias)} sentencias, ninguna bloquea"
    )


def test_h6_retirar_pico_bloquea_la_bobina(pg_sessionmaker):
    from app.services.inventory import retirar_pico

    sentencias: list[str] = []

    with pg_sessionmaker() as db:
        tenant, user, _m, bobina, _o, _l = _montada(db, peso=80.0)
        engine = db.get_bind()

        def _capturar(conn, cursor, statement, parameters, context, executemany):
            if "stock_items" in statement:
                sentencias.append(statement)

        event.listen(engine, "before_cursor_execute", _capturar)
        try:
            retirar_pico(db, tenant.id, user.id, stock_item_id=bobina.id)
        finally:
            event.remove(engine, "before_cursor_execute", _capturar)

    assert any("FOR UPDATE" in s.upper() for s in sentencias), (
        "retirar_pico leyó stock_items sin FOR UPDATE"
    )


def test_h6_medir_bobina_bloquea_la_bobina(pg_sessionmaker):
    """El cierre de turno también sobrescribe cantidad_disponible: debe bloquear."""
    from app.services import coil_math
    from app.services.medicion import medir_bobina

    sentencias: list[str] = []

    with pg_sessionmaker() as db:
        tenant, user, _m, bobina, orden, linea = _montada(db, peso=90.0)
        engine = db.get_bind()

        def _capturar(conn, cursor, statement, parameters, context, executemany):
            if "stock_items" in statement:
                sentencias.append(statement)

        event.listen(engine, "before_cursor_execute", _capturar)
        try:
            original = coil_math.peso_desde_radio_mm
            coil_math.peso_desde_radio_mm = lambda **_: 88.0
            try:
                medir_bobina(
                    db, tenant.id, user.id,
                    stock_item_id=bobina.id, radio_mm=50.0,
                    order_id=orden.id, line_id=linea.id,
                )
            finally:
                coil_math.peso_desde_radio_mm = original
        finally:
            event.remove(engine, "before_cursor_execute", _capturar)

    assert any("FOR UPDATE" in s.upper() for s in sentencias), (
        "medir_bobina leyó stock_items sin FOR UPDATE"
    )


def test_e1_el_test_de_concurrencia_falla_sin_for_update(pg_sessionmaker, monkeypatch):
    """Evidencia: sin el bloqueo, la carrera pierde un descuento (70 en vez de 40)."""
    from sqlalchemy import select

    from app.services import inventory

    with pg_sessionmaker() as db:
        tenant, user, material, bobina, orden, linea = _montada(db, peso=100.0)
        ids = dict(
            tenant=tenant.id, user=user.id, material=material.id,
            bobina=bobina.id, orden=orden.id, linea=linea.id,
        )

    def _sin_bloqueo(db, tenant_id, material_id, **kw):
        stmt = (
            select(StockItem)
            .where(
                StockItem.tenant_id == tenant_id,
                StockItem.material_id == material_id,
                StockItem.estado.in_(("activo", "pico")),
            )
            .order_by(StockItem.fecha_entrada.asc())
        )
        return list(db.scalars(stmt))

    monkeypatch.setattr(inventory, "_elegibles_fifo", _sin_bloqueo)

    errores: list[Exception] = []

    def consumir(retener: float):
        try:
            with pg_sessionmaker() as s:
                inventory.consume_stock_fifo(
                    s, ids["tenant"], ids["user"],
                    material_id=ids["material"], cantidad_requerida=30,
                    order_id=ids["orden"], order_line_id=ids["linea"],
                    commit=False,
                )
                time.sleep(retener)
                s.commit()
        except Exception as exc:  # noqa: BLE001
            errores.append(exc)

    primero = threading.Thread(target=consumir, args=(1.5,))
    segundo = threading.Thread(target=consumir, args=(0,))
    primero.start()
    time.sleep(0.5)
    segundo.start()
    primero.join(30)
    segundo.join(30)

    with pg_sessionmaker() as db:
        final = db.get(StockItem, ids["bobina"]).cantidad_disponible

    assert not errores, errores
    assert final == Decimal("70"), (
        "sin FOR UPDATE se esperaba la actualización perdida (70 kg); "
        f"saldo final {final}"
    )
