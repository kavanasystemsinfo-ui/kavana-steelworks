"""Chatarra prevista y de más por modelo (services/chatarra_modelo.py)."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.models import MaterialConsumo, ProductionLog
from app.models.quality import ManufacturingModel
from app.services.chatarra_modelo import desglose_chatarra, referencia_aprendida
from app.services.informe_turno import informe_turno
from tests.helpers import make_material, make_order, make_order_line

D = Decimal


def _modelo(db, tenant, code="MOD-1", peso=None):
    m = ManufacturingModel(tenant_id=tenant.id, code=code, name=code, peso_pieza_terminada_kg=peso)
    db.add(m)
    db.commit()
    return m


def _consumo(db, tenant, material, order, line, kg, metodo):
    db.add(
        MaterialConsumo(
            tenant_id=tenant.id,
            order_id=order.id,
            order_line_id=line.id,
            material_id=material.id,
            consumed_quantity=D(str(kg)),
            unit="kg",
            calculation_method=metodo,
        )
    )


def _lineas_con_chatarra(db, tenant, modelo, pcts):
    """Una línea por % de chatarra: 100 kg de material por línea."""
    material = make_material(db, tenant, code=f"MAT-{modelo.code}")
    for i, pct in enumerate(pcts):
        order = make_order(db, tenant, numero=f"OP-{modelo.code}-{i}")
        line = make_order_line(db, order)
        line.modelo_id = modelo.id
        _consumo(db, tenant, material, order, line, 100 - pct, "density_formula")
        _consumo(db, tenant, material, order, line, pct, "coil_end_scrap")
    db.commit()


def test_sin_peso_ni_historia_el_modelo_esta_aprendiendo():
    d = desglose_chatarra(
        piezas=D("100"), piezas_kg=D("940"), chatarra_kg=D("60"), modelo=None, referencia=None
    )
    assert d["consumo_kg"] == D("1000")
    assert d["chatarra_kg"] == D("60")
    assert d["prevista_kg"] is None and d["de_mas_kg"] is None
    assert d["referencia"] is None


def test_con_peso_terminado_la_chatarra_de_proceso_es_exacta(db_session, tenant):
    # Tira cortada 9,4 kg; pieza terminada 9,0 kg → 0,4 kg de rebaba/punzonado por pieza
    modelo = _modelo(db_session, tenant, peso=D("9.0"))
    d = desglose_chatarra(
        piezas=D("100"), piezas_kg=D("940"), chatarra_kg=D("25"), modelo=modelo, referencia=None
    )
    assert d["consumo_kg"] == D("965")  # lo que salió de la bobina no cambia
    assert d["piezas_kg"] == D("900")
    assert d["prevista_kg"] == D("40")
    assert d["de_mas_kg"] == D("25")
    assert d["chatarra_kg"] == D("65")
    assert d["referencia"] == "peso_terminado"


def test_con_referencia_aprendida_separa_lo_de_mas():
    d = desglose_chatarra(
        piezas=D("100"), piezas_kg=D("920"), chatarra_kg=D("80"), modelo=None,
        referencia=D("0.05"),
    )
    assert d["prevista_kg"] == D("50")
    assert d["de_mas_kg"] == D("30")
    assert d["referencia"] == "aprendida"


def test_referencia_es_la_mediana_y_necesita_tres_lineas(db_session, tenant):
    modelo = _modelo(db_session, tenant, code="MOD-A")
    _lineas_con_chatarra(db_session, tenant, modelo, [4, 6])
    assert referencia_aprendida(db_session, tenant.id, modelo.id) is None

    otro = _modelo(db_session, tenant, code="MOD-B")
    _lineas_con_chatarra(db_session, tenant, otro, [4, 6, 20])
    assert referencia_aprendida(db_session, tenant.id, otro.id) == D("0.06")


def test_informe_de_turno_muestra_prevista_y_de_mas(db_session, tenant, user):
    modelo = _modelo(db_session, tenant, code="MOD-INF", peso=D("9.0"))
    order = make_order(db_session, tenant, numero="OP-CHAT")
    line = make_order_line(db_session, order)
    line.modelo_id = modelo.id
    ts = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)  # turno A
    for action, qty, meta in (
        ("produce", 100, {"consumedAmount": 940, "consumedMaterial": "kg"}),
        ("scrap", 25, {}),
    ):
        db_session.add(
            ProductionLog(
                tenant_id=tenant.id, order_id=order.id, line_id=line.id,
                operator_id=user.id, timestamp=ts, action=action,
                quantity=D(str(qty)), metadata_=meta,
            )
        )
    db_session.commit()

    fila = informe_turno(db_session, tenant.id, date(2026, 10, 26), "A")["por_operario"][0]
    assert fila["modelo"] == "MOD-INF"
    assert fila["consumo_kg"] == 965.0
    assert fila["chatarra_kg"] == 65.0
    assert fila["chatarra_prevista_kg"] == 40.0
    assert fila["chatarra_de_mas_kg"] == 25.0
    assert fila["referencia"] == "peso_terminado"


def test_supervisor_guarda_el_peso_de_la_pieza(db_session, tenant):
    from app.main import app
    from app.routers import quality as quality_router
    from tests.helpers import authed_client_for, make_user

    def _db():
        yield db_session

    sup = make_user(db_session, tenant, email="sup@test.local", role="supervisor")
    modelo = _modelo(db_session, tenant, code="MOD-API")
    app.dependency_overrides[quality_router.get_db] = _db
    try:
        client = authed_client_for(db_session, sup)
        r = client.patch(
            f"/api/v1/quality/models/{modelo.id}", json={"peso_pieza_terminada_kg": 9.25}
        )
        assert r.status_code == 200, r.text
        r = client.get("/api/v1/quality/models")
        assert any(m["peso_pieza_terminada_kg"] is not None for m in r.json())
        r = client.patch(
            f"/api/v1/quality/models/{modelo.id}", json={"peso_pieza_terminada_kg": -1}
        )
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()
    db_session.refresh(modelo)
    assert modelo.peso_pieza_terminada_kg == D("9.25")
