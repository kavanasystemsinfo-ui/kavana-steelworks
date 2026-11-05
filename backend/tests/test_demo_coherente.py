"""La demo siempre cuenta una planta coherente: órdenes repartidas por el flujo, incidencias
que se abren y se cierran solas, y reparación idempotente de los datos que ya existían."""

import asyncio
import random
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models import Incidencia, Order, OrderLine, ProductionLog, User, Workstation
from app.services import simulador
from app.services.seed_demo import buscar_tenant_demo, seed_demo
from app.services.seed_estanterias import (
    RECETAS_FLUJO,
    asegurar_flujo_demo,
    reparar_demo_coherente,
    seed_estanterias,
)
from app.services.simulador import rellenar_hueco

MADRID = ZoneInfo("Europe/Madrid")
PUESTOS_FLUJO = {"CORTE-1", "PUNZ-1", "DOBL-1", "SOL-1", "GALV-1", "MONT-1", "MONT-2"}
# Miércoles 16-01-2030 12:00 en planta: muy posterior a cualquier dato de la semilla
AHORA = datetime(2030, 1, 16, 12, tzinfo=MADRID)


@pytest.fixture(autouse=True)
def _sin_marca_de_relleno(monkeypatch):
    monkeypatch.setattr(simulador, "_ultimo_relleno", None)


def _demo(db):
    seed_demo(db)
    seed_estanterias(db)
    return buscar_tenant_demo(db)


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


def test_las_recetas_de_flujo_se_crean_una_sola_vez(db_session):
    tenant = _demo(db_session)
    primera = asegurar_flujo_demo(db_session, tenant.id)
    segunda = asegurar_flujo_demo(db_session, tenant.id)
    assert primera == len(RECETAS_FLUJO)
    assert segunda == 0
    plantillas = db_session.scalars(
        select(Order).where(Order.tenant_id == tenant.id, Order.numero.like("OP-EST-27%"))
    ).all()
    assert len(plantillas) == len(RECETAS_FLUJO)
    assert all(o.estado == "completed" and o.cliente != "Cliente demo" for o in plantillas)
    # Cada receta recorre al menos tres puestos distintos del flujo, en cascada
    for orden in plantillas:
        puestos = [ln.workstation_id for ln in sorted(orden.lines, key=lambda x: x.linea_numero)]
        assert len(set(puestos)) >= 4
        assert set(puestos) <= PUESTOS_FLUJO


def test_reparar_deja_la_demo_coherente_y_es_idempotente(db_session):
    tenant = _demo(db_session)
    operario = db_session.scalar(select(User).where(User.email == "operario@demo.local"))
    ordenes_demo = db_session.scalars(
        select(Order).where(Order.tenant_id == tenant.id, Order.numero == "OP-DEMO-001")
    ).all()
    for o in ordenes_demo:
        o.cliente = "Cliente demo"
    vieja = Incidencia(
        tenant_id=tenant.id, linea_id="LINEA-1", puesto="LINEA-1", operario_id=operario.id,
        descripcion="fre", tipo="maquina", estado="abierta",
    )
    db_session.add(vieja)
    db_session.flush()
    vieja.created_at = datetime.now(UTC) - timedelta(hours=1956)
    db_session.commit()

    cambios = reparar_demo_coherente(db_session, tenant.id)
    db_session.commit()

    assert cambios["clientes"] >= 1
    assert cambios["incidencias_cerradas"] == 1
    assert cambios["puestos_desactivados"] == 3
    assert cambios["ordenes_canceladas"] >= 1
    db_session.expire_all()
    assert vieja.estado == "resuelta"
    assert not db_session.scalars(
        select(Order).where(Order.tenant_id == tenant.id, Order.cliente == "Cliente demo")
    ).all()
    for code in ("LINEA-1", "LINEA-2", "LINEA-3"):
        w = db_session.scalar(
            select(Workstation).where(Workstation.tenant_id == tenant.id, Workstation.code == code)
        )
        assert w is not None and w.is_active is False  # desactivado, nunca borrado
    # Nada se borra: la incidencia sigue ahí
    assert db_session.get(Incidencia, vieja.id) is not None

    de_nuevo = reparar_demo_coherente(db_session, tenant.id)
    assert de_nuevo == {
        "clientes": 0, "incidencias_cerradas": 0, "puestos_desactivados": 0,
        "ordenes_canceladas": 0,
    }


