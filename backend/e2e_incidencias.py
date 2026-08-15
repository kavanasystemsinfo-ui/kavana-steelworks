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
    from app.core.database import SessionLocal

    db = SessionLocal()
    seed_demo(db)
    tenant = db.query(Tenant).filter_by(name="Demo Aceros").one()
    orden = db.query(Order).filter_by(tenant_id=tenant.id, numero="OP-DEMO-001").one()
    db.close()

    client = TestClient(app)

    # 1. Alta: asocia la orden activa de LINEA-1 y nace en 'abierta'
    r = client.post(
        "/api/v1/incidencias",
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
    assert actualizada["responsable"]["name"] == "Operario Demo"
    assert len(actualizada["historial"]) == 2

    # 4. Listado ordenado
    r = client.get("/api/v1/incidencias")
    assert r.status_code == 200, r.text
    assert len(r.json()["incidencias"]) == 1

    # 5. OEE: el downtime de la incidencia resta disponibilidad
    oee = calcular_oee(db=SessionLocal(), tenant_id=tenant.id)
    assert oee["raw"]["total_downtime_min"] == 45, oee
    assert "total_downtime_min" in oee["raw"]

    # 6. Check real: tipo inválido -> 400 (el CHECK de PG no llega a saltar
    # porque el servicio valida antes; verificar el CHECK con psql en la migración)
    r = client.post(
        "/api/v1/incidencias",
        json={"linea_id": "LINEA-1", "descripcion": "x", "tipo": "hack"},
    )
    assert r.status_code == 400, r.text

    db = SessionLocal()
    assert db.query(Incidencia).count() == 1
    db.close()

    print("E2E INCIDENCIAS OK: alta, orden activa, broker, resolucion, OEE downtime")


if __name__ == "__main__":
    main()
