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
3. Registra piezas: si el puesto tiene ritmo nominal, entre el 80 % y el 100 %
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

Al despertar la máquina (rellenar_hueco): recupera el hueco desde la última producción
(máx. 7 días y desde el inicio de la semana de producción) repitiendo el tick por
tramos de tiempo simulado, con la hora del registro dentro del tramo. Pasa por los
mismos servicios que un operario, así que stock, kardex y costes cuadran.
"""

import asyncio
import logging
import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Order, OrderLine, ProductionLog, StockItem, User, Workstation
from app.services.seed_planta import operario_de
from app.services.shifts import en_horario_laboral

MINUTOS_POR_PIEZA = Decimal("3")
ORDENES_ACTIVAS_MIN = 5  # suficientes para que la mayoría de los puestos tengan trabajo

# Solo las órdenes de la propia demo (simulador y semillas) las mueve el simulador.
# Una orden creada a mano por un visitante (formulario del supervisor) no lleva estas
# notas y se queda como está: así el operario puede verla y trabajarla (T-095).
MARCAS_ORDEN_DEMO = (
    "Orden generada por el simulador",
    "Orden de demostración",
    "Orden del catalogo",
    "Plantilla de flujo",
)


def _es_orden_de_demo():
    """Condición SQL: la orden es de la demo y no creada a mano."""
    return or_(*(Order.notas.startswith(m) for m in MARCAS_ORDEN_DEMO))

logger = logging.getLogger(__name__)


def _reponer_ordenes(db: Session, tenant_id, rng: random.Random) -> list[str]:
    """Lanza órdenes nuevas copiando completadas hasta tener el mínimo activo."""
    from app.services.sequences import next_sequence

    activas = db.scalars(
        select(Order).where(
            Order.tenant_id == tenant_id, Order.estado == "active", _es_orden_de_demo()
        )
    ).all()
    activos = {
        w.code
        for w in db.scalars(
            select(Workstation).where(
                Workstation.tenant_id == tenant_id, Workstation.is_active.is_(True)
            )
        )
    }
    plantillas = [
        o
        for o in db.scalars(
            select(Order)
            .where(
                Order.tenant_id == tenant_id,
                Order.estado == "completed",
                Order.cliente != "Cliente demo",
                _es_orden_de_demo(),
            )
            .order_by(Order.created_at.asc())
        )
        if o.lines and all(ln.workstation_id in activos for ln in o.lines)
    ]
    ocupados = {
        ln.workstation_id for o in activas for ln in o.lines if ln.estado != "completed"
    }
    acciones = []
    for _ in range(ORDENES_ACTIVAS_MIN - len(activas)):
        if not plantillas:
            break
        # La plantilla que menos puestos ya ocupados pisa (así se reparte el trabajo por la planta)
        pisados = {id(o): sum(ln.workstation_id in ocupados for ln in o.lines) for o in plantillas}
        minimo = min(pisados.values())
        plantilla = rng.choice([o for o in plantillas if pisados[id(o)] == minimo])
        ocupados |= {ln.workstation_id for ln in plantilla.lines}
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
    # Sufijo aleatorio de 32 bits: cientos de reposiciones en el mismo segundo no repiten
    # código (con 16 bits el test de muchos ticks chocaba de vez en cuando)
    marca = f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8].upper()}"
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
    """Inicio (UTC) del turno en curso en horario de planta: A 06:00, B 14:00, C 22:00."""
    from app.services.shifts import TZ_PLANTA

    local = ahora.astimezone(TZ_PLANTA)
    if 6 <= local.hour < 14:
        hora = 6
    elif 14 <= local.hour < 22:
        hora = 14
    else:
        hora = 22
        if local.hour < 6:
            local -= timedelta(days=1)
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


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


CAUSAS_INCIDENCIA = {
    "maquina": [
        "Fallo en el motor de arrastre: salta la protección térmica",
        "Fuga de aceite en el circuito hidráulico",
        "El sensor de final de carrera no responde",
        "Vibración anormal en el cabezal",
    ],
    "material": [
        "Falta de material: la bobina no llega del almacén",
        "Fleje con borde dañado, se aparta para revisión",
    ],
    "otro": [
        "Cambio de utillaje más largo de lo previsto",
        "Ajuste de medidas tras control de calidad",
    ],
}
MINUTOS_INCIDENCIA = (15, 90)


def _duracion_incidencia(incidencia_id) -> int:
    """Minutos que dura una incidencia simulada: estable por id, entre 15 y 90."""
    ini, fin = MINUTOS_INCIDENCIA
    return ini + incidencia_id.int % (fin - ini + 1)


def _gestionar_incidencias(
    db: Session, tenant, operario, lineas, rng: random.Random, minutos_tick: int,
    ahora: datetime, quien=None,
) -> tuple[list[str], set[str]]:
    """Resuelve las incidencias abiertas que ya duraron lo suyo y abre alguna nueva.

    Como mucho una abierta a la vez, siempre sobre un puesto con línea en curso. Devuelve
    lo hecho y los puestos que no producen en este tick (parados o recién arreglados).
    """
    from app.models import Incidencia
    from app.services.incidencias import actualizar_incidencia, crear_incidencia
    from app.services.puestos import ESTADOS_INCIDENCIA_ABIERTA

    quien = quien or (lambda _puesto, _momento: operario)
    acciones: list[str] = []
    recien_resueltas: set[str] = set()
    abiertas = db.scalars(
        select(Incidencia).where(
            Incidencia.tenant_id == tenant.id, Incidencia.estado.in_(ESTADOS_INCIDENCIA_ABIERTA)
        )
    ).all()
    for inc in list(abiertas):
        minutos = (_aware(ahora) - _aware(inc.created_at)).total_seconds() / 60
        if minutos >= _duracion_incidencia(inc.id):
            actualizar_incidencia(
                db, incidencia_id=inc.id, tenant_id=tenant.id, usuario_id=operario.id,
                estado="resuelta", comentario="Resuelta por mantenimiento",
                resolucion_tipo="reparacion",
                resolucion_descripcion="Resuelta en planta (simulador demo).",
                tiempo_parada=Decimal(str(round(minutos))),
            )
            acciones.append(f"resuelve incidencia de {inc.puesto} tras {round(minutos)} min")
            recien_resueltas.add(inc.puesto)
            abiertas.remove(inc)

    if not abiertas:
        en_curso = [ln for ln, _ in lineas if ln.estado == "in_progress" and ln.workstation_id]
        if en_curso and rng.random() < min(0.5, minutos_tick / 120):
            linea = rng.choice(en_curso)
            tipo = rng.choices(list(CAUSAS_INCIDENCIA), weights=(6, 3, 1))[0]
            inc = crear_incidencia(
                db, tenant_id=tenant.id, operario_id=quien(linea.workstation_id, ahora).id,
                linea_id=linea.workstation_id,
                descripcion=rng.choice(CAUSAS_INCIDENCIA[tipo]), tipo=tipo,
            )
            inc.created_at = _aware(ahora).astimezone(UTC)
            db.commit()
            abiertas = [inc]
            acciones.append(f"abre incidencia de {tipo} en {linea.workstation_id}")
    # El puesto recién arreglado retoma la producción en el tick siguiente
    return acciones, {inc.puesto for inc in abiertas} | recien_resueltas


def _momento_en_tramo(
    ahora: datetime | None, minutos_tick: int, rng: random.Random
) -> datetime | None:
    """Hora del registro: None (ahora mismo) o un instante dentro del tramo simulado."""
    if ahora is None:
        return None
    return _aware(ahora).astimezone(UTC) - timedelta(
        seconds=rng.randint(0, max(minutos_tick * 60 - 1, 0))
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

    ahora_tick = _aware(ahora or datetime.now(UTC))
    usuarios_planta: dict = {}

    def quien(puesto: str, momento: datetime) -> User:
        """Operario del puesto en el turno de `momento` (el demo si no tiene plantilla)."""
        return operario_de(usuarios_planta, db, tenant.id, puesto, momento) or operario

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
                db, tenant.id, quien(linea.workstation_id, ahora_tick).id,
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
        .where(Order.tenant_id == tenant.id, Order.estado == "active", _es_orden_de_demo())
        .order_by(Order.created_at.asc(), OrderLine.linea_numero.asc())
    ).all()

    # 1. Arrancar la siguiente línea pendiente en los puestos sin trabajo
    ocupados = {ln.workstation_id for ln, _ in lineas if ln.estado == "in_progress"}
    for linea, orden in lineas:
        previa = next(
            (ln for ln, o in lineas
             if o.id == orden.id and ln.linea_numero == linea.linea_numero - 1),
            None,
        )
        # Un paso arranca cuando le llegan piezas del anterior: un puesto no está "en curso"
        # esperando con el contador a cero
        if previa is not None and not (previa.produced_quantity or 0):
            continue
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
                db, tenant.id, quien(linea.workstation_id, momento).id,
                stock_item_id=bobina.id, radio_mm=radio,
                order_id=orden.id, line_id=linea.id,
                momento=momento + timedelta(seconds=1),
            )
            acciones.append(f"cierre de turno: mide {bobina.coil_id} en {linea.workstation_id}")
        except ValueError as exc:
            db.rollback()
            saltos.append(f"{orden.numero} L{linea.linea_numero}: {exc}")

    acc_inc, parados = _gestionar_incidencias(
        db, tenant, operario, lineas, rng, minutos_tick, ahora_tick, quien
    )
    acciones += acc_inc

    for linea, orden in lineas:
        if linea.estado != "in_progress":
            continue
        etiqueta = f"{orden.numero} L{linea.linea_numero}"
        if linea.workstation_id in parados:
            saltos.append(f"{etiqueta}: puesto parado por incidencia")
            continue
        momento_reg = _momento_en_tramo(ahora, minutos_tick, rng)
        op = quien(linea.workstation_id, momento_reg or ahora_tick)

        # La bobina se acabó de verdad antes de lo que cree el sistema (el
        # desperdicio no se ve hasta medir): fin de bobina con radio 0
        if linea.active_coil_id is not None:
            montada = db.get(StockItem, linea.active_coil_id)
            if montada.width_mm and _real_restante(db, montada) <= 0:
                codigo = montada.coil_id
                try:
                    create_retal(
                        db, tenant.id, op.id,
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
                bobina = _reponer_bobina(db, tenant.id, linea.material_id, op.id)
                if bobina is None:
                    saltos.append(f"{etiqueta}: sin bobinas de su material")
                    continue
                acciones.append(f"recibe {bobina.coil_id}")
            try:
                link_coil(
                    db, tenant.id, op.id,
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
            # Con ritmo nominal: entre el 80 % y el 100 % de lo que el puesto
            # haría en el intervalo del tick (una planta real no va al 100 %)
            esperado = ritmo * Decimal(minutos_tick) / 60
            factor = Decimal(str(round(rng.uniform(0.8, 1.0), 2)))
            objetivo = max((esperado * factor).quantize(Decimal("1")), Decimal("1"))
            piezas = min(objetivo, tope)
            # Si la línea acaba o espera piezas del paso anterior, solo cuenta el tiempo trabajado
            horas = max(
                (Decimal(minutos_tick) / 60 * piezas / objetivo).quantize(Decimal("0.01")),
                Decimal("0.01"),
            )
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
                    db, tenant.id, op.id,
                    order_id=orden.id, line_id=linea.id,
                    incremental_quantity=piezas, hours_worked=horas,
                    observaciones="simulador demo",
                    ocurrido_en=momento_reg,
                )
                acciones.append(f"produce {piezas} uds en {etiqueta}")
                error = None
                break
            except ValueError as exc:
                db.rollback()
                error = exc
                if not (_sin_material(exc) or _bloqueo_kilos(exc)):
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
                        db, tenant.id, op.id,
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
                        db, tenant.id, op.id,
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

    # Las órdenes que se cierran en este tick se reponen ya: la planta nunca se queda corta
    db.commit()
    acciones += _reponer_ordenes(db, tenant.id, rng)
    return {"tenant": str(tenant.id), "acciones": acciones, "saltos": saltos}


def _tick_en_sesion(minutos: int) -> dict:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        return simular_tick(db, minutos_tick=minutos)
    finally:
        db.close()


PASO_RECIENTE_MIN = 15  # tramos de la última jornada de 8 h
PASO_ANTIGUO_MIN = 60  # tramos de turnos más antiguos (menos detalle, menos coste)
HORAS_RECIENTES = 8
MAX_DIAS_RELLENO = 7
MAX_PASOS_RELLENO = 200

_ultimo_relleno: datetime | None = None


def _planta_sin_historia(db: Session, tenant_id) -> bool:
    """True si la planta nueva (seed_planta) existe pero todavía nadie ha producido en ella."""
    from app.services.seed_planta import OPERARIOS

    puestos = db.scalar(
        select(func.count()).select_from(Workstation).where(
            Workstation.tenant_id == tenant_id,
            Workstation.is_active.is_(True),
            Workstation.code.in_(list(OPERARIOS)),
        )
    )
    if not puestos:
        return False
    con_registros = db.scalar(
        select(func.count())
        .select_from(ProductionLog)
        .join(OrderLine, OrderLine.id == ProductionLog.line_id)
        .where(ProductionLog.tenant_id == tenant_id, OrderLine.workstation_id.in_(list(OPERARIOS)))
    )
    return not con_registros


def rellenar_hueco(
    db: Session, ahora: datetime | None = None, rng: random.Random | None = None
) -> dict:
    """Recupera lo que la planta habría producido mientras la máquina dormía.

    Repite simular_tick por tramos de tiempo simulado (15 min en las últimas 8 h,
    60 min antes) desde la última producción registrada (como mucho 7 días y desde
    el inicio de la semana de producción) hasta ahora, solo en horario de planta.
    Cada tramo pasa por los mismos servicios que un operario, con la hora del
    registro dentro del tramo. Idempotente: solo avanza con tramos completos, así que
    una segunda llamada seguida no añade nada; el resto del hueco (menos de un tramo)
    lo cubre el tick normal.
    """
    global _ultimo_relleno
    from app.services.seed_demo import buscar_tenant_demo
    from app.services.shifts import semana_produccion

    rng = rng or random.Random()
    ahora = _aware(ahora or datetime.now(UTC))
    tenant = buscar_tenant_demo(db)
    if tenant is None:
        return {"tenant": None, "pasos": 0, "acciones": [], "saltos": ["sin tenant demo"]}

    desde = max(ahora - timedelta(days=MAX_DIAS_RELLENO), semana_produccion(ahora)[0])
    ultimo = db.scalar(
        select(func.max(ProductionLog.timestamp)).where(
            ProductionLog.tenant_id == tenant.id, ProductionLog.action == "produce"
        )
    )
    if _planta_sin_historia(db, tenant.id):
        # Puestos nuevos aún sin ningún registro: se les da la semana de producción entera
        pass
    else:
        if ultimo is not None:
            desde = max(desde, _aware(ultimo))
        if _ultimo_relleno is not None:
            desde = max(desde, _ultimo_relleno)

    pasos = 0
    acciones: list[str] = []
    saltos: list[str] = []
    t = desde
    while pasos < MAX_PASOS_RELLENO:
        paso = (
            PASO_RECIENTE_MIN
            if ahora - t <= timedelta(hours=HORAS_RECIENTES)
            else PASO_ANTIGUO_MIN
        )
        fin = t + timedelta(minutes=paso)
        if fin > ahora:
            break
        if en_horario_laboral(fin - timedelta(seconds=1)):
            resultado = simular_tick(db, rng, minutos_tick=paso, ahora=fin)
            acciones += resultado["acciones"]
            saltos += resultado["saltos"]
            pasos += 1
        t = fin
    _ultimo_relleno = t
    return {"tenant": str(tenant.id), "pasos": pasos, "acciones": acciones, "saltos": saltos}


def _relleno_en_sesion() -> dict:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        return rellenar_hueco(db)
    finally:
        db.close()


async def bucle_simulador(minutos: int) -> None:
    """Relleno al despertar y un tick cada `minutos` en horario laboral. Nunca tumba la API."""
    while True:
        try:
            relleno = await asyncio.to_thread(_relleno_en_sesion)
            if relleno["pasos"]:
                logger.info("[simulador] relleno: %d tramos recuperados", relleno["pasos"])
        except Exception:
            logger.exception("[simulador] relleno fallido; se reintenta en el siguiente ciclo")
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
