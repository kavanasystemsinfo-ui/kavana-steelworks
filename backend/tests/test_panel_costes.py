"""Tests de la vista Costes del panel de mando (services/panel_costes.py).

Contrato cubierto:
- €/kg solo con líneas medidas en kg (las de metros se excluyen y se cuentan).
- Reparto material / mano de obra / chatarra: los euros cuadran con
  ``coste_total`` y los porcentajes suman 100 % (incluido el redondeo).
- Coste de paradas: minutos → horas × €/h del puesto de la incidencia.
- Las cinco reglas de causa, en su orden de prioridad.
- €/kg del periodo anterior, objetivo desde la configuración de empresa,
  tendencia de 8 semanas y periodo vacío sin cifras inventadas.

Referencia temporal fija (``AHORA``): martes 20-oct-2026 12:00 UTC = 07:00 en
horario de planta (UTC-5), semana del 19 al 25 de octubre y mes de octubre.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.models import Incidencia, Product, Workstation
from app.services.panel_costes import panel_costes
from tests.helpers import make_material, make_order, make_order_line

AHORA = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def _puesto(db, tenant, code="LINEA-1", coste_hora="30.00"):
    puesto = Workstation(
        tenant_id=tenant.id, code=code, name=f"Puesto {code}", hourly_cost=Decimal(coste_hora)
    )
    db.add(puesto)
    db.commit()
    return puesto


def _orden(
    db,
    tenant,
    numero,
    *,
    kg=100.0,
    coste_material=200.0,
    coste_linea=None,
    scrap=0.0,
    puesto="LINEA-1",
    actualizado=AHORA,
    producto=None,
    metros=None,
    coste_estandar=2.0,
):
    """Orden completada con una línea en kg (y opcionalmente otra en metros).

    El estimado sale de ``target_material_qty × coste_estandar``; con los
    valores por defecto son 100 kg × 2 €/kg = 200 €.
    """
    material = make_material(db, tenant, code=f"MAT-{numero}", cost=coste_estandar)
    order = make_order(db, tenant, numero=numero)
    order.estado = "completed"

    linea = make_order_line(db, order, workstation=puesto, total_quantity=10.0, material=material)
    linea.target_material_unit = "kg"
    linea.target_material_qty = Decimal(str(kg))
    linea.real_material_qty = Decimal(str(kg))
    linea.real_material_cost = Decimal(str(coste_material))
    linea.scrap_material_qty = Decimal(str(scrap))
    linea.real_cost = Decimal(str(coste_material if coste_linea is None else coste_linea))

    if producto:
        # El producto cuelga de la primera línea (es lo que muestra el panel).
        p = Product(tenant_id=tenant.id, code=f"P-{numero}", name=producto)
        db.add(p)
        db.flush()
        linea.product_id = p.id

    if metros is not None:
        linea_m = make_order_line(
            db, order, workstation=puesto, total_quantity=1.0, linea_numero=2, material=material
        )
        linea_m.target_material_unit = "m"
        linea_m.target_material_qty = Decimal("10")
        linea_m.real_material_qty = Decimal(str(metros))
        linea_m.real_material_cost = Decimal(str(metros))
        linea_m.real_cost = Decimal(str(metros))

    order.updated_at = actualizado
    db.commit()
    return order


def _incidencia(db, tenant, user, *, order=None, puesto="LINEA-1", tipo="maquina", minutos=0):
    incidencia = Incidencia(
        tenant_id=tenant.id,
        order_id=order.id if order else None,
        puesto=puesto,
        operario_id=user.id,
        descripcion="Incidencia de test",
        tipo=tipo,
        estado="resuelta",
        tiempo_parada_min=Decimal(str(minutos)),
    )
    incidencia.created_at = AHORA
    db.add(incidencia)
    db.commit()
    return incidencia


# --------------------------------------------------------------------------- #
# €/kg y totales
# --------------------------------------------------------------------------- #
def test_coste_kg_excluye_lineas_en_metros(db_session, tenant):
    """100 kg + 100 m: el ratio solo usa kg, pero el gasto total incluye ambos."""
    _orden(db_session, tenant, "OP-KG", coste_material=200, coste_linea=300, scrap=5, metros=100)

    datos = panel_costes(db_session, tenant.id, "mes", ahora=AHORA)

    assert datos["kg_total"] == 100.0  # los 100 m no suman kg
    assert datos["lineas_metros_excluidas"] == 1
    assert datos["coste_total"] == 400.0  # 200 material kg + 100 m + 100 mano de obra
    # (200 material − 10 chatarra) + 100 mano de obra + 10 chatarra = 300 € / 100 kg
    assert datos["coste_kg"]["valor"] == 3.0
    assert datos["ordenes_completadas"] == 1


def test_desglose_material_y_transformacion_cuadra_con_el_coste_kg(db_session, tenant):
    """El €/kg se parte en material y transformación; las dos cifras suman el total."""
    _orden(db_session, tenant, "OP-DESGLOSE", kg=100, coste_material=200, coste_linea=300)

    coste = panel_costes(db_session, tenant.id, "mes", ahora=AHORA)["coste_kg"]

    assert coste["material"] == 2.0  # 200 € de material / 100 kg
    assert coste["transformacion"] == 1.0  # (300 − 200) de mano de obra / 100 kg
    assert coste["material"] + coste["transformacion"] == pytest.approx(coste["valor"])


def test_desglose_deja_la_merma_dentro_del_material(db_session, tenant):
    """La chatarra ya está pagada en el material cargado: no se separa del bloque."""
    _orden(
        db_session,
        tenant,
        "OP-DESGLOSE-MERMA",
        kg=100,
        coste_material=200,
        coste_linea=300,
        scrap=10,
    )

    coste = panel_costes(db_session, tenant.id, "mes", ahora=AHORA)["coste_kg"]

    assert coste["material"] == 2.0  # 200 € (los 20 € de merma van dentro del material)
    assert coste["transformacion"] == 1.0
    assert coste["material"] + coste["transformacion"] == pytest.approx(coste["valor"])


def test_reparto_cuadra_con_coste_total_y_suma_100(db_session, tenant):
    """50 kg de chatarra: el material va neto para no contar la merma dos veces."""
    _orden(db_session, tenant, "OP-REPARTO", coste_material=200, coste_linea=300, scrap=50)

    datos = panel_costes(db_session, tenant.id, "mes", ahora=AHORA)
    reparto = datos["reparto"]

    assert [bloque["clave"] for bloque in reparto] == ["material", "mano_obra", "chatarra"]
    assert sum(bloque["euros"] for bloque in reparto) == pytest.approx(datos["coste_total"])
    assert datos["coste_total"] == 300.0  # 200 material + 100 mano de obra
    assert reparto[0]["euros"] == 100.0  # 200 − 100 de chatarra
    assert reparto[2]["euros"] == 100.0
    # 33,333… × 3: el residuo del redondeo va al bloque mayor y suma 100 exacto.
    assert sum(bloque["pct"] for bloque in reparto) == pytest.approx(100.0)
    assert [bloque["pct"] for bloque in reparto] == [33.34, 33.33, 33.33]


def test_chatarra_pct_material(db_session, tenant):
    _orden(db_session, tenant, "OP-MERMA", coste_material=200, scrap=10)

    datos = panel_costes(db_session, tenant.id, "mes", ahora=AHORA)

    assert datos["chatarra"]["euros"] == 20.0  # 10 kg × 2 €/kg
    assert datos["chatarra"]["pct_material"] == 10.0


# --------------------------------------------------------------------------- #
# Paradas
# --------------------------------------------------------------------------- #
def test_coste_de_paradas_por_horas_del_puesto(db_session, tenant, user):
    _puesto(db_session, tenant, "PLEG-1", "30.00")
    _incidencia(db_session, tenant, user, puesto="PLEG-1", tipo="maquina", minutos=90)

    datos = panel_costes(db_session, tenant.id, "mes", ahora=AHORA)

    assert datos["coste_paradas"] == {
        "total": 45.0,  # 1,5 h × 30 €/h
        "por_tipo": [{"tipo": "maquina", "etiqueta": "Máquina", "euros": 45.0}],
        "horas": 1.5,
    }


def test_parada_fuera_del_periodo_no_cuenta(db_session, tenant, user):
    _puesto(db_session, tenant, "PLEG-1", "30.00")
    incidencia = _incidencia(db_session, tenant, user, puesto="PLEG-1", minutos=90)
    incidencia.created_at = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    db_session.commit()

    datos = panel_costes(db_session, tenant.id, "mes", ahora=AHORA)

    assert datos["coste_paradas"]["total"] == 0.0
    assert datos["coste_paradas"]["por_tipo"] == []


# --------------------------------------------------------------------------- #
# Reglas de causa
# --------------------------------------------------------------------------- #
def test_las_cinco_reglas_de_causa(db_session, tenant, user):
    _orden(db_session, tenant, "OP-CHATARRA", puesto="PUNZ-1", scrap=10)
    con_parada = _orden(db_session, tenant, "OP-PARADAS", puesto="ENS-1")
    _incidencia(db_session, tenant, user, order=con_parada, puesto="PLEG-1", minutos=90)
    _orden(db_session, tenant, "OP-MEJOR", coste_material=180)
    _orden(db_session, tenant, "OP-NORMAL", coste_material=202)
    _orden(db_session, tenant, "OP-RARO", coste_material=230, producto="Estantería K-100")

    datos = panel_costes(db_session, tenant.id, "mes", ahora=AHORA)
    causas = {orden["numero"]: orden["causa"] for orden in datos["ordenes"]}

    assert causas["OP-CHATARRA"] == "Chatarra en PUNZ-1"  # merma > 5 % del material
    assert causas["OP-PARADAS"] == "Paradas en PLEG-1"  # 90 min > 60
    assert causas["OP-MEJOR"] == "Mejor aprovechamiento"  # −10 %
    assert causas["OP-NORMAL"] == "Dentro de lo normal"  # +1 %
    assert causas["OP-RARO"] == "Sin causa clara"  # +15 %
    assert {o["numero"]: o["producto"] for o in datos["ordenes"]}["OP-RARO"] == (
        "Estantería K-100"
    )


def test_prioridad_chatarra_sobre_paradas_y_desviacion(db_session, tenant, user):
    """Merma > 5 %, parada > 60 min y desviación negativa: gana la chatarra."""
    con_todo = _orden(db_session, tenant, "OP-TODO", puesto="PUNZ-1", coste_material=180, scrap=10)
    _incidencia(db_session, tenant, user, order=con_todo, puesto="PLEG-1", minutos=120)

    datos = panel_costes(db_session, tenant.id, "mes", ahora=AHORA)

    assert datos["ordenes"][0]["causa"] == "Chatarra en PUNZ-1"


def test_prioridad_paradas_sobre_desviacion(db_session, tenant, user):
    """Parada > 60 min con mejor aprovechamiento: la parada manda."""
    con_parada = _orden(db_session, tenant, "OP-PARADA", coste_material=180)
    _incidencia(db_session, tenant, user, order=con_parada, puesto="CORTE-1", minutos=120)

    datos = panel_costes(db_session, tenant.id, "mes", ahora=AHORA)

    assert datos["ordenes"][0]["causa"] == "Paradas en CORTE-1"


def test_parada_corta_no_es_causa(db_session, tenant, user):
    con_parada = _orden(db_session, tenant, "OP-CORTA", coste_material=180)
    _incidencia(db_session, tenant, user, order=con_parada, puesto="CORTE-1", minutos=60)

    datos = panel_costes(db_session, tenant.id, "mes", ahora=AHORA)

    assert datos["ordenes"][0]["causa"] == "Mejor aprovechamiento"


# --------------------------------------------------------------------------- #
# Periodos, objetivo y tendencia
# --------------------------------------------------------------------------- #
def test_coste_kg_del_periodo_anterior(db_session, tenant):
    _orden(
        db_session, tenant, "OP-OCT", coste_material=200, coste_linea=300,
        actualizado=datetime(2026, 10, 10, 12, 0, tzinfo=UTC),
    )
    _orden(
        db_session, tenant, "OP-SEP", kg=50, coste_material=100,
        actualizado=datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
    )

    datos = panel_costes(db_session, tenant.id, "mes", ahora=AHORA)

    assert datos["coste_kg"]["valor"] == 3.0  # octubre: 300 € / 100 kg
    assert datos["coste_kg"]["periodo_anterior"] == 2.0  # septiembre: 100 € / 50 kg


def test_trimestre_agrupa_los_tres_meses(db_session, tenant):
    """Q4 (oct-dic): la referencia es el 15-dic, último mes del trimestre."""
    for numero, mes in (("OP-T1", 10), ("OP-T2", 11), ("OP-T3", 12)):
        _orden(
            db_session, tenant, numero, coste_material=100, kg=50,
            actualizado=datetime(2026, mes, 10, 12, 0, tzinfo=UTC),
        )

    datos = panel_costes(
        db_session, tenant.id, "trimestre", ahora=datetime(2026, 12, 15, 12, 0, tzinfo=UTC)
    )

    assert datos["ordenes_completadas"] == 3
    assert datos["kg_total"] == 150.0
    assert datos["coste_kg"]["valor"] == 2.0


def test_objetivo_desde_la_configuracion_de_empresa(db_session, tenant):
    sin_objetivo = panel_costes(db_session, tenant.id, "mes", ahora=AHORA)
    assert sin_objetivo["coste_kg"]["objetivo"] is None

    tenant.finances = {"objetivo_coste_kg": "2,45"}  # coma decimal en configuración
    db_session.commit()
    assert panel_costes(db_session, tenant.id, "mes", ahora=AHORA)["coste_kg"]["objetivo"] == 2.45

    tenant.finances = {"coste_kg_objetivo": 3}
    db_session.commit()
    assert panel_costes(db_session, tenant.id, "mes", ahora=AHORA)["coste_kg"]["objetivo"] == 3.0


def test_tendencia_de_ocho_semanas(db_session, tenant):
    _orden(db_session, tenant, "OP-SEM-ACTUAL", coste_material=200, coste_linea=300)
    _orden(
        db_session, tenant, "OP-HACE-3-SEMANAS", coste_material=200,
        actualizado=datetime(2026, 9, 29, 12, 0, tzinfo=UTC),
    )

    datos = panel_costes(db_session, tenant.id, "mes", ahora=AHORA)
    semanas = {punto["semana"]: punto["valor"] for punto in datos["tendencia"]}

    assert len(datos["tendencia"]) == 8
    assert list(semanas)[-1] == "2026-10-19"  # la semana de AHORA, la última
    assert semanas["2026-10-19"] == 3.0
    assert semanas["2026-09-28"] == 2.0  # 200 € / 100 kg
    assert semanas["2026-10-05"] == 0.0  # sin kg: 0, no se inventa


def test_orden_sin_estimado_no_entra_en_desviacion_ni_en_la_lista(db_session, tenant):
    _orden(db_session, tenant, "OP-SIN-ESTIMADO", coste_estandar=0)

    datos = panel_costes(db_session, tenant.id, "mes", ahora=AHORA)

    assert datos["desviacion"] == {"pct": 0.0, "euros": 0.0, "ordenes_con_estimado": 0}
    assert datos["ordenes"] == []
    assert datos["ordenes_completadas"] == 1  # el gasto sí cuenta en los totales


def test_periodo_vacio_devuelve_ceros(db_session, tenant):
    datos = panel_costes(db_session, tenant.id, "semana", ahora=AHORA)

    assert datos["coste_kg"] == {
        "valor": 0.0,
        "periodo_anterior": 0.0,
        "objetivo": None,
        "material": 0.0,
        "transformacion": 0.0,
    }
    assert datos["coste_total"] == 0.0
    assert datos["kg_total"] == 0.0
    assert [bloque["pct"] for bloque in datos["reparto"]] == [0.0, 0.0, 0.0]
    assert datos["chatarra"] == {"euros": 0.0, "pct_material": 0.0}
    assert datos["coste_paradas"] == {"total": 0.0, "por_tipo": [], "horas": 0.0}
    assert datos["ordenes"] == []


def test_periodo_invalido(db_session, tenant):
    with pytest.raises(ValueError, match="periodo"):
        panel_costes(db_session, tenant.id, "decada", ahora=AHORA)
