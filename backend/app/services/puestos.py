"""Monitor de puestos en planta (adopción del legacy: "un vistazo, un click").

Una tarjeta por puesto con lo que el sistema SABE, no con lo que supone:
- la línea de orden que tiene asignada (en curso > parada > pendiente),
- la bobina vinculada, el progreso en piezas,
- la última actividad registrada (ProductionLog) y quién la hizo,
- las incidencias abiertas del puesto.

El estado sale de esos datos: "incidencia" manda sobre todo (es el andon
rojo); después "en_curso", "parado", "pendiente" o "libre". La hora de la
última actividad va siempre al lado para que el supervisor juzgue si un
puesto "en curso" lleva rato sin registrar.

El mantenimiento preventivo no aparece: accumulated_hours aún no se
incrementa en ningún flujo, y mostrarlo sería inventar (matriz de adopción,
fila 9: pospuesto).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Incidencia, Order, OrderLine, ProductionLog, User, Workstation

ESTADOS_INCIDENCIA_ABIERTA = ("abierta", "en_revision")
PRIORIDAD_LINEA = {"in_progress": 0, "stopped": 1, "pending": 2}
ESTADO_PUESTO = {"in_progress": "en_curso", "stopped": "parado", "pending": "pendiente"}


def estado_puestos(db: Session, tenant_id: uuid.UUID) -> list[dict]:
    puestos = {
        w.code: w
        for w in db.scalars(
            select(Workstation).where(
                Workstation.tenant_id == tenant_id, Workstation.is_active.is_(True)
            )
        )
    }

    filas = db.execute(
        select(OrderLine, Order)
        .join(Order, Order.id == OrderLine.order_id)
        .where(
            Order.tenant_id == tenant_id,
            Order.estado == "active",
            OrderLine.estado.in_(tuple(PRIORIDAD_LINEA)),
            OrderLine.workstation_id.is_not(None),
        )
        .order_by(Order.created_at.asc(), OrderLine.linea_numero.asc())
    ).all()
    linea_por_puesto: dict[str, tuple[OrderLine, Order]] = {}
    for linea, orden in filas:
        actual = linea_por_puesto.get(linea.workstation_id)
        if actual is None or PRIORIDAD_LINEA[linea.estado] < PRIORIDAD_LINEA[actual[0].estado]:
            linea_por_puesto[linea.workstation_id] = (linea, orden)

    incidencias: dict[str, list[Incidencia]] = {}
    for inc in db.scalars(
        select(Incidencia)
        .where(
            Incidencia.tenant_id == tenant_id,
            Incidencia.estado.in_(ESTADOS_INCIDENCIA_ABIERTA),
        )
        .order_by(Incidencia.created_at.desc())
    ):
        incidencias.setdefault(inc.puesto, []).append(inc)

    codigos = sorted(set(puestos) | set(linea_por_puesto))
    resultado = []
    for code in codigos:
        ws = puestos.get(code)
        linea, orden = linea_por_puesto.get(code, (None, None))
        abiertas = incidencias.get(code, [])

        ultima = None
        if linea is not None:
            log = db.scalars(
                select(ProductionLog)
                .where(ProductionLog.line_id == linea.id)
                .order_by(ProductionLog.timestamp.desc())
                .limit(1)
            ).first()
            if log is not None:
                operario = db.get(User, log.operator_id)
                ultima = {
                    "accion": log.action,
                    "timestamp": log.timestamp.isoformat(),
                    "operario": operario.name if operario else None,
                }

        if abiertas:
            estado = "incidencia"
        elif linea is not None:
            estado = ESTADO_PUESTO[linea.estado]
        else:
            estado = "libre"

        resultado.append(
            {
                "code": code,
                "name": ws.name if ws else code,
                "color": ws.color if ws else None,
                "estado": estado,
                "orden": (
                    {
                        "id": str(orden.id),
                        "numero": orden.numero,
                        "cliente": orden.cliente,
                        "linea_id": str(linea.id),
                        "piezas": float(linea.produced_quantity or 0),
                        "objetivo": float(linea.total_quantity or 0),
                        "bobina": linea.active_coil_code,
                    }
                    if linea is not None
                    else None
                ),
                "ultima_actividad": ultima,
                "incidencias_abiertas": [
                    {"id": str(i.id), "tipo": i.tipo, "descripcion": i.descripcion}
                    for i in abiertas
                ],
            }
        )
    return resultado
