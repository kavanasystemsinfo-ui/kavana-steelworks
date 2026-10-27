"""Simulador de planta para la demo (adopción del simulador cron del legacy).

Una demo con todo a cero parece muerta; una con cifras inventadas miente.
El simulador hace lo que haría un operario, con los MISMOS servicios:
vincula una bobina (link_coil) y registra producción (record_production).
Así cada dato pasa por las mismas reglas, guardias y trazabilidad que en
planta, y queda marcado en el ProductionLog con source=simulador.

Solo actúa sobre el tenant demo (buscar_tenant_demo). Un tick:
0. Reposición para que la demo no se agote: si quedan menos de
   ORDENES_ACTIVAS_MIN órdenes activas, lanza una nueva copiando una
   completada (número de la secuencia real); si un material no tiene bobina
   libre, recibe una nueva igual a la última (receive_coil, con su kardex).
1. Si un puesto no tiene línea en curso, arranca la siguiente pendiente.
2. A cada línea en curso sin bobina le vincula la bobina FIFO de su material.
3. Registra piezas: si el puesto tiene ritmo nominal, entre el 60 % y el 100 %
   de su ritmo en el intervalo del tick; si no, unas pocas (1-4).
Lo que el sistema rechace (guardia de kilos, WIP) se salta y se informa: el
simulador nunca fuerza datos.

Programación (ADR-021): bucle dentro del backend (bucle_simulador), activado
con STEELWORKS_SIMULADOR_MINUTOS > 0 y solo en horario laboral de planta
(lunes a viernes, turnos A y B). Corre mientras la máquina está despierta,
es decir, cuando alguien usa la demo. Un tick suelto a mano:
    python -m app.services.simulador
"""

import asyncio
import logging
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, OrderLine, StockItem, User, Workstation

MINUTOS_POR_PIEZA = Decimal("3")
ORDENES_ACTIVAS_MIN = 2

logger = logging.getLogger(__name__)


def en_horario_laboral(ahora: datetime | None = None) -> bool:
    """Lunes a viernes, 06:00-22:00 en horario de planta (turnos A y B)."""
    from app.services.shifts import TZ_PLANTA

    local = (ahora or datetime.now(UTC)).astimezone(TZ_PLANTA)
    return local.weekday() < 5 and 6 <= local.hour < 22


def _reponer_ordenes(db: Session, tenant_id, rng: random.Random) -> list[str]:
    """Lanza órdenes nuevas copiando completadas hasta tener el mínimo activo."""
    from app.services.sequences import next_sequence

    activas = db.scalars(
        select(Order).where(Order.tenant_id == tenant_id, Order.estado == "active")
    ).all()
    plantillas = db.scalars(
        select(Order)
        .where(Order.tenant_id == tenant_id, Order.estado == "completed")
        .order_by(Order.created_at.asc())
    ).all()
    acciones = []
    for _ in range(ORDENES_ACTIVAS_MIN - len(activas)):
        if not plantillas:
            break
        plantilla = rng.choice(plantillas)
        orden = Order(
            tenant_id=tenant_id,
            numero=next_sequence(db, tenant_id, "order"),
            estado="active",
            cliente=plantilla.cliente,
            fecha_entrega=datetime.now(UTC) + timedelta(days=7),
            notas="Orden generada por el simulador (demo).",
        )
        db.add(orden)
        db.flush()
        tope_paso = None  # WIP: ningún paso pide más que el anterior
        for ln in sorted(plantilla.lines, key=lambda x: x.linea_numero):
            total = ln.total_quantity if tope_paso is None else min(ln.total_quantity, tope_paso)
            tope_paso = total
            db.add(
                OrderLine(
                    order_id=orden.id,
                    linea_numero=ln.linea_numero,
                    product_id=ln.product_id,
                    modelo_id=ln.modelo_id,
                    material_id=ln.material_id,
                    workstation_id=ln.workstation_id,
                    estado="pending",
                    total_quantity=total,
                    meters_per_piece=ln.meters_per_piece,
                    target_material_qty=ln.target_material_qty,
                    target_material_unit=ln.target_material_unit,
                )
            )
        db.commit()
        acciones.append(f"lanza {orden.numero} (copia de {plantilla.numero})")
    return acciones


