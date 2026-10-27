"""Vista Planta del panel de mando: ¿cómo va la planta y dónde perdemos?

Para el jefe de planta o el CTO: el periodo (hoy, esta semana, últimas 8
semanas) frente al periodo anterior de la misma duración, con datos
registrados y nada supuesto:
- horas trabajadas de cada puesto: piezas / eficiencia de cada evento
  `produce` (la eficiencia la guarda record_production como piezas/hora);
- paradas: incidencias del periodo (cerradas, con su tiempo declarado;
  abiertas, hasta ahora), recortadas a la ventana;
- eficiencia (OEE) = tiempo en marcha × velocidad × calidad:
  tiempo en marcha = horas trabajadas / (trabajadas + paradas),
  velocidad = piezas / (ritmo nominal × horas trabajadas),
  calidad = 1 − kg de chatarra / kg de material;
- entregas: órdenes cuya última producción cae en el periodo, a tiempo si fue
  antes de su fecha de entrega.

Un puesto sin ritmo nominal no entra en la velocidad; sin horas registradas
no hay eficiencia y el panel lo dice.
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Incidencia, Order, OrderLine, ProductionLog, Tenant, Workstation
from app.services.objetivos import objetivos_tenant
from app.services.panel_turno import TIPOS_INCIDENCIA, _utc, resumen_turno
from app.services.puestos import ESTADOS_INCIDENCIA_ABIERTA
from app.services.shifts import TZ_PLANTA

PERIODOS = ("hoy", "semana", "8semanas")
SEMANAS_TENDENCIA = 8


def ventana_periodo(periodo: str, ahora: datetime) -> tuple[datetime, datetime]:
    """Inicio (UTC) del periodo en horario de planta y su fin (ahora)."""
    if periodo not in PERIODOS:
        raise ValueError(f"Periodo no válido: {periodo}")
    local = _utc(ahora).astimezone(TZ_PLANTA)
    dia = local.replace(hour=0, minute=0, second=0, microsecond=0)
    lunes = dia - timedelta(days=dia.weekday())
    inicio = {
        "hoy": dia,
        "semana": lunes,
        "8semanas": lunes - timedelta(weeks=SEMANAS_TENDENCIA - 1),
    }[periodo]
    return inicio.astimezone(UTC), _utc(ahora)


def _pct(parte: float, total: float) -> float | None:
    return round(parte / total * 100, 1) if total > 0 else None


def _medir(db: Session, tenant_id: uuid.UUID, desde: datetime, hasta: datetime) -> dict:
    """Producción, paradas y eficiencia de una ventana, global y por puesto."""
    ritmos = {
        w.code: float(w.piezas_hora_nominal)
        for w in db.scalars(
            select(Workstation).where(
                Workstation.tenant_id == tenant_id, Workstation.is_active.is_(True)
            )
        )
        if w.piezas_hora_nominal
    }

    por_puesto: dict[str, dict] = defaultdict(
        lambda: {"piezas": 0.0, "horas": 0.0, "piezas_medidas": 0.0, "paradas_min": 0.0}
    )
    kg_material = 0.0
    kg_chatarra = 0.0
    filas = db.execute(
        select(ProductionLog, OrderLine.workstation_id)
        .join(OrderLine, OrderLine.id == ProductionLog.line_id)
        .where(
            ProductionLog.tenant_id == tenant_id,
            ProductionLog.timestamp >= desde,
            ProductionLog.timestamp < hasta,
            ProductionLog.action.in_(("produce", "scrap")),
        )
    ).all()
    for log, puesto in filas:
        cantidad = float(log.quantity or 0)
        if log.action == "scrap":
            kg_chatarra += cantidad
            continue
        meta = log.metadata_ or {}
        if meta.get("consumedMaterial") == "kg":
            kg_material += float(meta.get("consumedAmount") or 0)
        p = por_puesto[puesto or "—"]
        p["piezas"] += cantidad
        eficiencia = meta.get("efficiency")
        if eficiencia:
            p["horas"] += cantidad / float(eficiencia)
            p["piezas_medidas"] += cantidad

    paradas_causa: dict[str, float] = defaultdict(float)
    numero_paradas = 0
    for inc in db.scalars(
        select(Incidencia).where(Incidencia.tenant_id == tenant_id, Incidencia.created_at < hasta)
    ):
        creada = _utc(inc.created_at)
        if inc.estado in ESTADOS_INCIDENCIA_ABIERTA:
            minutos = (hasta - max(creada, desde)).total_seconds() / 60
        elif creada >= desde:
            minutos = float(inc.tiempo_parada_min or 0)
        else:
            continue
        if minutos <= 0:
            continue
        numero_paradas += 1
        paradas_causa[inc.tipo] += minutos
        por_puesto[inc.puesto]["paradas_min"] += minutos

    calidad = 1 - (kg_chatarra / (kg_material + kg_chatarra)) if kg_material + kg_chatarra else 1.0

    def factores(horas: float, paradas_min: float, piezas_medidas: float, nominal: float):
        if horas <= 0:
            return None
        marcha = horas / (horas + paradas_min / 60)
        velocidad = min(piezas_medidas / nominal, 1.0) if nominal > 0 else None
        if velocidad is None:
            return None
        return {
            "oee": round(marcha * velocidad * calidad * 100, 1),
            "disponibilidad": round(marcha * 100, 1),
            "rendimiento": round(velocidad * 100, 1),
            "calidad": round(calidad * 100, 1),
        }

    puestos = []
    horas_tot = paradas_tot = medidas_tot = nominal_tot = 0.0
    plan = 0.0
    for code, p in por_puesto.items():
        ritmo = ritmos.get(code)
        nominal = ritmo * p["horas"] if ritmo else 0.0
        f = factores(p["horas"], p["paradas_min"], p["piezas_medidas"], nominal)
        if ritmo:
            horas_tot += p["horas"]
            paradas_tot += p["paradas_min"]
            medidas_tot += p["piezas_medidas"]
            nominal_tot += nominal
            plan += ritmo * (p["horas"] + p["paradas_min"] / 60)
        if f is not None:
            puestos.append({"puesto": code, **f})
    puestos.sort(key=lambda x: x["oee"])

    piezas = sum(p["piezas"] for p in por_puesto.values())
    minutos_parado = sum(paradas_causa.values())
    return {
        "piezas": round(piezas),
        "plan": round(plan) if plan else None,
        "eficiencia": factores(horas_tot, paradas_tot, medidas_tot, nominal_tot),
        "paradas": {
            "minutos": round(minutos_parado),
            "numero": numero_paradas,
            "media_min": round(minutos_parado / numero_paradas) if numero_paradas else None,
            "por_causa": sorted(
                (
                    {
                        "causa": TIPOS_INCIDENCIA.get(tipo, "otra"),
                        "minutos": round(m),
                        "pct": _pct(m, minutos_parado),
                    }
                    for tipo, m in paradas_causa.items()
                ),
                key=lambda x: x["minutos"],
                reverse=True,
            ),
        },
        "chatarra_pct": _pct(kg_chatarra, kg_material + kg_chatarra),
        "puestos": puestos,
    }


def _entregas(db: Session, tenant_id: uuid.UUID, desde: datetime, hasta: datetime) -> dict:
    """Órdenes terminadas en la ventana (última producción) y cuántas a tiempo."""
    ultimas = db.execute(
        select(Order, func.max(ProductionLog.timestamp))
        .join(ProductionLog, ProductionLog.order_id == Order.id)
        .where(
            Order.tenant_id == tenant_id,
            Order.estado == "completed",
            ProductionLog.action == "produce",
        )
        .group_by(Order.id)
    ).all()
    total = a_tiempo = 0
    tarde = []
    for orden, ultima in ultimas:
        ultima = _utc(ultima)
        if not (desde <= ultima < hasta) or orden.fecha_entrega is None:
            continue
        total += 1
        if ultima <= _utc(orden.fecha_entrega):
            a_tiempo += 1
        else:
            tarde.append(orden.numero)
    return {"total": total, "a_tiempo": a_tiempo, "tarde": tarde}


def _semanas(db: Session, tenant_id: uuid.UUID, ahora: datetime) -> list[dict]:
    """Eficiencia de las últimas 8 semanas (lunes a domingo, horario de planta)."""
    local = _utc(ahora).astimezone(TZ_PLANTA)
    lunes = (local - timedelta(days=local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    serie = []
    for i in range(SEMANAS_TENDENCIA - 1, -1, -1):
        inicio = lunes - timedelta(weeks=i)
        fin = min(inicio + timedelta(weeks=1), local)
        medida = _medir(db, tenant_id, inicio.astimezone(UTC), fin.astimezone(UTC))
        serie.append(
            {
                "semana": f"S{inicio.isocalendar().week}",
                "oee": medida["eficiencia"]["oee"] if medida["eficiencia"] else None,
            }
        )
    return serie


def resumen_planta(
    db: Session, tenant_id: uuid.UUID, periodo: str, ahora: datetime | None = None
) -> dict:
    ahora = _utc(ahora or datetime.now(UTC))
    desde, hasta = ventana_periodo(periodo, ahora)
    duracion = hasta - desde
    actual = _medir(db, tenant_id, desde, hasta)
    anterior = _medir(db, tenant_id, desde - duracion, desde)
    entregas = _entregas(db, tenant_id, desde, hasta)

    ordenes = [
        o
        for o in resumen_turno(db, tenant_id, ahora)["ordenes"]
        if o["estado"] in ("retraso", "en_riesgo", "a_tiempo")
    ]

    return {
        "periodo": periodo,
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        **actual,
        "anterior": {
            "eficiencia": anterior["eficiencia"]["oee"] if anterior["eficiencia"] else None,
            "piezas": anterior["piezas"],
            "paradas_min": anterior["paradas"]["minutos"],
        },
        "entregas": entregas,
        "tendencia": _semanas(db, tenant_id, ahora),
        "ordenes": ordenes,
        "objetivos": objetivos_tenant(db.get(Tenant, tenant_id)),
    }
