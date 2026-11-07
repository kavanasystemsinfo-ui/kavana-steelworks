"""La demo tiene 8 puestos de planta reales y 3 operarios por puesto (mañana, tarde, noche)."""

import random
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models import OrderLine, ProductionLog, User, Workstation
from app.services import simulador
from app.services.seed_demo import buscar_tenant_demo, seed_demo
from app.services.seed_estanterias import asegurar_flujo_demo, seed_estanterias
from app.services.seed_planta import (
    OPERARIOS,
    PUESTOS_ANTIGUOS,
    PUESTOS_PLANTA,
    RECETAS_PLANTA,
    asegurar_planta_realista,
    email_operario,
    turno_de,
)

MADRID = ZoneInfo("Europe/Madrid")


def _planta(db):
    seed_demo(db)
    seed_estanterias(db)
    tenant = buscar_tenant_demo(db)
    asegurar_planta_realista(db, tenant.id)
    asegurar_flujo_demo(db, tenant.id, RECETAS_PLANTA)
    db.commit()
    return tenant


def test_ocho_puestos_activos_y_los_antiguos_desactivados(db_session):
    tenant = _planta(db_session)
    puestos = {
        w.code: w
        for w in db_session.scalars(select(Workstation).where(Workstation.tenant_id == tenant.id))
    }
    activos = {c for c, w in puestos.items() if w.is_active}
    assert activos == {p[0] for p in PUESTOS_PLANTA}
    assert len(activos) == 8
    assert puestos["P-313"].name.startswith("Perfiladora 313")
    assert puestos["PL-220"].name == "Plegadora PL-220"
    for code in PUESTOS_ANTIGUOS:
        if code in puestos:
            assert puestos[code].is_active is False  # se desactivan, nunca se borran


def test_tres_operarios_distintos_por_puesto_y_es_idempotente(db_session):
    tenant = _planta(db_session)
    antes = db_session.scalars(select(User).where(User.role == "operator")).all()
    segunda = asegurar_planta_realista(db_session, tenant.id)
    assert segunda == {
        "puestos": 0, "operarios": 0, "desactivados": 0, "ordenes_cerradas": 0,
        "bobinas_reubicadas": 0,
    }
    nombres = [n for ternas in OPERARIOS.values() for n in ternas]
    assert len(nombres) == 24 == len(set(nombres))
    assert all(len(t) == 3 for t in OPERARIOS.values())
    for puesto in OPERARIOS:
        emails = {email_operario(puesto, t) for t in "ABC"}
        assert len(emails) == 3
    assert len([u for u in antes if u.name in nombres]) == 24


def test_el_turno_sale_de_la_hora_de_planta():
    assert turno_de(datetime(2030, 1, 16, 7, tzinfo=MADRID)) == "A"
    assert turno_de(datetime(2030, 1, 16, 15, tzinfo=MADRID)) == "B"
    assert turno_de(datetime(2030, 1, 16, 23, tzinfo=MADRID)) == "C"
    assert turno_de(datetime(2030, 1, 16, 3, tzinfo=MADRID)) == "C"


def test_el_simulador_registra_a_nombre_del_operario_del_turno(db_session, monkeypatch):
    monkeypatch.setattr(simulador, "_ultimo_relleno", None)
    tenant = _planta(db_session)
    for hora in (8, 16, 23):
        simulador.simular_tick(
            db_session, random.Random(3), minutos_tick=15,
            ahora=datetime(2030, 1, 16, hora, tzinfo=MADRID),
        )
    filas = db_session.execute(
        select(ProductionLog, OrderLine.workstation_id)
        .join(OrderLine, OrderLine.id == ProductionLog.line_id)
        .where(ProductionLog.tenant_id == tenant.id)
    ).all()
    nuevos = [(lg, w) for lg, w in filas if w in OPERARIOS and lg.timestamp.year == 2030]
    assert nuevos, "el simulador debería haber producido en los puestos nuevos"
    usuarios = {u.id: u for u in db_session.scalars(select(User))}
    for lg, puesto in nuevos:
        ts = lg.timestamp if lg.timestamp.tzinfo else lg.timestamp.replace(tzinfo=UTC)
        assert usuarios[lg.operator_id].email == email_operario(puesto, turno_de(ts))


def test_la_planta_nueva_recibe_la_semana_de_historia_con_nombres_reales(db_session, monkeypatch):
    monkeypatch.setattr(simulador, "_ultimo_relleno", None)
    tenant = _planta(db_session)
    ahora = datetime(2030, 1, 16, 12, tzinfo=MADRID)
    primera = simulador.rellenar_hueco(db_session, ahora, random.Random(5))
    assert primera["pasos"] > 0
    filas = db_session.execute(
        select(OrderLine.workstation_id, User.name)
        .select_from(ProductionLog)
        .join(OrderLine, OrderLine.id == ProductionLog.line_id)
        .join(User, User.id == ProductionLog.operator_id)
        .where(ProductionLog.tenant_id == tenant.id)
    ).all()
    assert {p for p, _ in filas} >= {"P-313", "L-3015", "RB-1"}
    assert not any("Demo" in n for _, n in filas)
    # una segunda llamada seguida no repite la historia
    assert simulador.rellenar_hueco(db_session, ahora, random.Random(5))["pasos"] == 0


def test_ningun_usuario_conserva_nombre_de_demo(db_session):
    _planta(db_session)
    nombres = [u.name for u in db_session.scalars(select(User))]
    assert not [n for n in nombres if "Demo" in n]

