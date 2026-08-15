"""E2E de autocontroles de calidad contra PostgreSQL real (spec 04 §3.2).

Se ejecuta contra una BD limpia migrada (kavana_steelworks_qual) para validar
los CHECK y FKs reales de PG que sqlite no detecta. La URL se pasa por
STEELWORKS_DATABASE_URL (nunca escrita en el script: quirk de secretos).
"""

import os
import sys

from fastapi.testclient import TestClient

from app.main import app
from app.models import Order, ProductionLog, Tenant
from app.models.quality import ManufacturingModel, QualityRecord
from app.services.seed_demo import seed_demo

# El import de app.core.database usa STEELWORKS_DATABASE_URL del entorno.
if not os.environ.get("STEELWORKS_DATABASE_URL"):
    sys.exit("Falta STEELWORKS_DATABASE_URL")


def main() -> None:
    from app.core.database import SessionLocal

    db = SessionLocal()
    seed_demo(db)  # idempotente: crea tenant, bobina, orden, modelo de calidad
    tenant = db.query(Tenant).filter_by(name="Demo Aceros").one()
    orden = db.query(Order).filter_by(tenant_id=tenant.id, numero="OP-DEMO-001").one()
    modelo = db.query(ManufacturingModel).filter_by(code="PERFIL-DEMO-001").one()
    db.close()

    client = TestClient(app)

    # 1. Plantillas: el modelo demo expone su plan de controles
    r = client.get("/api/v1/quality/models")
    assert r.status_code == 200, r.text
    planes = [m for m in r.json() if m["code"] == "PERFIL-DEMO-001"]
    assert len(planes) == 1, r.text
    assert len(planes[0]["quality_plan"]) == 3, r.text

    # 2. Autocontrol OK: largo 1990 (dentro de 2000±10), visual True, espesor 1.2
    r = client.post(
        "/api/v1/quality/checks",
        json={
            "order_id": str(orden.id),
            "workstation_id": "LINEA-1",
            "manufacturing_model_id": str(modelo.id),
            "measurements": [
                {"check_name": "Largo Total", "value_entered": 1990},
                {"check_name": "Acabado superficial", "value_entered": True},
                {"check_name": "Espesor", "value_entered": 1.2},
            ],
            "notes": "e2e ok",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["record"]["overall_status"] == "approved", r.text

    # 3. Autocontrol RECHAZADO: se persiste igual, no bloquea (spec 04 regla 7)
    r = client.post(
        "/api/v1/quality/checks",
        json={
            "order_id": str(orden.id),
            "workstation_id": "LINEA-1",
            "manufacturing_model_id": str(modelo.id),
            "measurements": [
                {"check_name": "Largo Total", "value_entered": 1990},
                {"check_name": "Acabado superficial", "value_entered": True},
                {"check_name": "Espesor", "value_entered": 5},
            ],
            "notes": "e2e rechazado",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["record"]["overall_status"] == "rejected", r.text

    # 4. Registros filtrados por orden
    r = client.get(f"/api/v1/quality/records?order_id={orden.id}")
    assert r.status_code == 200, r.text
    assert len(r.json()["records"]) == 2, r.text

    # 5. Trazabilidad: 2 eventos quality_check (best-effort, no rompió nada)
    db = SessionLocal()
    n_logs = db.query(ProductionLog).filter_by(action="quality_check").count()
    assert n_logs == 2, n_logs
    n_records = db.query(QualityRecord).count()
    assert n_records == 2, n_records
    db.close()

    print("E2E QUALITY OK: migracion, seed, approved, rejected, records, trace")


if __name__ == "__main__":
    main()
