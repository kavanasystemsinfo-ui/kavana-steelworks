"""Chatarra prevista y chatarra de más por modelo (Jorge, 28-10).

El balance de masas ya da la chatarra total sin configurar nada: kilos que
salieron de la bobina menos lo que pesan las piezas buenas. Aquí solo se
separa lo que se genera sí o sí (rebaba entre piezas, punzonados) de lo que
se podía evitar, sin calcular la geometría de agujeros ni ranuras:

- Si el modelo tiene el peso de la pieza terminada (del ERP o de pesar una
  pieza en báscula), la chatarra de proceso es exacta: piezas × (peso de la
  tira cortada − peso de la pieza terminada). Todo lo demás es de más.
- Si no lo tiene, el sistema aprende la chatarra normal del modelo: la
  mediana del % de chatarra de sus líneas con bobina medida. Hacen falta al
  menos MIN_MUESTRAS líneas; mientras tanto el modelo está «aprendiendo».
"""

import statistics
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MaterialConsumo, OrderLine
from app.models.quality import ManufacturingModel

MIN_MUESTRAS = 3


def referencia_aprendida(db: Session, tenant_id: uuid.UUID, modelo_id) -> Decimal | None:
    """Fracción de chatarra normal del modelo (mediana por línea), o None."""
    if modelo_id is None:
        return None
    filas = db.execute(
        select(
            MaterialConsumo.order_line_id,
            MaterialConsumo.calculation_method,
            func.sum(MaterialConsumo.consumed_quantity),
        )
        .join(OrderLine, OrderLine.id == MaterialConsumo.order_line_id)
        .where(
            MaterialConsumo.tenant_id == tenant_id,
            OrderLine.modelo_id == modelo_id,
            MaterialConsumo.unit == "kg",
        )
        .group_by(MaterialConsumo.order_line_id, MaterialConsumo.calculation_method)
    ).all()
    por_linea: dict = {}
    for linea_id, metodo, kg in filas:
        b = por_linea.setdefault(linea_id, {"piezas": Decimal("0"), "chatarra": Decimal("0")})
        if metodo == "coil_end_scrap":
            b["chatarra"] += Decimal(str(kg or 0))
        elif metodo != "none":
            b["piezas"] += Decimal(str(kg or 0))
    muestras = [
        b["chatarra"] / (b["piezas"] + b["chatarra"])
        for b in por_linea.values()
        if b["chatarra"] > 0 and b["piezas"] > 0
    ]
    if len(muestras) < MIN_MUESTRAS:
        return None
    return Decimal(str(statistics.median(muestras)))


def desglose_chatarra(
    *,
    piezas: Decimal,
    piezas_kg: Decimal,
    chatarra_kg: Decimal,
    modelo: ManufacturingModel | None,
    referencia: Decimal | None,
) -> dict:
    """Reparte la chatarra del balance en prevista y de más.

    piezas_kg es lo descontado por las piezas (peso de la tira cortada) y
    chatarra_kg la medida por radio. El consumo total de bobina no cambia.
    """
    consumo = piezas_kg + chatarra_kg
    peso_terminada = modelo.peso_pieza_terminada_kg if modelo else None
    kg_tira = piezas_kg / piezas if piezas > 0 else Decimal("0")

    if peso_terminada and kg_tira > peso_terminada:
        proceso = piezas * (kg_tira - peso_terminada)
        total = chatarra_kg + proceso
        return {
            "consumo_kg": consumo,
            "piezas_kg": piezas * peso_terminada,
            "chatarra_kg": total,
            "prevista_kg": proceso,
            "de_mas_kg": chatarra_kg,
            "referencia": "peso_terminado",
        }
    if referencia is not None and consumo > 0:
        prevista = referencia * consumo
        return {
            "consumo_kg": consumo,
            "piezas_kg": piezas_kg,
            "chatarra_kg": chatarra_kg,
            "prevista_kg": prevista,
            "de_mas_kg": max(Decimal("0"), chatarra_kg - prevista),
            "referencia": "aprendida",
        }
    return {
        "consumo_kg": consumo,
        "piezas_kg": piezas_kg,
        "chatarra_kg": chatarra_kg,
        "prevista_kg": None,
        "de_mas_kg": None,
        "referencia": None,
    }
