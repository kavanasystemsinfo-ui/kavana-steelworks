"""Simulador de planta para la demo (adopción del simulador cron del legacy).

Una demo con todo a cero parece muerta; una con cifras inventadas miente.
El simulador hace lo que haría un operario, con los MISMOS servicios:
vincula una bobina (link_coil) y registra producción (record_production).
Así cada dato pasa por las mismas reglas, guardias y trazabilidad que en
planta, y queda marcado en el ProductionLog con source=simulador.

Solo actúa sobre el tenant demo (buscar_tenant_demo). Un tick:
1. Si un puesto no tiene línea en curso, arranca la siguiente pendiente.
2. A cada línea en curso sin bobina le vincula la bobina FIFO de su material.
3. Registra unas pocas piezas con el tiempo proporcional.
Lo que el sistema rechace (guardia de kilos, WIP, sin stock) se salta y se
informa: el simulador nunca fuerza datos.

Uso (una ejecución = un tick; la programación queda fuera del repo):
    python -m app.services.simulador
"""

import random
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, OrderLine, StockItem, User

MINUTOS_POR_PIEZA = Decimal("3")


def _operario_demo(db: Session, tenant_id) -> User | None:
    return db.scalar(
        select(User)
        .where(User.tenant_id == tenant_id, User.role == "operator", User.is_active.is_(True))
        .order_by(User.created_at)
    )


def _bobina_fifo(db: Session, tenant_id, material_id) -> StockItem | None:
    """Bobina FIFO del material que no esté ya activa en otra línea.

    link_coil cobra la bobina entera en cada línea que la vincula; el
    simulador no la reparte entre dos líneas para no duplicar el coste.
    """
    en_uso = select(OrderLine.active_coil_id).where(OrderLine.active_coil_id.is_not(None))
    return db.scalar(
        select(StockItem)
        .where(
            StockItem.tenant_id == tenant_id,
            StockItem.material_id == material_id,
            StockItem.estado == "activo",
            StockItem.cantidad_disponible > 0,
            StockItem.id.not_in(en_uso),
        )
        .order_by(StockItem.fecha_entrada.asc())
    )


def simular_tick(db: Session, rng: random.Random | None = None) -> dict:
    """Un paso de simulación sobre el tenant demo. Devuelve qué hizo."""
    from app.services.inventory import link_coil
    from app.services.production import record_production
    from app.services.seed_demo import buscar_tenant_demo

    rng = rng or random.Random()
    tenant = buscar_tenant_demo(db)
    if tenant is None:
        return {"tenant": None, "acciones": [], "saltos": ["sin tenant demo"]}
    operario = _operario_demo(db, tenant.id)
    if operario is None:
        return {"tenant": str(tenant.id), "acciones": [], "saltos": ["sin operario demo"]}

    acciones: list[str] = []
    saltos: list[str] = []

    lineas = db.execute(
        select(OrderLine, Order)
        .join(Order, Order.id == OrderLine.order_id)
        .where(Order.tenant_id == tenant.id, Order.estado == "active")
        .order_by(Order.created_at.asc(), OrderLine.linea_numero.asc())
    ).all()

    # 1. Arrancar la siguiente línea pendiente en los puestos sin trabajo
    ocupados = {ln.workstation_id for ln, _ in lineas if ln.estado == "in_progress"}
    for linea, orden in lineas:
        if linea.estado == "pending" and linea.workstation_id not in ocupados:
            linea.estado = "in_progress"
            ocupados.add(linea.workstation_id)
            acciones.append(
                f"arranca {orden.numero} L{linea.linea_numero} en {linea.workstation_id}"
            )
    db.commit()

    for linea, orden in lineas:
        if linea.estado != "in_progress":
            continue
        etiqueta = f"{orden.numero} L{linea.linea_numero}"

        # 2. Vincular bobina FIFO del material de la línea
        if linea.active_coil_id is None and linea.material_id is not None:
            bobina = _bobina_fifo(db, tenant.id, linea.material_id)
            if bobina is None:
                saltos.append(f"{etiqueta}: sin stock de su material")
                continue
            try:
                link_coil(
                    db, tenant.id, operario.id,
                    stock_item_id=bobina.id, order_id=orden.id, line_id=linea.id,
                )
                acciones.append(f"vincula {bobina.coil_id} a {etiqueta}")
            except ValueError as exc:
                db.rollback()
                saltos.append(f"{etiqueta}: {exc}")
                continue

        # 3. Producir unas piezas
        restantes = (linea.total_quantity or 0) - (linea.produced_quantity or 0)
        if restantes <= 0:
            continue
        tope = restantes
        previa = next(
            (ln for ln, o in lineas
             if o.id == orden.id and ln.linea_numero == linea.linea_numero - 1),
            None,
        )
        if previa is not None:  # WIP: no producir más de lo que entregó el paso anterior
            tope = min(tope, (previa.produced_quantity or 0) - (linea.produced_quantity or 0))
        if tope <= 0:
            saltos.append(f"{etiqueta}: esperando piezas del paso anterior")
            continue
        piezas = min(Decimal(rng.randint(1, 4)), tope)
        horas = (piezas * MINUTOS_POR_PIEZA / 60).quantize(Decimal("0.01"))
        try:
            record_production(
                db, tenant.id, operario.id,
                order_id=orden.id, line_id=linea.id,
                incremental_quantity=piezas, hours_worked=horas,
                observaciones="simulador demo",
            )
            acciones.append(f"produce {piezas} uds en {etiqueta}")
        except ValueError as exc:
            db.rollback()
            saltos.append(f"{etiqueta}: {exc}")

    return {"tenant": str(tenant.id), "acciones": acciones, "saltos": saltos}


if __name__ == "__main__":
    from app.core.database import engine

    with Session(engine) as sesion:
        resultado = simular_tick(sesion)
    print(f"[simulador] tenant={resultado['tenant']}")
    for accion in resultado["acciones"]:
        print(f"  + {accion}")
    for salto in resultado["saltos"]:
        print(f"  - {salto}")
