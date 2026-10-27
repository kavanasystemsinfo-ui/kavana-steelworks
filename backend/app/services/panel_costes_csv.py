"""CSV de la vista Costes del panel de mando (para Excel en español).

Solo formatea el contrato que devuelve ``panel_costes()``: no consulta la BD ni
recalcula cifras, igual que ``informe_csv`` en ``informe_turno``. Separador
``;``, coma decimal y BOM (lo añade el router), de modo que Excel lo abra
directo en una instalación española.

Se escribe en bloques con su cabecera —resumen, reparto, paradas, tendencia y
órdenes— porque la vista Costes no es una tabla única. Un bloque sin datos deja
su cabecera y ninguna fila: nunca se rellena con ceros inventados.
"""

from __future__ import annotations

import csv
import io
from typing import Any


def _celda(valor) -> str:
    """Texto de celda: coma decimal en flotantes, vacío donde no hay dato."""
    if valor is None:
        return ""
    if isinstance(valor, bool):  # antes que int: bool es int en Python
        return "sí" if valor else "no"
    if isinstance(valor, float):
        return f"{valor:.2f}".replace(".", ",")
    return str(valor)


def _fila(escritor: Any, celdas) -> None:
    escritor.writerow([_celda(celda) for celda in celdas])


def panel_costes_csv(datos: dict) -> str:
    """CSV del panel de costes a partir del dict ya calculado."""
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";")
    coste_kg = datos["coste_kg"]
    desviacion = datos["desviacion"]
    chatarra = datos["chatarra"]
    paradas = datos["coste_paradas"]

    escritor.writerow(
        [
            "Panel de costes",
            datos["periodo"],
            datos["desde"][:10],
            datos["hasta"][:10],
        ]
    )
    escritor.writerow([])

    escritor.writerow(["Resumen", "Valor"])
    for etiqueta, valor in (
        ("€/kg", coste_kg["valor"]),
        ("Material €/kg", coste_kg["material"]),
        ("Transformación €/kg", coste_kg["transformacion"]),
        ("€/kg periodo anterior", coste_kg["periodo_anterior"]),
        ("Objetivo €/kg", coste_kg["objetivo"]),
        ("Coste total (€)", datos["coste_total"]),
        ("kg producidos", datos["kg_total"]),
        ("Órdenes completadas", datos["ordenes_completadas"]),
        ("Líneas en metros excluidas del €/kg", datos["lineas_metros_excluidas"]),
        ("Desviación material (€)", desviacion["euros"]),
        ("Desviación material (%)", desviacion["pct"]),
        ("Órdenes con estimado", desviacion["ordenes_con_estimado"]),
        ("Chatarra (€)", chatarra["euros"]),
        ("Chatarra sobre material (%)", chatarra["pct_material"]),
    ):
        _fila(escritor, [etiqueta, valor])

    escritor.writerow([])
    escritor.writerow(["Reparto del coste", "Euros", "%"])
    for bloque in datos["reparto"]:
        _fila(escritor, [bloque["etiqueta"], bloque["euros"], bloque["pct"]])

    escritor.writerow([])
    escritor.writerow(["Coste por familia"])
    escritor.writerow(
        ["Familia", "kg", "Material €/kg", "Transformación €/kg", "Merma %", "Órdenes"]
    )
    for familia in datos["por_familia"]:
        _fila(
            escritor,
            [
                familia["etiqueta"],
                familia["kg"],
                familia["material"],
                familia["transformacion"],
                familia["merma_pct"],
                familia["ordenes"],
            ],
        )

    escritor.writerow([])
    escritor.writerow(["Coste de paradas", "Valor"])
    _fila(escritor, ["Total (€)", paradas["total"]])
    _fila(escritor, ["Horas paradas", paradas["horas"]])
    escritor.writerow([])
    escritor.writerow(["Paradas por tipo", "Euros"])
    for tipo in paradas["por_tipo"]:
        _fila(escritor, [tipo["etiqueta"], tipo["euros"]])

    escritor.writerow([])
    escritor.writerow(["Tendencia €/kg", "Valor"])
    escritor.writerow(["Semana", "€/kg"])
    for punto in datos["tendencia"]:
        _fila(escritor, [punto["semana"], punto["valor"]])

    escritor.writerow([])
    escritor.writerow(["Órdenes con desviación", ""])
    escritor.writerow(
        [
            "Orden",
            "Producto",
            "kg",
            "Estimado (€)",
            "Real (€)",
            "Desviación (€)",
            "Desviación (%)",
            "Causa",
        ]
    )
    for orden in datos["ordenes"]:
        _fila(
            escritor,
            [
                orden["numero"],
                orden["producto"],
                orden["kg"],
                orden["estimado"],
                orden["real"],
                orden["desv_euros"],
                orden["desv_pct"],
                orden["causa"],
            ],
        )

    return salida.getvalue()
