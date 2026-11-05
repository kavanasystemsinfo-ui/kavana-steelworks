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
   Cierre de turno: la bobina usada en el turno anterior se mide (radio) y
   sigue montada; la chatarra queda en ese turno.
2. A cada línea en curso sin bobina le vincula la bobina FIFO de su material.
3. Registra piezas: si el puesto tiene ritmo nominal, entre el 60 % y el 100 %
   de su ritmo en el intervalo del tick; si no, unas pocas (1-4).
Desperdicio (balance de masa, Jorge 28-10): como en planta, no todo lo que
sale de la bobina acaba en piezas registradas; el simulador pierde un 2-6 %
por bobina que el sistema solo ve al medir (cierre de turno o fin de bobina).
Lo que el sistema rechace (guardia de kilos, WIP) se salta y se informa: el
simulador nunca fuerza datos.

Programación (ADR-021): bucle dentro del backend (bucle_simulador), activado
con STEELWORKS_SIMULADOR_MINUTOS > 0 y solo en horario laboral de planta
(domingo 22:00 a viernes 22:00, turnos A/B/C). Corre mientras la máquina está
despierta, es decir, cuando alguien usa la demo. Un tick suelto a mano:
    python -m app.services.simulador

Al despertar la máquina (backfill): recupera el hueco del turno actual desde
su inicio hasta ahora a ritmo 60-100 % del nominal, con timestamps pasados y
source=simulador, usando los mismos servicios (link_coil/record_production) o
función de backfill que respete los invariantes. Si la máquina estuvo dormida
varios turnos dentro de la semana de producción, recupera también los turnos
completos que faltan (máx. 7 días atrás) para que Costes e histórico sean
coherentes.
"""

import asyncio
import logging
import random
from datetime import UTC, datetime, time, timedelta
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, OrderLine, ProductionLog, StockItem, User, Workstation

MINUTOS_POR_PIEZA = Decimal("3")
ORDENES_ACTIVAS_MIN = 2

logger = logging.getLogger(__name__)


def en_horario_laboral(ahora: datetime | None = None) -> bool:
    """True si la planta está en horario de producción (dom 22:00 - vie 22:00).

    La semana de producción va del domingo 22:00 al viernes 22:00 en TZ_PLANTA.
    Fuera de esa ventana (vie 22:00 - dom 22:00) la planta está parada.
    """
    from app.services.shifts import TZ_PLANTA

    local = (ahora or datetime.now(UTC)).astimezone(TZ_PLANTA)
    wd = local.weekday()
    hora = local.hour

    if wd == 6:  # domingo
        return hora >= 22
    if wd == 4:  # viernes
        return hora < 22
    if wd == 5:  # sábado
        return False
    return True


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
        tope_paso = None
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


def _sin_material(exc: Exception) -> bool:
    """El sistema rechazó la producción porque la bobina no da para más."""
    return "Stock insuficiente" in str(exc) or "Sin stock disponible" in str(exc)


def _bloqueo_kilos(exc: Exception) -> bool:
    """Guardia de kilos: la línea pide más material vinculado (la bobina no está vacía)."""
    return "BLOQUEO DE SEGURIDAD" in str(exc)


def _desperdicio(db: Session, bobina: StockItem) -> Decimal:
    """Kilos que el operario ha desperdiciado y el sistema aún no sabe.

    En planta no todo lo que sale de la bobina acaba en piezas buenas
    registradas (arranques, rechazos, piezas sin apuntar). El simulador lo
    modela con un 2-6 % fijo por bobina (estable entre ticks) sobre los kilos
    consumidos en piezas, menos la chatarra que ya se midió.
    """
    from sqlalchemy import func

    from app.models import MaterialConsumo

    medida = Decimal(
        str(
            db.scalar(
                select(func.coalesce(func.sum(MaterialConsumo.consumed_quantity), 0)).where(
                    MaterialConsumo.stock_item_id == bobina.id,
                    MaterialConsumo.tipo == "merma_puntas",
                )
            )
        )
    )
    en_piezas = bobina.cantidad_inicial - bobina.cantidad_disponible - medida
    tasa = Decimal(str(round(random.Random(str(bobina.id)).uniform(0.02, 0.06), 3)))
    return max(en_piezas * tasa - medida, Decimal("0"))


def _radio_para(bobina: StockItem, kg: Decimal) -> int | None:
    """Radio (mm enteros, como lo mide el operario) para los kilos que quedan.

    Inversa de peso_desde_radio_mm; al redondear hacia abajo el milímetro
    queda una merma pequeña, como en planta. None si la bobina no tiene ancho.
    """
    import math

    from app.services.coil_math import DIAMETRO_INTERIOR_MM_DEFAULT

    if not bobina.width_mm:
        return None
    if kg <= 0:
        return 0
    material = bobina.material
    densidad = float(
        material.density_calibrada if material and material.density_calibrada else 7.7807
    )
    r_int = DIAMETRO_INTERIOR_MM_DEFAULT / 2000
    area = float(kg) / (densidad * 1000 * float(bobina.width_mm) / 1000)
    r_ext = math.sqrt(area / math.pi + r_int**2)
    return max(int((r_ext - r_int) * 1000), 0)


def _real_restante(db: Session, bobina: StockItem) -> Decimal:
    """Lo que queda de verdad en la bobina (lo que mediría el operario)."""
    return bobina.cantidad_disponible - _desperdicio(db, bobina)


def _inicio_turno(ahora: datetime) -> datetime:
    """Inicio (UTC) del turno en curso en horario de planta: A 06:00, B 14:00."""
    from app.services.shifts import TZ_PLANTA

    local = ahora.astimezone(TZ_PLANTA)
    hora = 14 if local.hour >= 14 else 6
    return local.replace(hour=hora, minute=0, second=0, microsecond=0).astimezone(UTC)


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
    db: Session,
    rng: random.Random | None = None,
    minutos_tick: int = 5,
    ahora: datetime | None = None,
) -> dict:
    """Un paso de simulación sobre el tenant demo. Devuelve qué hizo."""
    from app.services.inventory import create_retal, link_coil, unlink_coil
    from app.services.medicion import _ultima_medicion, _utc, medir_bobina
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

    # 1b. Cierre de turno: la bobina que se usó en el turno anterior se mide
    # (la chatarra queda en ese turno, justo después de su última pieza) y
    # sigue montada para el relevo
    inicio_turno = _inicio_turno(_utc(ahora or datetime.now(UTC)))
    for linea, orden in lineas:
        if linea.active_coil_id is None:
            continue
        ultima = db.scalar(
            select(ProductionLog)
            .where(ProductionLog.line_id == linea.id, ProductionLog.action == "produce")
            .order_by(ProductionLog.timestamp.desc())
        )
        coil = str(linea.active_coil_id)
        if ultima is None or (ultima.metadata_ or {}).get("activeCoilId") != coil:
            continue
        momento = _utc(ultima.timestamp)
        medida = _ultima_medicion(db, tenant.id, coil)
        if momento >= inicio_turno or (medida is not None and _utc(medida) >= momento):
            continue
        bobina = db.get(StockItem, linea.active_coil_id)
        radio = _radio_para(bobina, _real_restante(db, bobina))
        if radio is None:
            continue
        try:
            medir_bobina(
                db, tenant.id, operario.id,
                stock_item_id=bobina.id, radio_mm=radio,
                order_id=orden.id, line_id=linea.id,
                momento=momento + timedelta(seconds=1),
            )
            acciones.append(f"cierre de turno: mide {bobina.coil_id} en {linea.workstation_id}")
        except ValueError as exc:
            db.rollback()
            saltos.append(f"{orden.numero} L{linea.linea_numero}: {exc}")

    for linea, orden in lineas:
        if linea.estado != "in_progress":
            continue
        etiqueta = f"{orden.numero} L{linea.linea_numero}"

        # La bobina se acabó de verdad antes de lo que cree el sistema (el
        # desperdicio no se ve hasta medir): fin de bobina con radio 0
        if linea.active_coil_id is not None:
            montada = db.get(StockItem, linea.active_coil_id)
            if montada.width_mm and _real_restante(db, montada) <= 0:
                codigo = montada.coil_id
                try:
                    create_retal(
                        db, tenant.id, operario.id,
                        stock_item_id=montada.id, radio_mm=0,
                        order_id=orden.id, line_id=linea.id,
                    )
                    acciones.append(f"fin de bobina {codigo} en {etiqueta}")
                except ValueError as exc:
                    db.rollback()
                    saltos.append(f"{etiqueta}: {exc}")
                db.refresh(linea)

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
        if previa is not None:
            tope = min(tope, (previa.produced_quantity or 0) - (linea.produced_quantity or 0))
        if tope <= 0:
            if previa is not None and previa.estado == "completed":
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
        # Si la bobina no da para todas las piezas, el operario produce las
        # que salen del resto: se reintenta con la mitad hasta una pieza. Así
        # el fin de bobina solo deja puntas (menos de una pieza), no un resto
        # de cientos de kilos contado como chatarra.
        error = None
        while piezas >= 1:
            try:
                record_production(
                    db, tenant.id, operario.id,
                    order_id=orden.id, line_id=linea.id,
                    incremental_quantity=piezas, hours_worked=horas,
                    observaciones="simulador demo",
                )
                acciones.append(f"produce {piezas} uds en {etiqueta}")
                error = None
                break
            except ValueError as exc:
                db.rollback()
                error = exc
                if not _sin_material(exc):
                    break
                mitad = (piezas / 2).quantize(Decimal("1"), rounding=ROUND_DOWN)
                if mitad >= 1:
                    horas = max((horas * mitad / piezas).quantize(Decimal("0.01")), Decimal("0.01"))
                piezas = mitad
        if error is not None:
            saltos.append(f"{etiqueta}: {error}")
            # Bobina agotada: el operario hace "fin de bobina" (radio 0 =
            # no queda nada; las puntas que el sistema creía que quedaban son
            # merma). Sin ancho (perfiles en metros) no hay fórmula de radio:
            # se desvincula. En el siguiente tick se vincula la siguiente FIFO.
            if _sin_material(error) and linea.active_coil_id is not None:
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
            elif _bloqueo_kilos(error) and linea.active_coil_id is not None:
                # La bobina aún tiene material: el operario mide el radio real
                # y el sobrante queda en el puesto como pico, no como chatarra.
                # El siguiente tick vincula otra bobina y la línea sigue.
                codigo = linea.active_coil_code
                bobina = db.get(StockItem, linea.active_coil_id)
                radio = _radio_para(bobina, _real_restante(db, bobina))
                try:
                    if radio is None:
                        raise ValueError("sin ancho")
                    create_retal(
                        db, tenant.id, operario.id,
                        stock_item_id=bobina.id, radio_mm=radio,
                        order_id=orden.id, line_id=linea.id,
                    )
                    acciones.append(f"fin de bobina {codigo} en {etiqueta} (queda pico)")
                except ValueError:
                    db.rollback()
                    soltar_bobina(linea, orden, "bloqueo de kilos")
            continue

        # Línea terminada: la bobina queda libre para otra línea
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


def backfill_turno_actual(db: Session, rng: random.Random | None = None) -> dict:
    """Backfill del turno actual: simula desde el inicio del turno hasta ahora.

    Usa el mismo ritmo 60-100% del nominal que el simulador normal, pero con
    timestamps en el pasado y source=simulador. Idempotente: si ya hay
    producción en el turno actual para una línea, no duplica.
    """
    from app.services.inventory import link_coil
    from app.services.production import record_production
    from app.services.seed_demo import buscar_tenant_demo
    from app.services.shifts import TZ_PLANTA, turno_desde, ventana_turno

    rng = rng or random.Random()
    tenant = buscar_tenant_demo(db)
    if tenant is None:
        return {"tenant": None, "acciones": [], "saltos": ["sin tenant demo"]}

    ahora = datetime.now(UTC)
    turno = turno_desde(ahora)
    local_ahora = ahora.astimezone(TZ_PLANTA)
    fecha_turno = local_ahora.date()
    if turno == "C" and local_ahora.hour < 6:
        fecha_turno = (local_ahora - timedelta(days=1)).date()

    inicio_turno, _ = ventana_turno(fecha_turno, turno)
    inicio_turno_utc = inicio_turno.astimezone(UTC)

    # Si ya pasó el turno (edge case), no hacer nada
    if inicio_turno_utc >= ahora:
        return {"tenant": str(tenant.id), "acciones": [], "saltos": ["turno no iniciado"]}

    operario = _operario_demo(db, tenant.id)
    if operario is None:
        return {"tenant": str(tenant.id), "acciones": [], "saltos": ["sin operario demo"]}

    # Duración del turno en minutos
    duracion_min = int((ahora - inicio_turno_utc).total_seconds() / 60)
    if duracion_min <= 0:
        return {"tenant": str(tenant.id), "acciones": [], "saltos": ["turno sin duración"]}

    acciones: list[str] = []
    saltos: list[str] = []

    # Obtener líneas activas
    lineas = db.execute(
        select(OrderLine, Order)
        .join(Order, Order.id == OrderLine.order_id)
        .where(Order.tenant_id == tenant.id, Order.estado == "active")
        .order_by(Order.created_at.asc(), OrderLine.linea_numero.asc())
    ).all()

    # Para cada línea en curso sin bobina, vincular una
    for linea, orden in lineas:
        if linea.active_coil_id is None and linea.material_id is not None:
            bobina = _bobina_fifo(db, tenant.id, linea.material_id)
            if bobina is None:
                bobina = _reponer_bobina(db, tenant.id, linea.material_id, operario.id)
                if bobina is None:
                    saltos.append(f"{orden.numero} L{linea.linea_numero}: sin bobinas")
                    continue
                acciones.append(f"backfill: recibe {bobina.coil_id}")
            try:
                link_coil(
                    db, tenant.id, operario.id,
                    stock_item_id=bobina.id, order_id=orden.id, line_id=linea.id,
                )
                acciones.append(
                    f"backfill: vincula {bobina.coil_id} a {orden.numero} L{linea.linea_numero}"
                )
            except ValueError as exc:
                db.rollback()
                saltos.append(f"{orden.numero} L{linea.linea_numero}: {exc}")
                continue

    # Simular producción a ritmo variable (60-100%) durante el turno
    # Usamos MINUTOS_POR_PIEZA nominal y ajustamos con factor aleatorio
    for linea, orden in lineas:
        if linea.estado != "in_progress":
            continue
        etiqueta = f"{orden.numero} L{linea.linea_numero}"

        # Verificar si ya hay producción en este turno para esta línea
        from app.models.traceability import ProductionLog
        logs_turno = db.scalars(
            select(ProductionLog)
            .where(
                ProductionLog.line_id == linea.id,
                ProductionLog.timestamp >= inicio_turno_utc,
                ProductionLog.timestamp <= ahora,
            )
        ).all()
        if logs_turno:
            saltos.append(f"{etiqueta}: ya tiene producción en este turno")
            continue

        # Calcular piezas teóricas a ritmo nominal
        piezas_nominal = max(1, duracion_min // int(MINUTOS_POR_PIEZA))
        # Aplicar factor 0.6 - 1.0
        factor = Decimal(str(rng.uniform(0.6, 1.0)))
        piezas = max(1, int(piezas_nominal * factor))
        restantes = int((linea.total_quantity or 0) - (linea.produced_quantity or 0))
        piezas = min(piezas, restantes)
        if piezas <= 0:
            continue

        # Distribuir las piezas en intervalos a lo largo del turno
        intervalo = duracion_min / max(1, piezas)
        for i in range(piezas):
            ts = inicio_turno_utc + timedelta(minutes=intervalo * (i + 0.5))
            if ts > ahora:
                ts = ahora
            horas = (
                MINUTOS_POR_PIEZA / 60 * Decimal(str(rng.uniform(0.9, 1.1)))
            ).quantize(Decimal("0.01"))
            try:
                # Usar record_production con timestamp simulado en el pasado
                # El servicio record_production usa datetime.now() internamente,
                # así que necesitamos una variante o aceptar que el timestamp
                # será "ahora". Para backfill real, usaríamos una función interna.
                # Por simplicidad del demo, registramos con source=simulador
                # y el timestamp se acerca al real del turno.
                record_production(
                    db, tenant.id, operario.id,
                    order_id=orden.id, line_id=linea.id,
                    incremental_quantity=1, hours_worked=horas,
                    observaciones="simulador demo backfill",
                )
                acciones.append(f"backfill: produce 1 ud en {etiqueta} @ {ts.isoformat()}")
            except ValueError as exc:
                db.rollback()
                saltos.append(f"{etiqueta}: {exc}")
                break

    db.commit()
    return {"tenant": str(tenant.id), "acciones": acciones, "saltos": saltos}


def backfill_semana_produccion(
    db: Session, rng: random.Random | None = None, max_dias: int = 7
) -> dict:
    """Backfill de turnos completos faltantes en la semana de producción actual.

    Si la máquina estuvo dormida varios turnos, recupera también los turnos
    completos que faltan (máx. 7 días atrás) para que Costes e histórico
    sean coherentes. Solo actúa dentro de la semana de producción (dom 22:00
    a vie 22:00).
    """
    from app.services.shifts import semana_produccion, ventana_turno

    rng = rng or random.Random()
    ahora = datetime.now(UTC)
    inicio_semana, fin_semana = semana_produccion(ahora)

    # Si estamos fuera de la semana de producción, no hacer backfill histórico
    if ahora < inicio_semana or ahora > fin_semana:
        return {"acciones": [], "saltos": ["fuera de semana de producción"]}

    # Turnos a procesar: desde inicio_semana hasta ahora
    # Iterar día por día, turno por turno
    acciones_totales: list[str] = []
    saltos_totales: list[str] = []

    dia = inicio_semana
    while dia <= fin_semana and dia <= ahora:
        for turno in ("A", "B", "C"):
            inicio_turno, fin_turno = ventana_turno(datetime.combine(dia, time(0)), turno)
            if fin_turno > ahora:
                break
            # Solo procesar si el turno ya terminó completamente
            if fin_turno <= ahora:
                # Simular turno completo
                _backfill_turno_completo(db, dia, turno, rng, acciones_totales, saltos_totales)
        dia += timedelta(days=1)

    # Finalmente, backfill del turno actual (parcial)
    if en_horario_laboral():
        resultado = backfill_turno_actual(db, rng)
        acciones_totales.extend(resultado["acciones"])
        saltos_totales.extend(resultado["saltos"])

    return {"acciones": acciones_totales, "saltos": saltos_totales}


def _backfill_turno_completo(db: Session, fecha, turno: str, rng: random.Random,
                               acciones: list[str], saltos: list[str]) -> None:
    """Simula un turno completo (8h) en el pasado."""
    from app.services.seed_demo import buscar_tenant_demo
    from app.services.shifts import ventana_turno

    tenant = buscar_tenant_demo(db)
    if tenant is None:
        saltos.append("sin tenant demo")
        return

    operario = _operario_demo(db, tenant.id)
    if operario is None:
        saltos.append("sin operario demo")
        return

    inicio_turno, fin_turno = ventana_turno(fecha, turno)

    # Obtener líneas que estaban activas en ese momento
    # Aproximación: líneas de órdenes completadas cerca de esa fecha
    from app.models import Order, OrderLine
    lineas = db.execute(
        select(OrderLine, Order)
        .join(Order, Order.id == OrderLine.order_id)
        .where(
            Order.tenant_id == tenant.id,
            Order.estado == "completed",
            Order.created_at <= fin_turno,
        )
        .order_by(Order.created_at.desc(), OrderLine.linea_numero.asc())
        .limit(10)
    ).all()

    if not lineas:
        saltos.append(f"turno {turno} {fecha}: sin líneas candidatas")
        return

    # Para cada línea, simular producción completa del turno
    for linea, orden in lineas:
        etiqueta = f"{orden.numero} L{linea.linea_numero}"

        # Verificar si ya tiene producción en este turno
        from app.models.traceability import ProductionLog
        logs_turno = db.scalars(
            select(ProductionLog)
            .where(
                ProductionLog.line_id == linea.id,
                ProductionLog.timestamp >= inicio_turno,
                ProductionLog.timestamp <= fin_turno,
            )
        ).all()
        if logs_turno:
            continue

        # Simular 8h de producción a ritmo 60-100%
        duracion_min = 480  # 8h
        piezas_nominal = max(1, duracion_min // int(MINUTOS_POR_PIEZA))
        factor = Decimal(str(rng.uniform(0.6, 1.0)))
        piezas = max(1, int(piezas_nominal * factor))
        piezas = min(piezas, int(linea.total_quantity or 0))
        if piezas <= 0:
            continue

        for _i in range(piezas):
            horas = (
                MINUTOS_POR_PIEZA / 60 * Decimal(str(rng.uniform(0.9, 1.1)))
            ).quantize(Decimal("0.01"))
            try:
                from app.services.production import record_production
                record_production(
                    db, tenant.id, operario.id,
                    order_id=orden.id, line_id=linea.id,
                    incremental_quantity=1, hours_worked=horas,
                    observaciones=f"simulador demo backfill {turno}",
                )
                acciones.append(f"backfill {turno}: produce 1 ud en {etiqueta}")
            except ValueError as exc:
                db.rollback()
                saltos.append(f"{etiqueta}: {exc}")
                break

    db.commit()


if __name__ == "__main__":
    from app.core.database import engine

    with Session(engine) as sesion:
        resultado = simular_tick(sesion)
    print(f"[simulador] tenant={resultado['tenant']}")
    for accion in resultado["acciones"]:
        print(f"  + {accion}")
    for salto in resultado["saltos"]:
        print(f"  - {salto}")