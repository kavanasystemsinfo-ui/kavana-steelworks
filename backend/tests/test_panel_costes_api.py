"""Tests del endpoint de la vista Costes del panel de mando.

Cubre lo que la Fase 1 no podía cubrir: contrato HTTP, roles, aislamiento entre
empresas y exportación CSV para Excel.

Los datos de prueba se crean en el instante actual (``datetime.now(UTC)``), que
siempre cae dentro de la ventana natural del periodo pedido, así que los tests
no dependen del día en que se ejecuten.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Workstation
from app.routers import supervisor as supervisor_router
from tests.helpers import auth_headers, make_material, make_order, make_order_line, make_tenant

URL = "/api/v1/supervisor/panel/costes"


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _orden(db, tenant, numero="OP-API", *, kg=100.0, coste_material=200.0, coste_linea=300.0):
    """Orden completada con una línea en kg, completada en este instante."""
    material = make_material(db, tenant, code=f"MAT-{numero}", cost=2.0)
    order = make_order(db, tenant, numero=numero)
    order.estado = "completed"

    linea = make_order_line(
        db, order, workstation="LINEA-1", total_quantity=10.0, material=material
    )
    linea.target_material_unit = "kg"
    linea.target_material_qty = Decimal(str(kg))
    linea.real_material_qty = Decimal(str(kg))
    linea.real_material_cost = Decimal(str(coste_material))
    linea.real_cost = Decimal(str(coste_linea))

    order.updated_at = datetime.now(UTC)
    db.commit()
    return order


@pytest.fixture()
def panel(db_session):
    """(tenant, rol) -> TestClient autenticado contra la BD de test."""

    def _override_get_db():
        yield db_session

    app.dependency_overrides[supervisor_router.get_db] = _override_get_db

    def _cliente(tenant, role="supervisor", email=None):
        client = TestClient(app)
        client.headers.update(auth_headers(db_session, tenant, role=role, email=email))
        return client

    yield _cliente
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Roles
# --------------------------------------------------------------------------- #
def test_supervisor_ve_el_panel(db_session, tenant, panel):
    _orden(db_session, tenant)

    r = panel(tenant).get(URL)

    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["periodo"] == "mes"
    assert datos["ordenes_completadas"] == 1
    assert datos["kg_total"] == 100.0
    assert datos["coste_total"] == 300.0  # 200 material + 100 mano de obra
    assert datos["coste_kg"] == {"valor": 3.0, "periodo_anterior": 0.0, "objetivo": None}


def test_admin_hereda_el_panel(db_session, tenant, panel):
    r = panel(tenant, role="admin").get(URL)

    assert r.status_code == 200, r.text
    assert r.json()["periodo"] == "mes"


def test_operario_no_puede_ver_el_panel(db_session, tenant, panel):
    r = panel(tenant, role="operator").get(URL)

    assert r.status_code == 403, r.text


def test_materias_no_puede_ver_el_panel(db_session, tenant, panel):
    r = panel(tenant, role="materials").get(URL)

    assert r.status_code == 403, r.text


def test_sin_token_devuelve_401(db_session, tenant, panel):
    panel(tenant)  # registra el override de BD
    r = TestClient(app).get(URL)

    assert r.status_code == 401, r.text


# --------------------------------------------------------------------------- #
# Contrato
# --------------------------------------------------------------------------- #
def test_contrato_completo_del_panel(db_session, tenant, panel):
    _orden(db_session, tenant)

    datos = panel(tenant).get(URL).json()

    assert set(datos) == {
        "periodo",
        "desde",
        "hasta",
        "coste_kg",
        "coste_total",
        "kg_total",
        "lineas_metros_excluidas",
        "ordenes_completadas",
        "desviacion",
        "chatarra",
        "reparto",
        "coste_paradas",
        "tendencia",
        "ordenes",
    }
    assert [bloque["clave"] for bloque in datos["reparto"]] == [
        "material",
        "mano_obra",
        "chatarra",
    ]
    assert sum(bloque["euros"] for bloque in datos["reparto"]) == pytest.approx(
        datos["coste_total"]
    )
    assert sum(bloque["pct"] for bloque in datos["reparto"]) == pytest.approx(100.0)
    assert len(datos["tendencia"]) == 8
    assert datos["ordenes"][0]["numero"] == "OP-API"
    assert datos["ordenes"][0]["causa"] == "Dentro de lo normal"
    assert datos["coste_paradas"] == {"total": 0.0, "por_tipo": [], "horas": 0.0}


def test_costes_de_paradas_en_el_endpoint(db_session, tenant, user, panel):
    from app.models import Incidencia

    db_session.add(
        Workstation(
            tenant_id=tenant.id,
            code="PLEG-1",
            name="Plegadora",
            hourly_cost=Decimal("30.00"),
        )
    )
    incidencia = Incidencia(
        tenant_id=tenant.id,
        puesto="PLEG-1",
        operario_id=user.id,
        descripcion="Atasco",
        tipo="maquina",
        estado="resuelta",
        tiempo_parada_min=Decimal("90"),
    )
    incidencia.created_at = datetime.now(UTC)
    db_session.add(incidencia)
    db_session.commit()

    paradas = panel(tenant).get(URL).json()["coste_paradas"]

    assert paradas["total"] == 45.0  # 1,5 h × 30 €/h
    assert paradas["horas"] == 1.5
    assert paradas["por_tipo"] == [{"tipo": "maquina", "etiqueta": "Máquina", "euros": 45.0}]


@pytest.mark.parametrize("periodo", ["semana", "mes", "trimestre"])
def test_periodos_validos(db_session, tenant, panel, periodo):
    _orden(db_session, tenant)

    r = panel(tenant).get(URL, params={"periodo": periodo})

    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["periodo"] == periodo
    assert datos["ordenes_completadas"] == 1
    assert datos["desde"] < datos["hasta"]


@pytest.mark.parametrize("formato", ["json", "csv"])
def test_periodo_invalido_devuelve_400(db_session, tenant, panel, formato):
    r = panel(tenant).get(URL, params={"periodo": "decada", "formato": formato})

    assert r.status_code == 400, r.text
    assert "periodo" in r.json()["detail"]


def test_formato_invalido_devuelve_400(db_session, tenant, panel):
    r = panel(tenant).get(URL, params={"formato": "xml"})

    assert r.status_code == 400, r.text
    assert "formato" in r.json()["detail"]


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #
def test_csv_para_excel(db_session, tenant, panel):
    _orden(db_session, tenant)

    r = panel(tenant).get(URL, params={"formato": "csv"})

    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert "panel-costes-mes-" in r.headers["content-disposition"]
    assert ".csv" in r.headers["content-disposition"]

    cuerpo = r.content.decode("utf-8")
    assert cuerpo.startswith("\ufeff"), "Excel necesita BOM para detectar UTF-8"
    assert "\ufeffPanel de costes;mes;" in cuerpo

    lineas = cuerpo.lstrip("\ufeff").splitlines()
    assert "Resumen;Valor" in lineas
    assert "€/kg;3,00" in lineas  # coma decimal, dos decimales
    assert "Coste total (€);300,00" in lineas
    assert "Material;200,00;66,67" in lineas
    assert "Reparto del coste;Euros;%" in lineas
    assert "Orden;Producto;kg;Estimado (€);Real (€);Desviación (€);Desviación (%);Causa" in lineas
    assert "OP-API;MAT-OP-API;100,00;200,00;200,00;0,00;0,00;Dentro de lo normal" in lineas
    assert "3.00" not in cuerpo, "ningún decimal con punto: Excel español lo lee como texto"
    assert len(lineas[-1].split(";")) == 8


def test_csv_sin_datos_no_inventa_cifras(db_session, tenant, panel):
    r = panel(tenant).get(URL, params={"formato": "csv"})

    cuerpo = r.content.decode("utf-8").lstrip("\ufeff")
    lineas = cuerpo.splitlines()

    assert "€/kg;0,00" in lineas
    assert "Objetivo €/kg;" in lineas, "sin objetivo configurado, la celda va vacía"
    assert "Coste total (€);0,00" in lineas
    assert not any(linea.startswith("OP-") for linea in lineas)


def test_csv_respeta_el_periodo_pedido(db_session, tenant, panel):
    r = panel(tenant).get(URL, params={"periodo": "trimestre", "formato": "csv"})

    assert r.status_code == 200, r.text
    assert r.content.decode("utf-8").startswith("\ufeffPanel de costes;trimestre;")
    assert "panel-costes-trimestre-" in r.headers["content-disposition"]


# --------------------------------------------------------------------------- #
# Aislamiento entre empresas
# --------------------------------------------------------------------------- #
def test_aislamiento_entre_dos_tenants_json(db_session, tenant, panel):
    otra = make_tenant(db_session, name="Aceros Otra")
    _orden(db_session, tenant, "OP-A")
    _orden(db_session, otra, "OP-B")

    datos_a = panel(tenant, email="supervisor-a@test.local").get(URL).json()
    datos_b = panel(otra, role="supervisor", email="supervisor-b@test.local").get(URL).json()

    assert datos_a["ordenes_completadas"] == 1
    assert [o["numero"] for o in datos_a["ordenes"]] == ["OP-A"]
    assert datos_a["kg_total"] == 100.0

    assert datos_b["ordenes_completadas"] == 1
    assert [o["numero"] for o in datos_b["ordenes"]] == ["OP-B"]


def test_aislamiento_entre_dos_tenants_csv(db_session, tenant, panel):
    otra = make_tenant(db_session, name="Aceros Otra")
    _orden(db_session, tenant, "OP-A")
    _orden(db_session, otra, "OP-B")

    csv_a = (
        panel(tenant, email="supervisor-a@test.local")
        .get(URL, params={"formato": "csv"})
        .content.decode("utf-8")
    )

    assert "OP-A" in csv_a
    assert "OP-B" not in csv_a, "el CSV de una empresa no puede mostrar órdenes de otra"


def test_tenant_sin_datos_no_ve_nada_ajeno(db_session, tenant, panel):
    """El filtro sale siempre del token: la empresa vacía no hereda datos de otra."""
    _orden(db_session, tenant, "OP-A")
    vacia = make_tenant(db_session, name="Aceros Vacía")

    datos = panel(vacia, email="supervisor-vacio@test.local").get(URL).json()

    assert datos["ordenes_completadas"] == 0
    assert datos["ordenes"] == []
    assert datos["coste_total"] == 0.0
