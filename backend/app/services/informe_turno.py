"""Informe de turno exportable (adopción de "Reports" de gerencia del legacy).

Sale de los eventos inmutables de trazabilidad (ProductionLog) y de las
incidencias abiertas en la ventana del turno, así que es un informe REAL del
turno pedido (fecha + A/B/C en horario de planta), no un acumulado.

Por puesto: piezas, material consumido, merma (kg y €), autocontroles
(total y no conformes) e incidencias con su tiempo de parada. Por operario,
orden y material: el balance de kilos del turno (consumido en piezas y
chatarra medida al cerrar el turno o la bobina). Sin datos en
la ventana, el informe sale vacío: nunca se rellena.
"""

import csv
import io
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Incidencia, Material, Order, OrderLine, ProductionLog, User
from app.services.shifts import TZ_PLANTA

TURNOS = {"A": (6, 8), "B": (14, 8), "C": (22, 8)}  # hora de inicio, duración (h)


def ventana_turno(fecha: date, turno: str) -> tuple[datetime, datetime]:
    """Inicio y fin (aware, horario de planta) del turno A/B/C de esa fecha.

    El turno C empieza a las 22:00 de la fecha y termina a las 06:00 del día
    siguiente.
    """
    if turno not in TURNOS:
        raise ValueError("turno debe ser A, B o C")
    hora, duracion = TURNOS[turno]
    inicio = datetime.combine(fecha, time(hour=hora), tzinfo=TZ_PLANTA)
    return inicio, inicio + timedelta(hours=duracion)


def _fila_vacia(puesto: str) -> dict:
    return {
        "puesto": puesto,
        "piezas": Decimal("0"),
        "consumo_kg": Decimal("0"),
        "consumo_m": Decimal("0"),
        "merma_kg": Decimal("0"),
        "merma_coste": Decimal("0"),
        "autocontroles": 0,
        "autocontroles_nok": 0,
        "incidencias": 0,
        "parada_min": Decimal("0"),
        "ordenes": set(),
    }


def informe_turno(db: Session, tenant_id: uuid.UUID, fecha: date, turno: str) -> dict:
    inicio, fin = ventana_turno(fecha, turno)
    desde, hasta = inicio.astimezone(UTC), fin.astimezone(UTC)
    filas: dict[str, dict] = {}

    balance: dict[tuple, dict] = {}
    eventos = db.execute(
        select(ProductionLog, OrderLine.workstation_id, OrderLine.material_id)
        .join(OrderLine, OrderLine.id == ProductionLog.line_id)
        .where(
            ProductionLog.tenant_id == tenant_id,
            ProductionLog.timestamp >= desde,
            ProductionLog.timestamp < hasta,
        )
    ).all()
    for log, puesto, material_id in eventos:
        meta = log.metadata_ or {}
        puesto = puesto or meta.get("workstationId") or "sin puesto"
        fila = filas.setdefault(puesto, _fila_vacia(puesto))
        if log.action in ("produce", "scrap"):
            clave = (log.operator_id, log.order_id, material_id)
            b = balance.setdefault(
                clave,
                {"piezas": Decimal("0"), "consumo_kg": Decimal("0"), "chatarra_kg": Decimal("0")},
            )
            if log.action == "produce":
                b["piezas"] += Decimal(str(log.quantity or 0))
                if meta.get("consumedMaterial") == "kg":
                    b["consumo_kg"] += Decimal(str(meta.get("consumedAmount") or 0))
            else:
                b["chatarra_kg"] += Decimal(str(log.quantity or 0))
        if log.action == "produce":
            fila["piezas"] += Decimal(str(log.quantity or 0))
            fila["ordenes"].add(str(log.order_id))
            cantidad = Decimal(str(meta.get("consumedAmount") or 0))
            if meta.get("consumedMaterial") == "kg":
                fila["consumo_kg"] += cantidad
            elif meta.get("consumedMaterial") == "m":
                fila["consumo_m"] += cantidad
        elif log.action == "scrap":
            fila["merma_kg"] += Decimal(str(log.quantity or 0))
            fila["merma_coste"] += Decimal(str(meta.get("merma_cost") or 0))
        elif log.action == "quality_check":
            fila["autocontroles"] += 1
            if str(meta.get("status", "")).lower() not in ("ok", "conforme", "passed"):
                fila["autocontroles_nok"] += 1

    for inc in db.scalars(
        select(Incidencia).where(
            Incidencia.tenant_id == tenant_id,
            Incidencia.created_at >= desde,
            Incidencia.created_at < hasta,
        )
    ):
        fila = filas.setdefault(inc.puesto or "sin puesto", _fila_vacia(inc.puesto or "sin puesto"))
        fila["incidencias"] += 1
        fila["parada_min"] += inc.tiempo_parada_min or Decimal("0")

    # Paradas con un toque del operario (avería, ajustes, limpieza...)
    from app.services.paradas import paradas_en

    for x in paradas_en(db, tenant_id, desde, hasta):
        if x["tipo"].startswith("parada_"):
            fila = filas.setdefault(x["puesto"], _fila_vacia(x["puesto"]))
            fila["parada_min"] += Decimal(str(round(x["minutos"], 1)))

    puestos = []
    for puesto in sorted(filas):
        f = filas[puesto]
        puestos.append(
            {
                "puesto": puesto,
                "ordenes": len(f["ordenes"]),
                "piezas": float(f["piezas"]),
                "consumo_kg": round(float(f["consumo_kg"]), 2),
                "consumo_m": round(float(f["consumo_m"]), 2),
                "merma_kg": round(float(f["merma_kg"]), 2),
                "merma_coste": round(float(f["merma_coste"]), 2),
                "autocontroles": f["autocontroles"],
                "autocontroles_nok": f["autocontroles_nok"],
                "incidencias": f["incidencias"],
                "parada_min": round(float(f["parada_min"]), 1),
            }
        )

    campos_suma = (
        "piezas", "consumo_kg", "consumo_m", "merma_kg", "merma_coste",
        "autocontroles", "autocontroles_nok", "incidencias", "parada_min",
    )
    totales = {c: round(sum(p[c] for p in puestos), 2) for c in campos_suma}

    return {
        "fecha": fecha.isoformat(),
        "turno": turno,
        "inicio": inicio.isoformat(),
        "fin": fin.isoformat(),
        "puestos": puestos,
        "totales": totales,
        "por_operario": _por_operario(db, balance),
    }


