"""Atomicidad del registro de producción (auditoría externa 2026-11-06).

Consumo FIFO y registro de producción se confirman en UN solo commit: si algo
falla después de descontar, al hacer rollback el stock queda intacto.
"""

import pytest

from tests.test_production import _setup


def test_fallo_tras_consumir_no_deja_stock_descontado(db_session, tenant, user, monkeypatch):
    from app.services import costes
    from app.services.production import record_production

    _, bobina, order, line = _setup(db_session, tenant, user)
    antes = bobina.cantidad_disponible

    def _falla(*args, **kwargs):
        raise RuntimeError("fallo inesperado al actualizar la orden")

    monkeypatch.setattr(costes, "actualizar_costes_orden", _falla)

    with pytest.raises(RuntimeError):
        record_production(
            db_session, tenant.id, user.id,
            order_id=order.id, line_id=line.id, incremental_quantity=2,
        )
    db_session.rollback()

    db_session.refresh(bobina)
    db_session.refresh(line)
    assert bobina.cantidad_disponible == antes
    assert (line.produced_quantity or 0) == 0


def test_produccion_correcta_descuenta_y_registra(db_session, tenant, user):
    from app.services.production import record_production

    _, bobina, order, line = _setup(db_session, tenant, user)
    antes = bobina.cantidad_disponible

    record_production(
        db_session, tenant.id, user.id,
        order_id=order.id, line_id=line.id, incremental_quantity=2,
    )
    db_session.refresh(bobina)
    db_session.refresh(line)
    assert bobina.cantidad_disponible < antes
    assert line.produced_quantity == 2
