"""E2E de incidencias de planta contra PostgreSQL real (spec 04 §3.3).

Se ejecuta contra una BD limpia migrada (kavana_steelworks_qual). La URL se
pasa por STEELWORKS_DATABASE_URL (nunca escrita en el script: quirk de
secretos). Valida CHECK/FK reales y el flujo: alta -> listado -> resolución
financiera -> OEE con downtime.
"""

import os
import sys

from fastapi.testclient import TestClient

from app.main import app
from app.models import Order, Tenant
from app.models.incidencia import Incidencia
from app.services.events import broker
from app.services.oee_kpis import calcular_oee
from app.services.seed_demo import seed_demo

if not os.environ.get("STEELWORKS_DATABASE_URL"):
    sys.exit("Falta STEELWORKS_DATABASE_URL")


def main() -> None:
    from sqlalchemy import create_engine

    from app.core.config import get_settings
    from app.core.database import Base, SessionLocal
    from app.services.auth import login

    # BD limpia desde cero (mismo patrón que los demás E2E): sin datos
    # residuales de ejecuciones anteriores.
    engine = create_engine(get_settings().sqlalchemy_database_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    engine.dispose()

    db = SessionLocal()
    seed_demo(db)
    tenant = db.query(Tenant).filter_by(name="Demo Aceros").one()
    orden = db.query(Order).filter_by(tenant_id=tenant.id, numero="OP-DEMO-001").one()

    # Login con los usuarios demo (password kavana, Fase 6)
    token_operario = login(db, tenant.id, "operario@demo.local", "kavana")
    token_supervisor = login(db, tenant.id, "supervisor@demo.local", "kavana")
    db.close()

    client = TestClient(app)
    op = {"Authorization": f"Bearer {token_operario}"}
    sup = {"Authorization": f"Bearer {token_supervisor}"}

    # 1. Alta: asocia la orden activa de LINEA-1 y nace en 'abierta'
    r = client.post(
        "/api/v1/incidencias",
        headers=op,
        json={
            "linea_id": "LINEA-1",
            "descripcion": "Atasco de bobina en la cizalla",
            "tipo": "maquina",
        },
    )
    assert r.status_code == 201, r.text
    inc = r.json()["incidencia"]
    assert inc["estado"] == "abierta"
    assert inc["order_id"] == str(orden.id)
    assert inc["puesto"] == "LINEA-1"
    assert inc["operario"]["name"] == "Operario Demo"

    # 2. Evento publicado en el broker del tenant
    assert any(e["tipo"] == "nueva_incidencia" for e in broker.get_events(tenant.id))

    # 3. Resolución financiera + cierre (tiempo de parada y coste)
    r = client.patch(
        f"/api/v1/incidencias/{inc['id']}",
        headers=sup,
        json={
            "estado": "cerrada",
            "resolucion_tipo": "reparacion",
            "resolucion_descripcion": "Limpieza de la cizalla",
            "tiempo_parada_min": 45,
            "coste": 85.5,
        },
    )
    assert r.status_code == 200, r.text
    actualizada = r.json()["incidencia"]
    assert actualizada["estado"] == "cerrada"
    assert float(actualizada["tiempo_parada_min"]) == 45
    assert float(actualizada["coste"]) == 85.5
    assert actualizada["responsable"]["name"] == "Supervisor Demo"
    assert len(actualizada["historial"]) == 2

    # 4. Listado ordenado (solo supervisor)
    r = client.get("/api/v1/incidencias", headers=sup)
    assert r.status_code == 200, r.text
    assert len(r.json()["incidencias"]) == 1

    # 5. OEE: el downtime de la incidencia resta disponibilidad
    oee = calcular_oee(db=SessionLocal(), tenant_id=tenant.id)
    assert oee["raw"]["total_downtime_min"] == 45, oee
    assert "total_downtime_min" in oee["raw"]

    # 6. Flujo QR + móvil (spec 04 §3.3.2): sesión -> foto -> incidencia
    r = client.post("/api/v1/incidencias/upload-session", headers=op)
    assert r.status_code == 200, r.text
    sesion = r.json()
    assert sesion["status"] == "pending"

    png = b"\x89PNG\r\n\x1a\n" + b"e2e-foto"
    r = client.post(
        f"/api/v1/incidencias/upload-mobile/{sesion['session_id']}",
        files={"foto": ("foto.png", png, "image/png")},
    )
    assert r.status_code == 200, r.text

    r = client.get(f"/api/v1/incidencias/upload-session/{sesion['session_id']}")
    assert r.status_code == 200, r.text
    estado = r.json()
    assert estado["status"] == "uploaded"
    assert estado["has_photo"] is True
    assert estado["photo_data_url"].startswith("data:image/png;base64,")

    r = client.post(
        "/api/v1/incidencias",
        headers=op,
        json={
            "linea_id": "LINEA-1",
            "descripcion": "Incidencia con evidencia QR",
            "tipo": "seguridad",
            "photo_session_id": sesion["session_id"],
        },
    )
    assert r.status_code == 201, r.text
    inc_foto = r.json()["incidencia"]
    assert inc_foto["foto_data_url"].startswith("data:image/png;base64,")
    assert inc_foto["foto_size"] == len(png)

    # Sesión 'used' y bytes temporales liberados
    from app.models.incidencia_upload import IncidenciaUploadSession

    db = SessionLocal()
    fila = (
        db.query(IncidenciaUploadSession)
        .filter_by(session_id=sesion["session_id"])
        .one()
    )
    assert fila.status == "used", fila.status
    assert fila.photo is None
    db.close()

    # 7. Check real: tipo inválido -> 400 (el CHECK de PG no llega a saltar
    # porque el servicio valida antes; verificar el CHECK con psql en la migración)
    r = client.post(
        "/api/v1/incidencias",
        headers=op,
        json={"linea_id": "LINEA-1", "descripcion": "x", "tipo": "hack"},
    )
    assert r.status_code == 400, r.text

    db = SessionLocal()
    assert db.query(Incidencia).count() == 2
    db.close()

    print(
        "E2E INCIDENCIAS OK: alta, orden activa, broker, resolucion, OEE downtime, foto QR"
    )


if __name__ == "__main__":
    main()
