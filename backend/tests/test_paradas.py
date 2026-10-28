"""Tests de las paradas con un toque (services/paradas.py, fase 3 del rediseño
del panel de operario, Jorge 28-10)."""

from datetime import UTC, datetime, timedelta

from app.main import app
from app.models import Incidencia, Parada
from app.routers import auth as auth_router
from app.routers import production as production_router
from app.services.paradas import paradas_en
from tests.helpers import authed_client_for


def _cliente(db, user):
    def _gen():
        yield db

    app.dependency_overrides[production_router.get_db] = _gen
    app.dependency_overrides[auth_router.get_db] = _gen
    return authed_client_for(db, user)


def test_parar_y_volver_a_producir(db_session, tenant, user):
    cliente = _cliente(db_session, user)

    r = cliente.post("/api/v1/production/paradas", json={"puesto": "LINEA-1", "motivo": "limpieza"})
    assert r.status_code == 201, r.text
    parada = r.json()
    assert parada["motivo_texto"] == "limpieza" and parada["fin"] is None
    assert cliente.get("/api/v1/production/paradas/abierta").json()["id"] == parada["id"]
    # Una sola parada abierta por operario
    otra = cliente.post(
        "/api/v1/production/paradas", json={"puesto": "LINEA-1", "motivo": "averia"}
    )
    assert otra.status_code == 400

    cambio = cliente.patch(f"/api/v1/production/paradas/{parada['id']}", json={"motivo": "averia"})
    assert cambio.json()["motivo"] == "averia"
    fin = cliente.post(
        f"/api/v1/production/paradas/{parada['id']}/fin", json={"nota": "cuchilla rota"}
    )
    assert fin.status_code == 200
    assert fin.json()["fin"] is not None and fin.json()["nota"] == "cuchilla rota"
    assert cliente.get("/api/v1/production/paradas/abierta").json() is None


def test_motivo_no_valido(db_session, tenant, user):
    cliente = _cliente(db_session, user)
    r = cliente.post("/api/v1/production/paradas", json={"puesto": "LINEA-1", "motivo": "siesta"})
    assert r.status_code == 400


def test_cerrar_la_jornada_cierra_la_parada(db_session, tenant, user):
    cliente = _cliente(db_session, user)
    cliente.post("/api/v1/production/paradas", json={"puesto": "LINEA-1", "motivo": "ajustes"})
    assert cliente.post("/api/v1/auth/close-shift").status_code == 200
    assert db_session.query(Parada).one().fin is not None


def test_paradas_en_suma_paradas_e_incidencias_recortadas(db_session, tenant, user):
    ahora = datetime.now(UTC)
    desde, hasta = ahora - timedelta(hours=2), ahora
    db_session.add_all(
        [
            # Empezó antes de la ventana: cuenta 30 min (desde el inicio)
            Parada(
                tenant_id=tenant.id, puesto="LINEA-1", operario_id=user.id, motivo="cambio_modelo",
                inicio=desde - timedelta(minutes=10), fin=desde + timedelta(minutes=30),
            ),
            # Abierta: cuenta hasta ahora (15 min)
            Parada(
                tenant_id=tenant.id, puesto="LINEA-2", operario_id=user.id, motivo="averia",
                inicio=ahora - timedelta(minutes=15),
            ),
            Incidencia(
                tenant_id=tenant.id, puesto="LINEA-3", operario_id=user.id, descripcion="motor",
                tipo="maquina", estado="cerrada", tiempo_parada_min=20,
                created_at=ahora - timedelta(minutes=50),
            ),
        ]
    )
    db_session.commit()

    paradas = {p["puesto"]: p for p in paradas_en(db_session, tenant.id, desde, hasta)}
    assert round(paradas["LINEA-1"]["minutos"]) == 30
    assert paradas["LINEA-1"]["motivo"] == "cambio de modelo"
    assert round(paradas["LINEA-2"]["minutos"]) == 15 and paradas["LINEA-2"]["abierta"]
    assert paradas["LINEA-3"]["minutos"] == 20
