"""Tests de la ficha de puesto (services/ficha_puesto.py y su endpoint)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models import Incidencia, ProductionLog, Workstation
from app.services.ficha_puesto import ficha_puesto
from tests.helpers import auth_headers, make_order, make_order_line, make_tenant, make_user

# Miércoles 28-10-2026 a las 12:00 en planta (Madrid, UTC+1)
AHORA = datetime(2026, 10, 28, 11, 0, tzinfo=UTC)
LUNES = datetime(2026, 10, 25, 23, 0, tzinfo=UTC)  # lunes 00:00 en planta


def _puesto(db, tenant, code, ritmo=None):
    db.add(
        Workstation(
            tenant_id=tenant.id,
            code=code,
            name=f"Puesto {code}",
            piezas_hora_nominal=Decimal(str(ritmo)) if ritmo else None,
        )
    )
    db.commit()


def _log(db, tenant, user, order, line, cuando, cantidad, action="produce", meta=None):
    db.add(
        ProductionLog(
            tenant_id=tenant.id,
            order_id=order.id,
            line_id=line.id,
            operator_id=user.id,
            timestamp=cuando,
            action=action,
            quantity=Decimal(str(cantidad)),
            metadata_=meta or {},
        )
    )
    db.commit()


def _meta(bobina, eficiencia=80, kg=10):
    return {
        "efficiency": eficiencia,
        "consumedMaterial": "kg",
        "consumedAmount": kg,
        "activeCoilCode": bobina,
    }


def test_sesiones_se_cortan_por_operario_linea_y_hueco(db_session, tenant, user):
    ana = make_user(db_session, tenant, email="ana@t.local", name="Ana")
    _puesto(db_session, tenant, "PERF-1", ritmo=100)
    orden = make_order(db_session, tenant, numero="OP-7")
    l1 = make_order_line(db_session, orden, workstation="PERF-1")
    l2 = make_order_line(db_session, orden, workstation="PERF-1", linea_numero=2)
    t0 = LUNES + timedelta(hours=8)
    # Sesión 1: el operario fijo, línea 1, dos bobinas
    _log(db_session, tenant, user, orden, l1, t0, 40, meta=_meta("B-1"))
    _log(db_session, tenant, user, orden, l1, t0 + timedelta(minutes=30), 40, meta=_meta("B-2"))
    _log(db_session, tenant, user, orden, l1, t0 + timedelta(minutes=45), 3, action="scrap")
    # Sesión 2: cambia el operario
    _log(db_session, tenant, ana, orden, l1, t0 + timedelta(hours=1), 30, meta=_meta("B-2"))
    # Sesión 3: mismo operario, cambia la línea
    t_l2 = t0 + timedelta(hours=1, minutes=20)
    _log(db_session, tenant, ana, orden, l2, t_l2, 20, meta=_meta("B-3"))
    # Sesión 4: mismo operario y línea pero seis horas después
    _log(db_session, tenant, ana, orden, l2, t0 + timedelta(hours=8), 10, meta=_meta("B-3"))

    r = ficha_puesto(db_session, tenant.id, "PERF-1", "semana", AHORA)
    s = r["sesiones"]

    assert [x["operario"] for x in s] == ["Ana", "Ana", "Ana", user.name]
    assert [x["piezas"] for x in s] == [10, 20, 30, 80]  # la más reciente primero
    ultima = s[-1]
    assert ultima["bobinas"] == ["B-1", "B-2"]
    assert ultima["chatarra_kg"] == 3.0
    assert ultima["minutos"] == 45
    assert ultima["orden"] == "OP-7"
    assert [e["accion"] for e in ultima["eventos"]] == ["produce", "produce", "scrap"]
    assert ultima["eventos"][1]["bobina"] == "B-2"
    assert ultima["eventos"][0]["hora"].endswith("+00:00")


def test_ficha_con_cifras_de_puesto_y_sin_ruido_de_otros(db_session, tenant, user):
    _puesto(db_session, tenant, "PERF-1", ritmo=100)
    _puesto(db_session, tenant, "PUNZ-1", ritmo=50)
    orden = make_order(db_session, tenant)
    perf = make_order_line(db_session, orden, workstation="PERF-1")
    punz = make_order_line(db_session, orden, workstation="PUNZ-1", linea_numero=2)
    _log(db_session, tenant, user, orden, perf, LUNES + timedelta(hours=10), 320,
         meta=_meta("B-1", 80, 98))
    _log(db_session, tenant, user, orden, perf, LUNES + timedelta(hours=11), 2, action="scrap")
    _log(db_session, tenant, user, orden, punz, LUNES + timedelta(hours=10), 50,
         meta=_meta("B-9", 25))
    db_session.add(
        Incidencia(
            tenant_id=tenant.id,
            puesto="PERF-1",
            operario_id=user.id,
            descripcion="Avería",
            tipo="maquina",
            estado="resuelta",
            tiempo_parada_min=Decimal("60"),
            created_at=LUNES + timedelta(hours=9),
        )
    )
    db_session.commit()

    r = ficha_puesto(db_session, tenant.id, "PERF-1", "semana", AHORA)

    assert r["puesto"]["name"] == "Puesto PERF-1"
    assert r["piezas"] == 320
    assert r["plan"] == 500  # 100 pz/h × (4 h trabajadas + 1 h parado)
    assert r["eficiencia"]["disponibilidad"] == 80.0
    assert r["eficiencia"]["calidad"] == 98.0  # 2 kg de chatarra sobre 100
    assert r["paradas"]["por_causa"] == [{"causa": "avería", "minutos": 60, "pct": 100.0}]
    assert r["material"] == {"kg_consumidos": 98.0, "chatarra_kg": 2.0, "chatarra_pct": 2.0}
    assert all(e["bobina"] != "B-9" for s in r["sesiones"] for e in s["eventos"])
    assert "coste" not in str(r).lower() and "euro" not in str(r).lower()


def test_puesto_inexistente_y_periodo_invalido(db_session, tenant):
    _puesto(db_session, tenant, "PERF-1")
    with pytest.raises(LookupError):
        ficha_puesto(db_session, tenant.id, "NO-EXISTE", "hoy", AHORA)
    with pytest.raises(ValueError):
        ficha_puesto(db_session, tenant.id, "PERF-1", "año", AHORA)
    vacia = ficha_puesto(db_session, tenant.id, "PERF-1", "hoy", AHORA)
    assert vacia["sesiones"] == [] and vacia["piezas"] == 0 and vacia["eficiencia"] is None


def test_endpoint_ficha_roles_y_aislamiento(db_session, tenant, user):
    from tests.test_auth_roles import _client

    otro = make_tenant(db_session, name="Otro", slug="otro")
    _puesto(db_session, otro, "AJENO-1", ritmo=50)
    _puesto(db_session, tenant, "PERF-1", ritmo=100)
    url = "/api/v1/supervisor/puestos/PERF-1/ficha"

    anonimo = _client(db_session, {})
    assert anonimo.get(url).status_code == 401
    op = _client(db_session, auth_headers(db_session, tenant, role="operator", email="o@t.local"))
    assert op.get(url).status_code == 403
    sup = _client(
        db_session, auth_headers(db_session, tenant, role="supervisor", email="s@t.local")
    )
    r = sup.get(url + "?periodo=semana")
    assert r.status_code == 200
    assert r.json()["puesto"]["code"] == "PERF-1"
    assert sup.get(url + "?periodo=año").status_code == 400
    assert sup.get("/api/v1/supervisor/puestos/AJENO-1/ficha").status_code == 404
