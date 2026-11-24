"""T-164: el simulador y los paneles leen poco de Neon (caché, bloqueo, plantillas)."""

import asyncio
import random

import pytest
from sqlalchemy import event, select

from app.models import Order, OrderLine, Workstation
from app.services import cache, simulador
from app.services.simulador import ORDENES_ACTIVAS_MIN, BloqueoSimulador, _reponer_ordenes
from tests.helpers import make_order, make_order_line

# --------------------------------------------------------------------------- caché 20 s


@pytest.fixture(autouse=True)
def _cache_limpia():
    cache.clear_cache()
    yield
    cache.clear_cache()


def test_la_cache_no_repite_la_consulta_dentro_de_20_s():
    llamadas = []

    def producir():
        llamadas.append(1)
        return {"n": len(llamadas)}

    primera = cache.cached_call("t1", "turno", (), producir)
    segunda = cache.cached_call("t1", "turno", (), producir)

    assert primera == segunda == {"n": 1}
    assert len(llamadas) == 1


def test_la_cache_no_mezcla_tenants_ni_endpoints_ni_parametros():
    for clave in (("t2", "turno", ()), ("t1", "planta", ()), ("t1", "turno", ("hoy",))):
        assert cache.cached_call(*clave, lambda: "otro") == "otro"
    assert cache.cached_call("t1", "turno", (), lambda: "propio") == "propio"
    assert cache.cached_call("t1", "turno", (), lambda: "no se llama") == "propio"


def test_la_cache_caduca_a_los_20_s(monkeypatch):
    reloj = [1000.0]
    monkeypatch.setattr(cache.time, "monotonic", lambda: reloj[0])
    cache.cached_call("t1", "turno", (), lambda: "viejo")

    reloj[0] += cache.TTL_SECONDS - 1
    assert cache.cached_call("t1", "turno", (), lambda: "nuevo") == "viejo"

    reloj[0] += 2
    assert cache.cached_call("t1", "turno", (), lambda: "nuevo") == "nuevo"


def test_la_cache_no_crece_sin_limite(monkeypatch):
    reloj = [0.0]
    monkeypatch.setattr(cache.time, "monotonic", lambda: reloj[0])
    for i in range(cache.MAX_ENTRADAS + 50):
        reloj[0] += 0.01
        cache.cached_call("t1", "planta", (i,), lambda i=i: i)
    assert len(cache._cache) <= cache.MAX_ENTRADAS


# ------------------------------------------------------------------ bloqueo del simulador


class _Resultado:
    def __init__(self, valor):
        self._valor = valor

    def scalar(self):
        return self._valor


class _ConexionFalsa:
    def __init__(self, obtiene=True, falla_al_soltar=False):
        self.obtiene = obtiene
        self.falla_al_soltar = falla_al_soltar
        self.sentencias = []
        self.cerrada = False
        self.invalidada = False

    def execution_options(self, **_):
        return self

    def execute(self, sentencia, params=None):
        texto = str(sentencia)
        self.sentencias.append(texto)
        if "pg_advisory_unlock" in texto and self.falla_al_soltar:
            raise RuntimeError("conexión caída")
        return _Resultado(self.obtiene)

    def invalidate(self):
        self.invalidada = True

    def close(self):
        self.cerrada = True


class _MotorFalso:
    def __init__(self, conexion, dialecto="postgresql"):
        self._conexion = conexion
        self.dialect = type("D", (), {"name": dialecto})()

    def connect(self):
        return self._conexion


def test_el_bloqueo_se_toma_y_se_suelta_en_la_misma_conexion():
    conn = _ConexionFalsa()
    bloqueo = BloqueoSimulador(_MotorFalso(conn))

    assert bloqueo.tomar() is True
    assert "pg_try_advisory_lock" in conn.sentencias[0]
    assert not conn.cerrada  # la conexión se mantiene mientras se trabaja

    bloqueo.soltar()
    assert "pg_advisory_unlock" in conn.sentencias[-1]
    assert conn.cerrada and not conn.invalidada


def test_si_otra_maquina_tiene_el_bloqueo_no_se_simula():
    conn = _ConexionFalsa(obtiene=False)
    bloqueo = BloqueoSimulador(_MotorFalso(conn))

    assert bloqueo.tomar() is False
    assert conn.cerrada
    bloqueo.soltar()
    assert not any("pg_advisory_unlock" in s for s in conn.sentencias)


def test_si_no_se_puede_soltar_se_cierra_la_conexion_de_verdad():
    conn = _ConexionFalsa(falla_al_soltar=True)
    bloqueo = BloqueoSimulador(_MotorFalso(conn))
    assert bloqueo.tomar() is True

    bloqueo.soltar()

    assert conn.invalidada and conn.cerrada  # así el servidor libera el bloqueo


