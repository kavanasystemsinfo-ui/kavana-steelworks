"""Tests de autocontroles de calidad (spec 04 §3.2): evaluación y registro.

Contrato portado de QualityService.js / QualityController.js del legacy:
- límites inclusivos (valor == límite pasa), tolerancias asimétricas
- checks sin medición se omiten (no bloquean)
- approved (todo pasa) / rejected (falla algún crítico) / rework (solo no críticos)
- pass_fail/visual: solo true, 'pass' u 'OK' pasan (spec 04 §5)
- largos dinámicos de la orden (meters_per_piece * 1000) aplicados a checks
  cuyo nombre matchea /largo\\s*total|longitud/i
"""

import uuid
from decimal import Decimal

from app.main import app
from app.models import ProductionLog
from app.models.quality import ManufacturingModel, QualityPlanCheck, QualityRecord
from app.routers import quality as quality_router
from app.services.quality import evaluar_inspeccion, evaluar_numerico
from tests.helpers import authed_client_for, make_order, make_order_line


def make_model(db, tenant, code="MOD-001", checks=None):
    """Crea una plantilla con su plan de calidad."""
    modelo = ManufacturingModel(
        tenant_id=tenant.id,
        code=code,
        name=f"Modelo {code}",
        material_code="ACERO-01",
        is_active=True,
    )
    db.add(modelo)
    db.flush()
    for i, c in enumerate(checks or [], start=1):
        db.add(
            QualityPlanCheck(
                manufacturing_model_id=modelo.id,
                position=i,
                name=c["name"],
                tipo=c["tipo"],
                tool_id=c.get("tool_id"),
                nominal_value=c.get("nominal"),
                tolerance_plus=c.get("tol_plus"),
                tolerance_minus=c.get("tol_minus"),
                is_critical=c.get("critical", True),
            )
        )
    db.commit()
    db.refresh(modelo)
    return modelo


def plan_basico():
    return [
        {
            "name": "Largo Total",
            "tipo": "numeric",
            "nominal": Decimal("100"),
            "tol_plus": Decimal("5"),
            "tol_minus": Decimal("5"),
            "tool_id": "Cinta métrica",
        },
        {"name": "Acabado superficial", "tipo": "visual", "critical": True},
        {
            "name": "Peso unitario",
            "tipo": "numeric",
            "nominal": Decimal("50"),
            "tol_plus": Decimal("2"),
            "tol_minus": Decimal("2"),
            "critical": False,
        },
    ]


def _plan_orm(checks):
    return [
        QualityPlanCheck(
            name=c["name"],
            tipo=c["tipo"],
            nominal_value=c.get("nominal"),
            tolerance_plus=c.get("tol_plus"),
            tolerance_minus=c.get("tol_minus"),
            is_critical=c.get("critical", True),
        )
        for c in checks
    ]


# ── Evaluación pura (sin BD) ──────────────────────────────────────────────────


def test_evaluar_numerico_limites_inclusivos():
    assert evaluar_numerico(100, 5, 5, 105) is True  # valor == max pasa
    assert evaluar_numerico(100, 5, 5, 95) is True  # valor == min pasa
    assert evaluar_numerico(100, 5, 5, 105.1) is False
    assert evaluar_numerico(100, 5, 5, 94.9) is False


def test_evaluar_numerico_tolerancias_asimetricas():
    assert evaluar_numerico(100, 10, 5, 108) is True  # 100+10=110 -> pasa
    assert evaluar_numerico(100, 10, 5, 96) is True  # 100-5=95 -> pasa
    assert evaluar_numerico(100, 10, 5, 93) is False  # por debajo del mínimo


def test_evaluar_inspeccion_estados():
    checks = [
        {
            "name": "Largo",
            "tipo": "numeric",
            "nominal": Decimal("100"),
            "tol_plus": Decimal("5"),
            "tol_minus": Decimal("5"),
        },
        {"name": "Visual", "tipo": "visual", "critical": True},
    ]
    plan = _plan_orm(checks)

    # Todo pasa -> approved
    procesadas, estado = evaluar_inspeccion(
        plan,
        [
            {"check_name": "Largo", "value_entered": 100},
            {"check_name": "Visual", "value_entered": True},
        ],
    )
    assert estado == "approved"
    assert len(procesadas) == 2

    # Falla un crítico -> rejected
    _, estado = evaluar_inspeccion(
        plan,
        [
            {"check_name": "Largo", "value_entered": 100},
            {"check_name": "Visual", "value_entered": "PASS"},
        ],
    )
    assert estado == "rejected"