def _por_operario(db: Session, balance: dict[tuple, dict]) -> list[dict]:
    """Balance de kilos por operario, orden y material, con su % de chatarra."""
    filas = []
    for (operario_id, orden_id, material_id), b in balance.items():
        operario = db.get(User, operario_id) if operario_id else None
        orden = db.get(Order, orden_id) if orden_id else None
        material = db.get(Material, material_id) if material_id else None
        total = b["consumo_kg"] + b["chatarra_kg"]
        filas.append(
            {
                "operario": operario.name if operario else "—",
                "orden": orden.numero if orden else "—",
                "material": material.code if material else "—",
                "piezas": float(b["piezas"]),
                "consumo_kg": round(float(total), 2),
                "piezas_kg": round(float(b["consumo_kg"]), 2),
                "chatarra_kg": round(float(b["chatarra_kg"]), 2),
                "chatarra_pct": round(float(b["chatarra_kg"] / total * 100), 1) if total else None,
            }
        )
    return sorted(filas, key=lambda f: (f["operario"], f["orden"], f["material"]))


COLUMNAS_CSV = [
    ("puesto", "Puesto"),
    ("ordenes", "Órdenes"),
    ("piezas", "Piezas"),
    ("consumo_kg", "Consumo (kg)"),
    ("consumo_m", "Consumo (m)"),
    ("merma_kg", "Merma (kg)"),
    ("merma_coste", "Merma (€)"),
    ("autocontroles", "Autocontroles"),
    ("autocontroles_nok", "Autocontroles NOK"),
    ("incidencias", "Incidencias"),
    ("parada_min", "Parada (min)"),
]


def informe_csv(informe: dict) -> str:
    """CSV con separador ';' y coma decimal (Excel en español lo abre directo)."""

    def celda(valor):
        if isinstance(valor, float):
            return f"{valor:.2f}".replace(".", ",")
        return valor

    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow([f"Informe de turno {informe['turno']}", informe["fecha"]])
    escritor.writerow([titulo for _, titulo in COLUMNAS_CSV])
    for p in informe["puestos"]:
        escritor.writerow([celda(p[c]) for c, _ in COLUMNAS_CSV])
    totales = informe["totales"]
    escritor.writerow(
        ["TOTAL", ""] + [celda(totales[c]) for c, _ in COLUMNAS_CSV[2:]]
    )
    return salida.getvalue()