def _reponer_bobina(db: Session, tenant_id, material_id, user_id) -> StockItem | None:
    """Recibe una bobina igual a la última del material (flujo real de recepción)."""
    from app.services.receiving import receive_coil

    ultima = db.scalar(
        select(StockItem)
        .where(StockItem.tenant_id == tenant_id, StockItem.material_id == material_id)
        .order_by(StockItem.fecha_entrada.desc())
    )
    if ultima is None:
        return None
    marca = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return receive_coil(
        db, tenant_id, user_id,
        material_id=material_id,
        lote=f"SIM-{marca}",
        coil_id=f"SIM-{ultima.material.code}-{marca}",
        peso=ultima.cantidad_inicial,
        width_mm=ultima.width_mm,
        thickness_mm=ultima.thickness_mm,
        coste_real=ultima.coste_por_unidad,
        ubicacion="ALMACEN",
        grado_acero=ultima.grado_acero,
    )


def _operario_demo(db: Session, tenant_id) -> User | None:
    return db.scalar(
        select(User)
        .where(User.tenant_id == tenant_id, User.role == "operator", User.is_active.is_(True))
        .order_by(User.created_at)
    )


def _bobina_fifo(db: Session, tenant_id, material_id) -> StockItem | None:
    """Bobina FIFO del material, libre y con material de verdad.

    Libre: link_coil rechaza una bobina activa en otra línea. Con material:
    más del 5 % de su peso inicial, para no volver a montar una bobina que
    se acaba de agotar (bucle con la guardia de kilos).
    """
    en_uso = select(OrderLine.active_coil_id).where(OrderLine.active_coil_id.is_not(None))
    return db.scalar(
        select(StockItem)
        .where(
            StockItem.tenant_id == tenant_id,
            StockItem.material_id == material_id,
            StockItem.estado == "activo",
            StockItem.cantidad_disponible > StockItem.cantidad_inicial * Decimal("0.05"),
            StockItem.id.not_in(en_uso),
        )
        .order_by(StockItem.fecha_entrada.asc())
    )