class TestPlantaViva:
    @pytest.fixture()
    def planta(self, db_session):
        tenant = _demo(db_session)
        asegurar_flujo_demo(db_session, tenant.id)
        reparar_demo_coherente(db_session, tenant.id)
        db_session.commit()
        rellenar_hueco(db_session, AHORA, random.Random(11))
        return tenant

    def test_el_trabajo_se_reparte_por_el_flujo(self, db_session, planta):
        puestos = {
            ln.workstation_id
            for ln in db_session.scalars(
                select(OrderLine)
                .join(ProductionLog, ProductionLog.line_id == OrderLine.id)
                .where(ProductionLog.timestamp > (AHORA - timedelta(days=7)).astimezone(UTC))
            )
        }
        assert len(puestos & PUESTOS_FLUJO) >= 6, puestos

    def test_siempre_hay_varias_ordenes_activas_con_cliente_creible(self, db_session, planta):
        activas = db_session.scalars(
            select(Order).where(Order.tenant_id == planta.id, Order.estado == "active")
        ).all()
        assert len(activas) >= simulador.ORDENES_ACTIVAS_MIN
        assert all(o.cliente and o.cliente != "Cliente demo" for o in activas)

    def test_las_incidencias_se_abren_y_se_cierran_en_minutos(self, db_session, planta):
        todas = db_session.scalars(
            select(Incidencia).where(Incidencia.tenant_id == planta.id)
        ).all()
        simuladas = [i for i in todas if i.resolucion_descripcion == (
            "Resuelta en planta (simulador demo)."
        ) or i.estado in ("abierta", "en_revision")]
        assert simuladas, "en una semana de planta tiene que haber habido alguna incidencia"
        abiertas = [i for i in todas if i.estado in ("abierta", "en_revision")]
        assert len(abiertas) <= 1
        for inc in abiertas:
            edad = AHORA.astimezone(UTC) - _aware(inc.created_at)
            assert edad < timedelta(hours=24)
        for inc in todas:
            if inc.resolucion_descripcion == "Resuelta en planta (simulador demo).":
                assert 15 <= float(inc.tiempo_parada_min) <= 150

    def test_un_puesto_parado_no_produce_mientras_dura_la_incidencia(self, db_session, planta):
        for inc in db_session.scalars(select(Incidencia).where(Incidencia.tenant_id == planta.id)):
            if inc.resolucion_descripcion != "Resuelta en planta (simulador demo).":
                continue
            fin = _aware(inc.created_at) + timedelta(minutes=float(inc.tiempo_parada_min))
            produccion = db_session.scalars(
                select(ProductionLog)
                .join(OrderLine, OrderLine.id == ProductionLog.line_id)
                .where(
                    OrderLine.workstation_id == inc.puesto,
                    ProductionLog.action == "produce",
                    ProductionLog.timestamp > inc.created_at.replace(tzinfo=None)
                    + timedelta(minutes=1),
                    ProductionLog.timestamp < fin.replace(tzinfo=None) - timedelta(minutes=1),
                )
            ).all()
            assert produccion == [], (inc.puesto, inc.created_at)


def test_el_bucle_rellena_el_hueco_al_arrancar(monkeypatch):
    llamadas = []

    def falso_relleno():
        llamadas.append("relleno")
        return {"pasos": 3}

    async def dormir_y_parar(_segundos):
        raise asyncio.CancelledError

    monkeypatch.setattr(simulador, "_relleno_en_sesion", falso_relleno)
    monkeypatch.setattr(simulador.asyncio, "sleep", dormir_y_parar)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(simulador.bucle_simulador(5))

    assert llamadas == ["relleno"]
