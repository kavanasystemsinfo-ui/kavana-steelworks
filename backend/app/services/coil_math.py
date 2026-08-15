"""Cálculo geométrico de bobinas: port de coilMath.js del legacy (fórmula v2).

El operario mide los MILÍMETROS DE RADIO de la bobina con un metro y el
sistema convierte a kg restantes. Es la fórmula verificada por Jorge en
fábrica (legacy "Magic Wand", feature de CoilCalculator).

Densidad Calibrada Kavana = 7.7807 kg/dm³ (Decisión 92): compensa el factor
de bobinado/recubrimiento y coincide con las básculas de planta.
"""

import math
from decimal import ROUND_HALF_UP, Decimal

# Constantes canónicas (spec 01 / Decisión 92)
DIAMETRO_INTERIOR_MM_DEFAULT = 508  # mandril estándar
DENSIDAD_CALIBRADA_KAVANA_KG_DM3 = Decimal("7.7807")


def peso_desde_radio_mm(
    *,
    radio_mm: Decimal | float | int,
    width_mm: Decimal | float | int | None,
    inner_diameter_mm: Decimal | float | int = DIAMETRO_INTERIOR_MM_DEFAULT,
    densidad_kg_dm3: Decimal | float = DENSIDAD_CALIBRADA_KAVANA_KG_DM3,
) -> float:
    """Peso teórico restante de una bobina según su radio medido (kg).

    Fórmula del legacy (calculateWeightFromThickness):
    P_m     = radio_mm / 1000
    R_int_m = (innerDiameterMm / 1000) / 2
    R_ext_m = R_int_m + P_m
    Volumen_m3 = π * (R_ext² − R_int²) * (width_mm / 1000)
    Peso_kg    = Volumen_m3 * (densidad * 1000)
    """
    if width_mm is None or width_mm == 0:
        raise ValueError(
            "La bobina no tiene ancho registrado; no se puede calcular el peso por radio"
        )

    radio = Decimal(str(radio_mm))
    ancho = Decimal(str(width_mm))
    diametro_interior = Decimal(str(inner_diameter_mm))
    densidad = Decimal(str(densidad_kg_dm3))

    if radio <= 0:
        return 0.0

    P_m = radio / 1000
    R_int_m = (diametro_interior / 1000) / 2
    R_ext_m = R_int_m + P_m

    ancho_m = ancho / 1000
    densidad_kgm3 = densidad * 1000

    volumen_m3 = math.pi * (float(R_ext_m) ** 2 - float(R_int_m) ** 2) * float(ancho_m)
    peso_kg = Decimal(str(volumen_m3)) * Decimal(str(densidad_kgm3))
    return float(peso_kg.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
