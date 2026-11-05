"""Ficha de un puesto: qué ha pasado en él y quién lo ha hecho.

Para el supervisor que ve un puesto flojo en la vista Planta y quiere saber
por qué: estado ahora, piezas contra plan, eficiencia, paradas por causa,
chatarra y el desglose por SESIONES del operario.

Una sesión son los registros consecutivos (producción, chatarra, arranques,
cierres...) del mismo operario en la misma línea de orden del puesto. Se abre
una sesión nueva si cambia el operario, si cambia la línea o si pasan más de
`HUECO_SESION` entre dos registros (un operario que vuelve al día siguiente
no tiene una sola sesión de 20 horas).

Nada de euros: kilos y merma sí. Las fechas se comparan siempre en UTC.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, OrderLine, ProductionLog, Workstation
from app.services.panel_planta import _medir, ventana_periodo
from app.services.panel_turno import _utc
from app.services.paradas import paradas_en
from app.services.puestos import estado_puestos

HUECO_SESION = timedelta(hours=4)

ACCIONES = {
    "start": "Empieza la orden",
    "pause": "Pausa",
    "resume": "Reanuda",
    "finish": "Termina la bobina",
    "produce": "Produce",
    "scrap": "Chatarra",
    "setup_start": "Empieza el ajuste",
    "setup_finish": "Termina el ajuste",
    "close_shift": "Cierra el turno",
    "stopped": "Parada",
    "quality_check": "Control de calidad",
}


def _evento(log: ProductionLog) -> dict:
    meta = log.metadata_ or {}
    consumo = meta.get("consumedAmount") if meta.get("consumedMaterial") == "kg" else None
    return {
        "hora": _utc(log.timestamp).isoformat(),
        "accion": log.action,
        "texto": ACCIONES.get(log.action, log.action),
        "cantidad": float(log.quantity or 0),
        "bobina": meta.get("activeCoilCode"),
        "kg_material": round(float(consumo), 1) if consumo else None,
        "nota": meta.get("observaciones"),
    }


def sesiones_de_puesto(db: Session, tenant_id: uuid.UUID, puesto: str, desde, hasta) -> list[dict]:
    """Sesiones del puesto en la ventana, la más reciente primero."""
    filas = db.execute(
        select(ProductionLog, Order.numero, OrderLine.linea_numero)
        .join(OrderLine, OrderLine.id == ProductionLog.line_id)
        .join(Order, Order.id == ProductionLog.order_id)
        .where(
            ProductionLog.tenant_id == tenant_id,
            OrderLine.workstation_id == puesto,
            ProductionLog.timestamp >= desde,
            ProductionLog.timestamp < hasta,
        )
        .order_by(ProductionLog.timestamp.asc(), ProductionLog.created_at.asc())
    ).all()

    sesiones: list[dict] = []
    actual: dict | None = None
    for log, numero_orden, linea_numero in filas:
        ts = _utc(log.timestamp)
        if (
            actual is None
            or actual["_operario_id"] != log.operator_id
            or actual["_linea_id"] != log.line_id
            or ts - actual["_ultimo"] > HUECO_SESION
        ):
            actual = {
                "_operario_id": log.operator_id,
                "_linea_id": log.line_id,
                "_ultimo": ts,
                "operario": log.operator.name if log.operator else "Sin operario",
                "orden": numero_orden,
                "linea": linea_numero,
                "inicio": ts.isoformat(),
                "fin": ts.isoformat(),
                "piezas": 0.0,
                "chatarra_kg": 0.0,
                "kg_material": 0.0,
                "bobinas": [],
                "eventos": [],
            }
            sesiones.append(actual)
        ev = _evento(log)
        actual["_ultimo"] = ts
        actual["fin"] = ev["hora"]
        actual["eventos"].append(ev)
        if log.action == "produce":
            actual["piezas"] += ev["cantidad"]
            actual["kg_material"] += ev["kg_material"] or 0
        elif log.action == "scrap":
            actual["chatarra_kg"] += ev["cantidad"]
        if ev["bobina"] and ev["bobina"] not in actual["bobinas"]:
            actual["bobinas"].append(ev["bobina"])

    for s in sesiones:
        s.pop("_operario_id")
        s.pop("_linea_id")
        s.pop("_ultimo")
        inicio, fin = datetime.fromisoformat(s["inicio"]), datetime.fromisoformat(s["fin"])
        s["minutos"] = round((fin - inicio).total_seconds() / 60)
        s["piezas"] = round(s["piezas"])
        s["chatarra_kg"] = round(s["chatarra_kg"], 1)
        s["kg_material"] = round(s["kg_material"], 1)
    sesiones.reverse()
    return sesiones


def ficha_puesto(
    db: Session,
    tenant_id: uuid.UUID,
    codigo: str,
    periodo: str,
    ahora: datetime | None = None,
) -> dict:
    """Ficha del puesto. `LookupError` si no existe; `ValueError` si el periodo no vale."""
    ahora = _utc(ahora or datetime.now(UTC))
    desde, hasta = ventana_periodo(periodo, ahora)

    ws = db.scalar(
        select(Workstation).where(Workstation.tenant_id == tenant_id, Workstation.code == codigo)
    )
    ahora_puesto = next((p for p in estado_puestos(db, tenant_id) if p["code"] == codigo), None)
    if ws is None and ahora_puesto is None:
        raise LookupError(f"Puesto no encontrado: {codigo}")

    medida = _medir(db, tenant_id, desde, hasta)
    mio = next((p for p in medida["detalle_puestos"] if p["puesto"] == codigo), None) or {
        "piezas": 0,
        "plan": None,
        "eficiencia": None,
        "paradas_min": 0,
        "paradas_n": 0,
        "kg_material": 0.0,
        "chatarra_kg": 0.0,
        "chatarra_pct": None,
    }

    causas: dict[str, float] = {}
    for p in paradas_en(db, tenant_id, desde, hasta):
        if p["puesto"] == codigo:
            causas[p["motivo"]] = causas.get(p["motivo"], 0.0) + p["minutos"]
    total = sum(causas.values())

    sesiones = sesiones_de_puesto(db, tenant_id, codigo, desde, hasta)
    ritmo = ws.piezas_hora_nominal if ws else None
    return {
        "puesto": {
            "code": codigo,
            "name": ws.name if ws else codigo,
            "color": ws.color if ws else None,
            "ritmo_nominal": float(ritmo) if ritmo else None,
        },
        "periodo": periodo,
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "ahora": ahora_puesto,
        "piezas": mio["piezas"],
        "plan": mio["plan"],
        "eficiencia": mio["eficiencia"],
        "paradas": {
            "minutos": mio["paradas_min"],
            "numero": mio["paradas_n"],
            "por_causa": sorted(
                (
                    {
                        "causa": c,
                        "minutos": round(m),
                        "pct": round(m / total * 100, 1) if total else None,
                    }
                    for c, m in causas.items()
                ),
                key=lambda x: x["minutos"],
                reverse=True,
            ),
        },
        "material": {
            "kg_consumidos": mio["kg_material"],
            "chatarra_kg": mio["chatarra_kg"],
            "chatarra_pct": mio["chatarra_pct"],
        },
        "sesiones": sesiones,
    }
