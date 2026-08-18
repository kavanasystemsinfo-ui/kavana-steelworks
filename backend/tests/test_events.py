"""Tests TDD del broker de eventos WebSocket (spec 05, sección 2.6).

Contrato:
- El broker publica eventos por canal (tenant_id) y suscripción.
- Eventos de planta: consumo FIFO, stock_deficit, downtime, incidencias.
- Sin conexión persistente: el broker almacena eventos para entrega
  posterior (patrón simple, sin Redis en el core).
"""


def test_broker_publica_y_recupera_eventos_por_canal(db_session, tenant):
    from app.services.events import EventBroker

    broker = EventBroker()
    broker.publish(
        tenant_id=tenant.id,
        tipo="stock_deficit",
        data={"material": "ACERO-01", "impacto": 123.4},
    )

    eventos = broker.get_events(tenant.id)
    assert len(eventos) == 1
    assert eventos[0]["tipo"] == "stock_deficit"
    assert eventos[0]["data"]["impacto"] == 123.4


def test_broker_separa_eventos_por_tenant(db_session, tenant):

    # segundo tenant
    from app.services.events import EventBroker
    from tests.helpers import make_tenant

    t2 = make_tenant(db_session, name="Otra Planta")
    db_session.add(t2)
    db_session.commit()
    db_session.refresh(t2)

    broker = EventBroker()
    broker.publish(tenant_id=tenant.id, tipo="consumo_fifo", data={"kg": 30})
    broker.publish(tenant_id=t2.id, tipo="downtime", data={"min": 45})

    assert len(broker.get_events(tenant.id)) == 1
    assert len(broker.get_events(t2.id)) == 1
    assert broker.get_events(tenant.id)[0]["tipo"] == "consumo_fifo"
    assert broker.get_events(t2.id)[0]["tipo"] == "downtime"


def test_broker_limita_cola_por_tenant(db_session, tenant):
    from app.services.events import EventBroker

    broker = EventBroker(max_events=5)
    for i in range(10):
        broker.publish(tenant_id=tenant.id, tipo="kpi", data={"i": i})

    eventos = broker.get_events(tenant.id)
    assert len(eventos) == 5  # los últimos 5
    assert eventos[-1]["data"]["i"] == 9
