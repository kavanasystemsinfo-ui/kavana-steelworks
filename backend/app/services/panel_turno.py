"""Vista Turno del panel de mando: ¿llego al plan del turno y qué hago ahora?

Todo sale de datos que el sistema registra, nunca de supuestos:
- piezas del turno: eventos `produce` del ProductionLog dentro de la ventana
  del turno (A 06-14, B 14-22, C 22-06, horario de planta);
- plan: ritmo nominal (Workstation.piezas_hora_nominal) de los puestos que
  tienen orden asignada, repartido de forma lineal en las 8 h del turno;
- previsión de cierre: piezas actuales + ritmo de la última hora × lo que
  queda de turno;
- paradas: incidencias del turno (abiertas, contando hasta ahora; cerradas,
  con su tiempo de parada declarado);
- chatarra: kg de los eventos `scrap` frente a los kg consumidos.

Sin ritmo nominal no hay plan: se devuelve None y el panel lo dice, en vez
de inventar un objetivo.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Incidencia,
    Order,
    OrderLine,
    Product,
    ProductionLog,
    Tenant,
    Workstation,
    WorkstationGroup,
)
from app.models.parada import MOTIVOS_PARADA
from app.services.alertas import alertas
from app.services.objetivos import objetivos_tenant
from app.services.paradas import paradas_abiertas_por_puesto, paradas_en
from app.services.puestos import ESTADOS_INCIDENCIA_ABIERTA, estado_puestos
from app.services.shifts import TZ_PLANTA

DURACION_TURNO_MIN = 480
INICIO_TURNO = {"A": 6, "B": 14, "C": 22}
TRAMO_SERIE_MIN = 15
SIN_REGISTRAR_MIN = 30  # un puesto "en marcha" sin registrar más de esto se revisa
TIPOS_INCIDENCIA = {
    "maquina": "avería",
    "material": "falta de material",
    "seguridad": "seguridad",
    "otro": "incidencia",
}


def _utc(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


def ventana_turno(ahora: datetime) -> tuple[str, datetime, datetime]:
    """Turno en curso y su inicio y fin (UTC) para el instante dado."""
    local = _utc(ahora).astimezone(TZ_PLANTA)
    if 6 <= local.hour < 14:
        codigo = "A"
    elif 14 <= local.hour < 22:
        codigo = "B"
    else:
        codigo = "C"
    inicio = local.replace(hour=INICIO_TURNO[codigo], minute=0, second=0, microsecond=0)
    if codigo == "C" and local.hour < 6:
        inicio -= timedelta(days=1)
    return (
        codigo,
        inicio.astimezone(UTC),
        (inicio + timedelta(minutes=DURACION_TURNO_MIN)).astimezone(UTC),
    )


def _minutos(desde: datetime, hasta: datetime) -> float:
    return max((_utc(hasta) - _utc(desde)).total_seconds() / 60, 0.0)


def _pct(parte: float, total: float) -> float | None:
    return round(parte / total * 100, 1) if total > 0 else None


def resumen_turno(db: Session, tenant_id: uuid.UUID, ahora: datetime | None = None) -> dict:
    ahora = _utc(ahora or datetime.now(UTC))
    codigo, inicio, fin = ventana_turno(ahora)
    transcurrido = min(_minutos(inicio, ahora), DURACION_TURNO_MIN)
    restante = DURACION_TURNO_MIN - transcurrido

    puestos_db = {
        w.code: w
        for w in db.scalars(
            select(Workstation).where(
                Workstation.tenant_id == tenant_id, Workstation.is_active.is_(True)
            )
        )
    }
    grupos = {
        g.id: g
        for g in db.scalars(select(WorkstationGroup).where(WorkstationGroup.tenant_id == tenant_id))
    }

    def ritmo(code: str | None) -> float | None:
        ws = puestos_db.get(code) if code else None
        return float(ws.piezas_hora_nominal) if ws and ws.piezas_hora_nominal else None

    # --- Producción del turno -------------------------------------------------
    logs = db.scalars(
        select(ProductionLog)
        .where(
            ProductionLog.tenant_id == tenant_id,
            ProductionLog.timestamp >= inicio,
            ProductionLog.timestamp <= ahora,
            ProductionLog.action.in_(("produce", "scrap")),
        )
        .order_by(ProductionLog.timestamp.asc())
    ).all()
    piezas = 0.0
    piezas_ultima_hora = 0.0
    kg_consumidos = 0.0
    kg_chatarra = 0.0
    tramos = [0.0] * (int(transcurrido // TRAMO_SERIE_MIN) + 1)
    for log in logs:
        cantidad = float(log.quantity or 0)
        if log.action == "scrap":
            kg_chatarra += cantidad
            continue
        piezas += cantidad
        if _minutos(log.timestamp, ahora) <= 60:
            piezas_ultima_hora += cantidad
        meta = log.metadata_ or {}
        if meta.get("consumedMaterial") == "kg":
            kg_consumidos += float(meta.get("consumedAmount") or 0)
        indice = min(int(_minutos(inicio, log.timestamp) // TRAMO_SERIE_MIN), len(tramos) - 1)
        tramos[indice] += cantidad

    serie = []
    acumulado = 0.0
    for i, cantidad in enumerate(tramos):
        acumulado += cantidad
        serie.append({"minuto": min((i + 1) * TRAMO_SERIE_MIN, transcurrido), "piezas": acumulado})
    serie.insert(0, {"minuto": 0, "piezas": 0.0})

    # --- Puestos ---------------------------------------------------------------
    monitor = estado_puestos(db, tenant_id)
    lineas_ids = [uuid.UUID(p["orden"]["linea_id"]) for p in monitor if p["orden"]]
    productos: dict[str, str] = {}
    if lineas_ids:
        for linea, nombre in db.execute(
            select(OrderLine.id, Product.name)
            .join(Product, Product.id == OrderLine.product_id)
            .where(OrderLine.id.in_(lineas_ids))
        ).all():
            productos[str(linea)] = nombre

    incidencias_abiertas = {
        i.puesto: i
        for i in db.scalars(
            select(Incidencia)
            .where(
                Incidencia.tenant_id == tenant_id,
                Incidencia.estado.in_(ESTADOS_INCIDENCIA_ABIERTA),
            )
            .order_by(Incidencia.created_at.asc())
        )
    }

    paradas_operario = paradas_abiertas_por_puesto(db, tenant_id)

    puestos = []
    plan_hora = 0.0
    for p in monitor:
        ws = puestos_db.get(p["code"])
        grupo = grupos.get(ws.group_id) if ws and ws.group_id else None
        orden = p["orden"]
        estado = {
            "incidencia": "parado",
            "en_curso": "en_marcha",
            "parado": "parado",
            "pendiente": "preparado",
            "libre": "sin_orden",
        }[p["estado"]]
        motivo = None
        minutos = None
        parada = paradas_operario.get(p["code"])
        if parada is not None and p["estado"] != "incidencia":
            # El operario ha parado la máquina con un toque (avería, limpieza...)
            estado = "parado"
            motivo = MOTIVOS_PARADA[parada.motivo].capitalize()
            minutos = round(_minutos(parada.inicio, ahora))
        elif p["estado"] == "incidencia":
            inc = incidencias_abiertas.get(p["code"])
            if inc is not None:
                motivo = TIPOS_INCIDENCIA.get(inc.tipo, "incidencia").capitalize()
                minutos = round(_minutos(inc.created_at, ahora))
        elif p["ultima_actividad"]:
            minutos = round(
                _minutos(datetime.fromisoformat(p["ultima_actividad"]["timestamp"]), ahora)
            )
        if estado == "en_marcha" and minutos is not None and minutos > SIN_REGISTRAR_MIN:
            estado = "sin_registrar"
        r = ritmo(p["code"])
        if orden and r:
            plan_hora += r
        puestos.append(
            {
                "code": p["code"],
                "name": p["name"],
                "grupo": grupo.name if grupo else None,
                "estado": estado,
                "motivo": motivo,
                "minutos": minutos,
                "ritmo_nominal": r,
                "orden": (
                    {
                        "numero": orden["numero"],
                        "producto": productos.get(orden["linea_id"]) or orden["cliente"],
                        "piezas": orden["piezas"],
                        "objetivo": orden["objetivo"],
                    }
                    if orden
                    else None
                ),
            }
        )
    # Orden del flujo de la planta: grupos por fecha de alta, sin grupo al final
    rango_grupo = {
        g.name: i for i, g in enumerate(sorted(grupos.values(), key=lambda g: _utc(g.created_at)))
    }
    puestos.sort(key=lambda p: (rango_grupo.get(p["grupo"], len(rango_grupo)), p["code"]))

    # --- Plan y previsión ------------------------------------------------------
    if plan_hora > 0:
        plan_turno = round(plan_hora * DURACION_TURNO_MIN / 60)
        plan_ahora = round(plan_hora * transcurrido / 60)
    else:
        plan_turno = plan_ahora = None
    ritmo_reciente = piezas_ultima_hora / min(transcurrido, 60) * 60 if transcurrido >= 30 else None
    prevision = (
        round(piezas + ritmo_reciente * restante / 60) if ritmo_reciente is not None else None
    )

    # --- Paradas ---------------------------------------------------------------
    paradas = [
        {
            "puesto": x["puesto"],
            "motivo": x["motivo"],
            "descripcion": x["descripcion"],
            "minutos": round(x["minutos"]),
            "abierta": x["abierta"],
        }
        for x in paradas_en(db, tenant_id, inicio, ahora)
    ]
    paradas.sort(key=lambda x: x["minutos"], reverse=True)
    minutos_parado = sum(x["minutos"] for x in paradas)

    # --- Eficiencia del turno (OEE) --------------------------------------------
    planificados = sum(1 for p in puestos if p["orden"] and p["ritmo_nominal"])
    chatarra_pct = _pct(kg_chatarra, kg_consumidos + kg_chatarra)
    eficiencia = None
    if plan_hora > 0 and transcurrido > 0:
        tiempo_plan = planificados * transcurrido
        disponibilidad = max(1 - minutos_parado / tiempo_plan, 0) if tiempo_plan else 0
        esperado = plan_hora * transcurrido / 60 * disponibilidad
        rendimiento = min(piezas / esperado, 1) if esperado > 0 else 0
        calidad = 1 - (chatarra_pct or 0) / 100
        factores = {
            "disponibilidad": round(disponibilidad * 100, 1),
            "rendimiento": round(rendimiento * 100, 1),
            "calidad": round(calidad * 100, 1),
        }
        eficiencia = {
            "oee": round(disponibilidad * rendimiento * calidad * 100, 1),
            **factores,
            "mas_resta": min(factores, key=factores.get),
        }

    # --- Órdenes en curso ------------------------------------------------------
    ordenes = []
    for orden in db.scalars(
        select(Order)
        .where(Order.tenant_id == tenant_id, Order.estado == "active")
        .order_by(Order.fecha_entrega.asc().nulls_last(), Order.numero.asc())
    ):
        lineas = sorted(orden.lines, key=lambda ln: ln.linea_numero)
        abiertas = [ln for ln in lineas if ln.estado != "completed"]
        if not abiertas:
            continue
        actual = next((ln for ln in abiertas if ln.estado == "in_progress"), abiertas[0])
        horas_faltan = 0.0
        sin_ritmo = False
        for ln in abiertas:
            r = ritmo(ln.workstation_id)
            pendiente = float((ln.total_quantity or 0) - (ln.produced_quantity or 0))
            if r is None:
                sin_ritmo = True
            else:
                horas_faltan += max(pendiente, 0) / r
        entrega = _utc(orden.fecha_entrega) if orden.fecha_entrega else None
        horas_quedan = (entrega - ahora).total_seconds() / 3600 if entrega else None
        if entrega is None or sin_ritmo:
            estado = "sin_plazo" if entrega is None else "sin_ritmo"
        elif horas_quedan <= 0 or horas_faltan > horas_quedan:
            estado = "retraso"
        elif horas_faltan > horas_quedan * 0.7:
            estado = "en_riesgo"
        else:
            estado = "a_tiempo"
        producto = None
        if actual.product_id:
            prod = db.get(Product, actual.product_id)
            producto = prod.name if prod else None
        ordenes.append(
            {
                "numero": orden.numero,
                "producto": producto or orden.cliente,
                "puesto": actual.workstation_id,
                "piezas": float(actual.produced_quantity or 0),
                "objetivo": float(actual.total_quantity or 0),
                "entrega": entrega.isoformat() if entrega else None,
                "horas_faltan": round(horas_faltan, 1) if not sin_ritmo else None,
                "horas_quedan": round(horas_quedan, 1) if horas_quedan is not None else None,
                "estado": estado,
            }
        )
    prioridad_orden = {"retraso": 0, "en_riesgo": 1, "a_tiempo": 2, "sin_ritmo": 3, "sin_plazo": 4}
    ordenes.sort(key=lambda o: prioridad_orden[o["estado"]])

    # --- Pendiente de actuar ---------------------------------------------------
    pendientes = []
    for inc in incidencias_abiertas.values():
        pendientes.append(
            {
                "urgencia": "urgente",
                "titulo": f"{inc.puesto} parado · {TIPOS_INCIDENCIA.get(inc.tipo, 'incidencia')}",
                "detalle": inc.descripcion,
                "minutos": round(_minutos(inc.created_at, ahora)),
                "accion": "incidencia",
                "ref": str(inc.id),
            }
        )
    for m in alertas(db, tenant_id)["stock_bajo_minimos"]:
        pendientes.append(
            {
                "urgencia": "hoy",
                "titulo": f"Stock bajo mínimo: {m['name']}",
                "detalle": (
                    f"Quedan {m['stock']:g} {m['unidad']}, mínimo {m['minimo']:g}. "
                    "Avisa a Materias Primas para reponer."
                ),
                "minutos": None,
                "accion": "stock",
                "ref": m["code"],
            }
        )
    for o in ordenes:
        if o["estado"] in ("retraso", "en_riesgo"):
            pendientes.append(
                {
                    "urgencia": "hoy",
                    "titulo": f"Orden {o['numero']} "
                    + ("va con retraso" if o["estado"] == "retraso" else "en riesgo"),
                    "detalle": (
                        f"Necesita {o['horas_faltan']:g} h de trabajo y quedan "
                        f"{max(o['horas_quedan'], 0):g} h hasta la entrega."
                    ),
                    "minutos": None,
                    "accion": "orden",
                    "ref": o["numero"],
                }
            )
    for p in puestos:
        if p["estado"] == "sin_registrar":
            pendientes.append(
                {
                    "urgencia": "revisar",
                    "titulo": f"{p['code']} sin registrar producción",
                    "detalle": f"Orden en curso sin registros desde hace {p['minutos']} min.",
                    "minutos": p["minutos"],
                    "accion": "puesto",
                    "ref": p["code"],
                }
            )

    return {
        "turno": {
            "codigo": codigo,
            "inicio": inicio.isoformat(),
            "fin": fin.isoformat(),
            "transcurrido_min": round(transcurrido),
            "duracion_min": DURACION_TURNO_MIN,
        },
        "piezas": round(piezas),
        "plan_turno": plan_turno,
        "plan_ahora": plan_ahora,
        "prevision_cierre": prevision,
        "serie": serie,
        "eficiencia": eficiencia,
        "paradas": {
            "minutos": minutos_parado,
            "numero": len(paradas),
            "mayor": paradas[0] if paradas else None,
        },
        "chatarra": {"kg": round(kg_chatarra, 1), "pct": chatarra_pct},
        "objetivos": objetivos_tenant(db.get(Tenant, tenant_id)),
        "puestos": puestos,
        "ordenes": ordenes,
        "pendientes": pendientes,
    }