def simular_tick(
    db: Session, rng: random.Random | None = None, minutos_tick: int = 5
) -> dict:
    """Un paso de simulación sobre el tenant demo. Devuelve qué hizo."""
    from app.services.inventory import create_retal, link_coil, unlink_coil
    from app.services.production import record_production
    from app.services.seed_demo import buscar_tenant_demo

    rng = rng or random.Random()
    tenant = buscar_tenant_demo(db)
    if tenant is None:
        return {"tenant": None, "acciones": [], "saltos": ["sin tenant demo"]}
    operario = _operario_demo(db, tenant.id)
    if operario is None:
        return {"tenant": str(tenant.id), "acciones": [], "saltos": ["sin operario demo"]}

    acciones: list[str] = _reponer_ordenes(db, tenant.id, rng)
    ritmos = {
        w.code: w.piezas_hora_nominal
        for w in db.scalars(select(Workstation).where(Workstation.tenant_id == tenant.id))
        if w.piezas_hora_nominal
    }
    saltos: list[str] = []

    def soltar_bobina(linea: OrderLine, orden: Order, motivo: str) -> None:
        """Desvincula como haría el operario (reembolso de lo no consumido)."""
        codigo = linea.active_coil_code
        try:
            unlink_coil(
                db, tenant.id, operario.id,
                stock_item_id=linea.active_coil_id, order_id=orden.id, line_id=linea.id,
            )
            acciones.append(
                f"desvincula {codigo} de {orden.numero} L{linea.linea_numero} ({motivo})"
            )
        except ValueError as exc:
            db.rollback()
            saltos.append(f"{orden.numero} L{linea.linea_numero}: {exc}")

    def cerrar_corto(linea: OrderLine, orden: Order) -> None:
        """Cierra la línea con faltante y, si era la última, la orden."""
        from app.services.costes import actualizar_costes_orden

        if linea.active_coil_id is not None:
            soltar_bobina(linea, orden, "cierre con faltante")
        linea.estado = "completed"
        db.flush()
        if all(ln.estado == "completed" for ln in orden.lines):
            orden.estado = "completed"
        actualizar_costes_orden(db, orden)
        db.commit()
        acciones.append(
            f"cierra {orden.numero} L{linea.linea_numero} con faltante "
            f"({linea.produced_quantity}/{linea.total_quantity})"
        )

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
                bobina = _reponer_bobina(db, tenant.id, linea.material_id, operario.id)
                if bobina is None:
                    saltos.append(f"{etiqueta}: sin bobinas de su material")
                    continue
                acciones.append(f"recibe {bobina.coil_id}")
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
            if previa is not None and previa.estado == "completed":
                # El paso anterior ya no entregará más: el supervisor cierra la
                # línea corta (con faltante) para no bloquear el puesto
                cerrar_corto(linea, orden)
            else:
                saltos.append(f"{etiqueta}: esperando piezas del paso anterior")
            continue
        ritmo = ritmos.get(linea.workstation_id)
        if ritmo:
            # Con ritmo nominal: entre el 60 % y el 100 % de lo que el puesto
            # haría en el intervalo del tick (una planta real no va al 100 %)
            esperado = ritmo * Decimal(minutos_tick) / 60
            factor = Decimal(str(round(rng.uniform(0.6, 1.0), 2)))
            piezas = min(max((esperado * factor).quantize(Decimal("1")), Decimal("1")), tope)
            horas = (Decimal(minutos_tick) / 60).quantize(Decimal("0.01"))
        else:
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
            # Bobina agotada: el operario hace "fin de bobina" (radio 0 =
            # no queda nada; lo que el sistema creía que quedaba es merma).
            # Sin ancho (perfiles en metros) no hay fórmula de radio: se
            # desvincula. En el siguiente tick se vincula la siguiente FIFO.
            agotada = "BLOQUEO DE SEGURIDAD" in str(exc) or "Stock insuficiente" in str(exc)
            if agotada and linea.active_coil_id is not None:
                codigo = linea.active_coil_code
                try:
                    create_retal(
                        db, tenant.id, operario.id,
                        stock_item_id=linea.active_coil_id, radio_mm=0,
                        order_id=orden.id, line_id=linea.id,
                    )
                    acciones.append(f"fin de bobina {codigo} en {etiqueta}")
                except ValueError:
                    db.rollback()
                    soltar_bobina(linea, orden, "bobina agotada")
            continue

        # Línea terminada: la bobina queda libre para otra línea (una bobina,
        # un solo sitio)
        db.refresh(linea)
        if linea.estado == "completed" and linea.active_coil_id is not None:
            soltar_bobina(linea, orden, "línea terminada")

    return {"tenant": str(tenant.id), "acciones": acciones, "saltos": saltos}


def _tick_en_sesion(minutos: int) -> dict:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        return simular_tick(db, minutos_tick=minutos)
    finally:
        db.close()


async def bucle_simulador(minutos: int) -> None:
    """Un tick cada `minutos` en horario laboral. Nunca tumba la API."""
    while True:
        await asyncio.sleep(minutos * 60)
        if not en_horario_laboral():
            continue
        try:
            resultado = await asyncio.to_thread(_tick_en_sesion, minutos)
            logger.info(
                "[simulador] %d acciones, %d saltos",
                len(resultado["acciones"]),
                len(resultado["saltos"]),
            )
        except Exception:
            logger.exception("[simulador] tick fallido; se reintenta en el siguiente")


if __name__ == "__main__":
    from app.core.database import engine

    with Session(engine) as sesion:
        resultado = simular_tick(sesion)
    print(f"[simulador] tenant={resultado['tenant']}")
    for accion in resultado["acciones"]:
        print(f"  + {accion}")
    for salto in resultado["saltos"]:
        print(f"  - {salto}")