def test_sin_postgres_no_hay_bloqueo_y_se_simula():
    conn = _ConexionFalsa()
    assert BloqueoSimulador(_MotorFalso(conn, dialecto="sqlite")).tomar() is True
    assert conn.sentencias == []


def test_con_bloqueo_solo_trabaja_quien_lo_tiene(monkeypatch):
    eventos = []

    class Falso:
        def __init__(self, tiene):
            self.tiene = tiene

        def tomar(self):
            return self.tiene

        def soltar(self):
            eventos.append("suelta")

    def trabajo(x):
        eventos.append(f"trabaja {x}")
        return x

    monkeypatch.setattr(simulador, "BloqueoSimulador", lambda: Falso(False))
    assert asyncio.run(simulador._con_bloqueo(trabajo, 1)) is None
    assert eventos == []

    monkeypatch.setattr(simulador, "BloqueoSimulador", lambda: Falso(True))
    assert asyncio.run(simulador._con_bloqueo(trabajo, 2)) == 2
    assert eventos == ["trabaja 2", "suelta"]


def test_con_bloqueo_lo_suelta_aunque_el_trabajo_falle(monkeypatch):
    soltado = []

    class Falso:
        def tomar(self):
            return True

        def soltar(self):
            soltado.append(1)

    def roto():
        raise RuntimeError("fallo")

    monkeypatch.setattr(simulador, "BloqueoSimulador", Falso)
    with pytest.raises(RuntimeError):
        asyncio.run(simulador._con_bloqueo(roto))
    assert soltado == [1]


# ------------------------------------------------------------- órdenes del simulador


def _demo_orden(db, tenant, numero, estado, puestos, cliente="ACME"):
    orden = make_order(db, tenant, numero=numero)
    orden.estado = estado
    orden.cliente = cliente
    orden.notas = "Orden de demostración"
    db.commit()
    for n, puesto in enumerate(puestos, start=1):
        make_order_line(db, orden, workstation=puesto, linea_numero=n)
    return orden


def _planta(db, tenant, n=6):
    for i in range(1, n + 1):
        db.add(Workstation(tenant_id=tenant.id, code=f"P{i}", name=f"Puesto P{i}"))
    db.commit()


def test_la_orden_nueva_va_al_puesto_libre(db_session, tenant):
    """Reparte el trabajo: de las plantillas elige la que menos puestos ocupados pisa."""
    _planta(db_session, tenant)
    for i in range(1, 6):
        _demo_orden(db_session, tenant, f"PL-{i}", "completed", [f"P{i}"])
    for i in range(1, ORDENES_ACTIVAS_MIN):  # ocupan P1..P4; falta una
        _demo_orden(db_session, tenant, f"AC-{i}", "active", [f"P{i}"])
    simulador._plantillas_cache.clear()

    acciones = _reponer_ordenes(db_session, tenant.id, random.Random(1))

    assert len(acciones) == 1
    nueva = db_session.scalar(
        select(Order).where(Order.tenant_id == tenant.id, Order.notas.like("Orden generada%"))
    )
    lineas = db_session.scalars(select(OrderLine).where(OrderLine.order_id == nueva.id)).all()
    assert [ln.workstation_id for ln in lineas] == ["P5"]


def test_con_ordenes_de_sobra_solo_cuenta_y_no_lee_plantillas(db_session, tenant):
    _planta(db_session, tenant)
    _demo_orden(db_session, tenant, "PL-1", "completed", ["P1"])
    for i in range(ORDENES_ACTIVAS_MIN):
        _demo_orden(db_session, tenant, f"AC-{i}", "active", [f"P{i + 1}"])

    sentencias = []
    motor = db_session.get_bind()

    def registrar(conn, cursor, statement, *args):
        sentencias.append(statement)

    event.listen(motor, "before_cursor_execute", registrar)
    try:
        assert _reponer_ordenes(db_session, tenant.id, random.Random(1)) == []
    finally:
        event.remove(motor, "before_cursor_execute", registrar)

    assert len(sentencias) == 1 and "count" in sentencias[0].lower()


def test_la_estructura_de_plantillas_se_lee_una_vez(db_session, tenant):
    _planta(db_session, tenant)
    for i in range(1, 4):
        _demo_orden(db_session, tenant, f"PL-{i}", "completed", [f"P{i}", f"P{i + 1}"])
    simulador._plantillas_cache.clear()

    sentencias = []
    motor = db_session.get_bind()

    def registrar(conn, cursor, statement, *args):
        sentencias.append(statement)

    event.listen(motor, "before_cursor_execute", registrar)
    try:
        primera = simulador._estructura_plantillas(db_session, tenant.id)
        leidas_primera = len(sentencias)
        segunda = simulador._estructura_plantillas(db_session, tenant.id)
    finally:
        event.remove(motor, "before_cursor_execute", registrar)

    assert primera == segunda and len(primera) == 3
    assert len(sentencias) == leidas_primera + 1  # la segunda vez solo hace el COUNT
