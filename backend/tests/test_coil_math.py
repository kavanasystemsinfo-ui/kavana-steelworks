"""Tests TDD del port de coilMath.js (spec 01, fórmula v2 radio→kg).

La fórmula fue verificada por Jorge en fábrica (legacy "Magic Wand"):
el operario mide los MILÍMETROS DE RADIO de la bobina con un metro y el
sistema convierte a kg. Densidad Calibrada Kavana = 7.7807 kg/dm³ (Decisión 92).

Valores de referencia calculados con la fórmula exacta del legacy:
- radio 500 mm, ancho 1000 mm → 12.319,67 kg
- radio 250 mm, ancho 1000 mm → 4.632,10 kg
- radio 250 mm, ancho 122 mm → 565,12 kg
"""

import pytest

from app.services.coil_math import peso_desde_radio_mm


def test_peso_bobina_completa_referencia():
    """Radio 500 mm y ancho 1000 mm: bobina de ~12,3 t (valor legacy)."""
    peso = peso_desde_radio_mm(radio_mm=500, width_mm=1000)
    assert peso == pytest.approx(12319.67, abs=0.02)


def test_peso_radio_mitad():
    """Radio 250 mm y ancho 1000 mm: ~4,6 t."""
    peso = peso_desde_radio_mm(radio_mm=250, width_mm=1000)
    assert peso == pytest.approx(4632.10, abs=0.02)


def test_peso_ancho_estrecho():
    """Radio 250 mm y ancho 122 mm: ~565 kg."""
    peso = peso_desde_radio_mm(radio_mm=250, width_mm=122)
    assert peso == pytest.approx(565.12, abs=0.02)


def test_radio_cero_peso_cero():
    """Radio 0: sin material, peso 0."""
    assert peso_desde_radio_mm(radio_mm=0, width_mm=122) == 0


def test_radio_mayor_mas_peso():
    """A más radio (más pared de bobina), más kg."""
    assert peso_desde_radio_mm(radio_mm=300, width_mm=122) > peso_desde_radio_mm(
        radio_mm=200, width_mm=122
    )


def test_densidad_calibrada_kavana_por_defecto():
    """La densidad por defecto es la calibrada Kavana 7.7807 kg/dm³ (Decisión 92)."""
    # Con densidad de acero macizo 7.85 pesaría más
    peso_kavana = peso_desde_radio_mm(radio_mm=250, width_mm=122)
    peso_acero = peso_desde_radio_mm(radio_mm=250, width_mm=122, densidad_kg_dm3=7.85)
    assert peso_kavana < peso_acero
    assert peso_kavana == pytest.approx(565.12, abs=0.02)


def test_sin_ancho_error_claro():
    """Sin ancho no se puede calcular: error explícito, nunca fallback silencioso."""
    with pytest.raises(ValueError, match="ancho"):
        peso_desde_radio_mm(radio_mm=250, width_mm=None)