def test_evaluar_inspeccion_rework_si_falla_solo_no_critico():
    checks = [
        {
            "name": "Largo",
            "tipo": "numeric",
            "nominal": Decimal("100"),
            "tol_plus": Decimal("5"),
            "tol_minus": Decimal("5"),
            "critical": False,
        },
        {"name": "Visual", "tipo": "visual", "critical": True},
    ]
    plan = _plan_orm(checks)

    _, estado = evaluar_inspeccion(
        plan,
        [
            {"check_name": "Largo", "value_entered": 200},
            {"check_name": "Visual", "value_entered": True},
        ],
    )
    assert estado == "rework"


def test_evaluar_inspeccion_check_sin_medicion_se_omite():
    plan = _plan_orm(
        [
            {
                "name": "A",
                "tipo": "numeric",
                "nominal": Decimal("100"),
                "tol_plus": Decimal("5"),
                "tol_minus": Decimal("5"),
            },
            {"name": "B", "tipo": "visual", "critical": True},
        ]
    )
    procesadas, estado = evaluar_inspeccion(
        plan, [{"check_name": "A", "value_entered": 100}]
    )
    assert estado == "approved"
    assert len(procesadas) == 1  # B no se contó ni bloqueó


def test_evaluar_inspeccion_pass_fail_normalizacion_estricta():
    plan = _plan_orm([{"name": "Visual", "tipo": "visual", "critical": True}])
    casos = [
        (True, True),
        ("pass", True),
        ("OK", True),
        ("PASS", False),
        ("ok", False),
        ("no", False),
    ]
    for valor, esperado in casos:
        _, estado = evaluar_inspeccion(
            plan, [{"check_name": "Visual", "value_entered": valor}]
        )
        assert estado == ("approved" if esperado else "rejected"), f"valor={valor!r}"


def test_evaluar_inspeccion_valor_no_numerico_falla():
    plan = _plan_orm(
        [
            {
                "name": "Largo",
                "tipo": "numeric",
                "nominal": Decimal("100"),
                "tol_plus": Decimal("5"),
                "tol_minus": Decimal("5"),
            }
        ]
    )
    _, estado = evaluar_inspeccion(
        plan, [{"check_name": "Largo", "value_entered": "abc"}]
    )
    assert estado == "rejected"


def test_evaluar_inspeccion_context_override_nominal():
    plan = _plan_orm(
        [
            {
                "name": "Largo Total",
                "tipo": "numeric",
                "nominal": Decimal("1500"),
                "tol_plus": Decimal("10"),
                "tol_minus": Decimal("10"),
            }
        ]
    )
    # Sin override: 1990 está fuera de 1500±10
    _, estado = evaluar_inspeccion(
        plan, [{"check_name": "Largo Total", "value_entered": 1990}]
    )
    assert estado == "rejected"
    # Con override a 2000: 1990 pasa
    procesadas, estado = evaluar_inspeccion(
        plan,
        [{"check_name": "Largo Total", "value_entered": 1990}],
        context_overrides={"Largo Total": {"nominal_value": Decimal("2000")}},
    )
    assert estado == "approved"
    assert procesadas[0]["nominal"] == Decimal("2000")


# ── Integración con el router ─────────────────────────────────────────────────


def _override_get_db(db_session):
    def _gen():
        yield db_session

    return _gen


