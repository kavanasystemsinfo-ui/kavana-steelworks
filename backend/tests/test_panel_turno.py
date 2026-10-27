"""Tests de la vista Turno del panel de mando (services/panel_turno.py)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models import Incidencia, ProductionLog, Workstation
from app.services.panel_turno import resumen_turno, ventana_turno
from tests.helpers import auth_headers, make_order, make_order_line, make_tenant

# Martes 27-10-2026 a las 18:00 en planta (UTC-5): turno B, 4 h transcurridas
AHORA = datetime(2026, 10, 27, 23, 0, tzinfo=UTC)
INICIO_B = datetime(2026, 10, 27, 19, 0, tzinfo=UTC)


def _puesto(db, tenant, code, ritmo=None):
    ws = Workstation(
        tenant_id=tenant.id,
        code=code,
        name=f"Puesto {code}",
        piezas_hora_nominal=Decimal(str(ritmo)) if ritmo else None,
    )
    db.add(ws)
    db.commit()
    return ws


def _produce(db, tenant, user, order, line, cuando, piezas, action="produce", meta=None):
    db.add(
        ProductionLog(
            tenant_id=tenant.id,
            order_id=order.id,
            line_id=line.id,
            operator_id=user.id,
            timestamp=cuando,
            action=action,
            quantity=Decimal(str(piezas)),
            metadata_=meta or {},
        )
    )
    db.commit()


def test_ventana_de_cada_turno():
    assert ventana_turno(AHORA) == ("B", INICIO_B, INICIO_B + timedelta(hours=8))
    # 03:00 en planta: turno C que empezó a las 22:00 del día anterior
    codigo, inicio, _ = ventana_turno(datetime(2026, 10, 28, 8, 0, tzinfo=UTC))
    assert codigo == "C"
    assert inicio == datetime(2026, 10, 28, 3, 0, tzinfo=UTC)


def test_sin_ritmo_no_hay_plan(db_session, tenant):
    _puesto(db_session, tenant, "PERF-1")
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order, workstation="PERF-1", total_quantity=100)
    line.estado = "in_progress"
    db_session.commit()

    r = resumen_turno(db_session, tenant.id, AHORA)

    assert r["turno"]["codigo"] == "B"
    assert r["turno"]["transcurrido_min"] == 240
    assert r["plan_turno"] is None
    assert r["eficiencia"] is None


def test_plan_piezas_y_prevision(db_session, tenant, user):
    _puesto(db_session, tenant, "PERF-1", ritmo=50)
    _puesto(db_session, tenant, "LIBRE-1", ritmo=100)  # sin orden: no cuenta en el plan
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order, workstation="PERF-1", total_quantity=1000)
    line.estado = "in_progress"
    db_session.commit()
    # Antes del turno: no cuenta
    _produce(db_session, tenant, user, order, line, INICIO_B - timedelta(minutes=5), 99)
    _produce(db_session, tenant, user, order, line, INICIO_B + timedelta(minutes=30), 100)
    _produce(db_session, tenant, user, order, line, AHORA - timedelta(minutes=20), 40)

    r = resumen_turno(db_session, tenant.id, AHORA)

    assert r["piezas"] == 140
    assert r["plan_turno"] == 400  # 50 pz/h × 8 h
    assert r["plan_ahora"] == 200  # 50 pz/h × 4 h
    # Última hora: 40 piezas → 40 pz/h × 4 h restantes
    assert r["prevision_cierre"] == 300
    assert r["serie"][0] == {"minuto": 0, "piezas": 0.0}
    assert r["serie"][-1]["piezas"] == 140
    assert r["eficiencia"]["rendimiento"] == 70.0
    assert r["eficiencia"]["mas_resta"] == "rendimiento"


def test_paradas_del_turno_y_pendientes(db_session, tenant, user):
    _puesto(db_session, tenant, "PUNZ-1", ritmo=40)
    order = make_order(db_session, tenant, numero="2602")
    order.fecha_entrega = AHORA + timedelta(hours=1)
    line = make_order_line(db_session, order, workstation="PUNZ-1", total_quantity=120)
    line.estado = "in_progress"
    db_session.add_all(
        [
            Incidencia(
                tenant_id=tenant.id,
                puesto="PUNZ-1",
                operario_id=user.id,
                descripcion="Bobina agotada",
                tipo="material",
                estado="abierta",
                created_at=AHORA - timedelta(minutes=23),
            ),
            # Cerrada en el turno: cuenta su tiempo declarado
            Incidencia(
                tenant_id=tenant.id,
                puesto="PUNZ-1",
                operario_id=user.id,
                descripcion="Atasco",
                tipo="maquina",
                estado="resuelta",
                tiempo_parada_min=Decimal("10"),
                created_at=INICIO_B + timedelta(minutes=10),
            ),
            # Cerrada en el turno anterior: no cuenta
            Incidencia(
                tenant_id=tenant.id,
                puesto="PUNZ-1",
                operario_id=user.id,
                descripcion="Antigua",
                tipo="maquina",
                estado="cerrada",
                tiempo_parada_min=Decimal("90"),
                created_at=INICIO_B - timedelta(hours=2),
            ),
        ]
    )
    db_session.commit()

    r = resumen_turno(db_session, tenant.id, AHORA)

    assert r["paradas"]["minutos"] == 33
    assert r["paradas"]["numero"] == 2
    assert r["paradas"]["mayor"]["motivo"] == "falta de material"
    [puesto] = r["puestos"]
    assert puesto["estado"] == "parado"
    assert puesto["minutos"] == 23
    [orden] = r["ordenes"]
    assert orden["estado"] == "retraso"  # faltan 3 h de trabajo y queda 1 h
    urgencias = [p["urgencia"] for p in r["pendientes"]]
    assert urgencias == ["urgente", "hoy"]
    assert r["pendientes"][0]["titulo"] == "PUNZ-1 parado · falta de material"


def test_puesto_en_marcha_sin_registrar_se_revisa(db_session, tenant, user):
    _puesto(db_session, tenant, "DOBL-1", ritmo=30)
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order, workstation="DOBL-1", total_quantity=80)
    line.estado = "in_progress"
    db_session.commit()
    _produce(db_session, tenant, user, order, line, AHORA - timedelta(minutes=45), 5)

    r = resumen_turno(db_session, tenant.id, AHORA)

    assert r["puestos"][0]["estado"] == "sin_registrar"
    assert r["pendientes"][-1]["urgencia"] == "revisar"


def test_chatarra_en_porcentaje_de_los_kilos(db_session, tenant, user):
    _puesto(db_session, tenant, "PERF-1", ritmo=50)
    order = make_order(db_session, tenant)
    line = make_order_line(db_session, order, workstation="PERF-1", total_quantity=100)
    _produce(
        db_session,
        tenant,
        user,
        order,
        line,
        AHORA - timedelta(minutes=10),
        10,
        meta={"consumedMaterial": "kg", "consumedAmount": 97},
    )
    _produce(db_session, tenant, user, order, line, AHORA - timedelta(minutes=5), 3, action="scrap")

    r = resumen_turno(db_session, tenant.id, AHORA)

    assert r["chatarra"] == {"kg": 3.0, "pct": 3.0}


def test_endpoint_turno_solo_supervisor_y_por_tenant(db_session, tenant):
    from tests.test_auth_roles import _client

    _puesto(db_session, tenant, "PERF-1", ritmo=50)
    otro = make_tenant(db_session, name="Otro", slug="otro")
    _puesto(db_session, otro, "AJENO-1", ritmo=50)

    sup = _client(
        db_session, auth_headers(db_session, tenant, role="supervisor", email="s@t.local")
    )
    r = sup.get("/api/v1/supervisor/turno")
    assert r.status_code == 200
    assert [p["code"] for p in r.json()["puestos"]] == ["PERF-1"]

    op = _client(db_session, auth_headers(db_session, tenant, role="operator", email="o@t.local"))
    assert op.get("/api/v1/supervisor/turno").status_code == 403
