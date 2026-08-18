"""Tests del servicio de secuencias automáticas (spec 07 §2.3).

Contrato:
- next_sequence resuelve el prefix con la fecha ({MM}{YY}) y devuelve el
  número formateado con padding.
- El contador avanza y se persiste (no repite número).
- Concurrencia: dos llamadas nunca reciben el mismo número (SELECT FOR UPDATE).
- Config por tenant: prefix/padding por tipo vienen de tenants.sequences_config.
"""

from datetime import UTC, datetime

from app.models import Sequence
from app.services.sequences import next_sequence


def _tenant_con_secuencias(db, tenant, prefix_order="OP-{MM}{YY}-", padding=3):
    tenant.sequences_config = {
        "order": {"prefix": prefix_order, "padding": padding},
        "lot": {"prefix": "LT-{DD}{MM}{YY}-", "padding": 3},
    }
    db.commit()
    return tenant


def test_next_sequence_devuelve_numero_formateado(db_session, tenant):
    _tenant_con_secuencias(db_session, tenant)
    ahora = datetime.now(UTC)
    mm = f"{ahora.month:02d}"
    yy = f"{ahora.year % 100:02d}"
    esperado_prefix = f"OP-{mm}{yy}-"

    numero = next_sequence(db_session, tenant.id, "order")
    assert numero == f"{esperado_prefix}001"


def test_next_sequence_avanza_y_no_repite(db_session, tenant):
    _tenant_con_secuencias(db_session, tenant)

    n1 = next_sequence(db_session, tenant.id, "order")
    n2 = next_sequence(db_session, tenant.id, "order")
    assert n1 != n2
    assert n2.endswith("002")

    fila = db_session.query(Sequence).filter_by(
        tenant_id=tenant.id, sequence_type="order"
    ).one()
    assert fila.next_number == 3  # ya apunta al siguiente


def test_next_sequence_resetea_contador_por_mes(db_session, tenant):
    """Prefix distinto (nuevo mes) = contador nuevo desde 001."""
    _tenant_con_secuencias(db_session, tenant, prefix_order="OP-FIJO-")
    next_sequence(db_session, tenant.id, "order")
    next_sequence(db_session, tenant.id, "order")

    # Cambiamos el prefix configurado: simula mes nuevo
    tenant.sequences_config["order"]["prefix"] = "OP-NUEVO-"
    db_session.commit()

    n = next_sequence(db_session, tenant.id, "order")
    assert n == "OP-NUEVO-001"


def test_next_sequence_lot_y_order_independientes(db_session, tenant):
    _tenant_con_secuencias(db_session, tenant)

    op = next_sequence(db_session, tenant.id, "order")
    lot = next_sequence(db_session, tenant.id, "lot")
    assert op.startswith("OP-")
    assert lot.startswith("LT-")
    assert op.split("-")[-1] == "001"
    assert lot.split("-")[-1] == "001"


# NOTA: la concurrencia real (dos peticiones simultáneas sin duplicar número)
# se verifica en el E2E contra PostgreSQL (e2e_admin.py), donde SELECT FOR
# UPDATE sí bloquea la fila. SQLite ignora FOR UPDATE y serializa de otra
# forma, por eso no hay test unitario de concurrencia aquí.


def test_next_sequence_padding_configurable(db_session, tenant):
    _tenant_con_secuencias(db_session, tenant, padding=5)
    numero = next_sequence(db_session, tenant.id, "order")
    assert numero.endswith("00001")