def test_registrar_autocontrol_crea_record_y_log(db_session, tenant, user):
    orden = make_order(db_session, tenant, numero="OP-CAL-001")
    make_order_line(db_session, orden, workstation="LINEA-1")
    modelo = make_model(db_session, tenant, checks=plan_basico())

    app.dependency_overrides[quality_router.get_db] = _override_get_db(db_session)
    try:
        client = authed_client_for(db_session, user)
        r = client.post(
            "/api/v1/quality/checks",
            json={
                "order_id": str(orden.id),
                "workstation_id": "LINEA-1",
                "manufacturing_model_id": str(modelo.id),
                "measurements": [
                    {"check_name": "Largo Total", "value_entered": 100},
                    {"check_name": "Acabado superficial", "value_entered": True},
                    {"check_name": "Peso unitario", "value_entered": 50},
                ],
                "notes": "control rutinario",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["msg"] == "Inspección registrada: APPROVED"
    assert body["record"]["overall_status"] == "approved"

    record = db_session.query(QualityRecord).filter_by(order_id=orden.id).one()
    assert record.operator_id == user.id  # el operario de la demo
    assert len(record.measurements) == 3
    assert all(m.is_passed for m in record.measurements)

    log = db_session.query(ProductionLog).filter_by(action="quality_check").one()
    assert log.order_id == orden.id
    assert log.metadata_["status"] == "approved"
    assert log.metadata_["measurementsCount"] == 3


def test_registrar_autocontrol_aplica_largo_dinamico_de_la_orden(
    db_session, tenant, user
):
    orden = make_order(db_session, tenant, numero="OP-CAL-LARGO")
    linea = make_order_line(db_session, orden, workstation="LINEA-1")
    linea.meters_per_piece = Decimal("2.0")  # largo real 2.000 mm
    db_session.commit()
    # Plantilla con nominal viejo (1500): si no hubiera override, 1990 fallaría
    checks = [
        {
            "name": "Largo Total",
            "tipo": "numeric",
            "nominal": Decimal("1500"),
            "tol_plus": Decimal("10"),
            "tol_minus": Decimal("10"),
            "tool_id": "Cinta métrica",
        },
    ]
    modelo = make_model(db_session, tenant, code="MOD-LARGO", checks=checks)

    app.dependency_overrides[quality_router.get_db] = _override_get_db(db_session)
    try:
        client = authed_client_for(db_session, user)
        r = client.post(
            "/api/v1/quality/checks",
            json={
                "order_id": str(orden.id),
                "workstation_id": "LINEA-1",
                "manufacturing_model_id": str(modelo.id),
                "measurements": [{"check_name": "Largo Total", "value_entered": 1990}],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 201, r.text
    assert r.json()["record"]["overall_status"] == "approved"

    record = db_session.query(QualityRecord).filter_by(order_id=orden.id).one()
    medicion = record.measurements[0]
    assert float(medicion.nominal) == 2000.0  # override por meters_per_piece


def test_registrar_autocontrol_rechazado_no_bloquea_produccion(
    db_session, tenant, user
):
    orden = make_order(db_session, tenant, numero="OP-CAL-REJ")
    make_order_line(db_session, orden, workstation="LINEA-1")
    modelo = make_model(db_session, tenant, checks=plan_basico())

    app.dependency_overrides[quality_router.get_db] = _override_get_db(db_session)
    try:
        client = authed_client_for(db_session, user)
        r = client.post(
            "/api/v1/quality/checks",
            json={
                "order_id": str(orden.id),
                "workstation_id": "LINEA-1",
                "manufacturing_model_id": str(modelo.id),
                "measurements": [
                    {"check_name": "Largo Total", "value_entered": 9999},
                    {"check_name": "Acabado superficial", "value_entered": True},
                ],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 201, r.text
    assert r.json()["record"]["overall_status"] == "rejected"


def test_registrar_autocontrol_validaciones(db_session, tenant, user):
    app.dependency_overrides[quality_router.get_db] = _override_get_db(db_session)
    try:
        client = authed_client_for(db_session, user)
        # Sin measurements -> 422 (Pydantic: campo obligatorio)
        r1 = client.post(
            "/api/v1/quality/checks",
            json={
                "order_id": str(uuid.uuid4()),
                "workstation_id": "LINEA-1",
                "manufacturing_model_id": str(uuid.uuid4()),
            },
        )
        assert r1.status_code == 422
        # Plantilla inexistente -> 404
        r2 = client.post(
            "/api/v1/quality/checks",
            json={
                "order_id": str(uuid.uuid4()),
                "workstation_id": "LINEA-1",
                "manufacturing_model_id": str(uuid.uuid4()),
                "measurements": [{"check_name": "X", "value_entered": 1}],
            },
        )
        assert r2.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_get_quality_records_filtra_por_orden(db_session, tenant, user):
    orden = make_order(db_session, tenant, numero="OP-CAL-LIST")
    make_order_line(db_session, orden, workstation="LINEA-1")
    modelo = make_model(db_session, tenant, checks=plan_basico())

    app.dependency_overrides[quality_router.get_db] = _override_get_db(db_session)
    try:
        client = authed_client_for(db_session, user)
        client.post(
            "/api/v1/quality/checks",
            json={
                "order_id": str(orden.id),
                "workstation_id": "LINEA-1",
                "manufacturing_model_id": str(modelo.id),
                "measurements": [{"check_name": "Largo Total", "value_entered": 100}],
            },
        )
        r = client.get(f"/api/v1/quality/records?order_id={orden.id}")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert len(body["records"]) == 1
    assert body["records"][0]["overall_status"] == "approved"
    assert body["records"][0]["operator"]["name"] == user.name
    assert len(body["records"][0]["measurements"]) == 1


def test_get_quality_models_devuelve_plan(db_session, tenant, user):
    modelo = make_model(db_session, tenant, code="MOD-PLAN", checks=plan_basico())

    app.dependency_overrides[quality_router.get_db] = _override_get_db(db_session)
    try:
        client = authed_client_for(db_session, user)
        r = client.get("/api/v1/quality/models")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    body = r.json()
    assert any(m["id"] == str(modelo.id) for m in body)
    con_plan = next(m for m in body if m["id"] == str(modelo.id))
    assert con_plan["code"] == "MOD-PLAN"
    assert len(con_plan["quality_plan"]) == 3
    assert con_plan["quality_plan"][0]["name"] == "Largo Total"
    assert con_plan["quality_plan"][0]["tipo"] == "numeric"
