"""Ficha de trazabilidad de una orden (T-045).

Une en una sola respuesta lo que hoy está repartido: el registro inmutable de
producción (ProductionLog), las vinculaciones y altas de bobina, las paradas,
las incidencias y la creación de la orden. Devuelve:

- ``resumen``: piezas, merma, kilos por bobina, personas y paradas.
- ``linea_tiempo``: eventos de más reciente a más antiguo, cada uno con su
  categoría (produccion, calidad, bobina, parada, incidencia, estado) para poder
  filtrar en pantalla.

Solo lectura. Todo se filtra por ``tenant_id``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Incidencia,
    MaterialConsumo,
    MaterialTransaction,
    Order,
    OrderLine,
    Parada,
    ProductionLog,
    StockItem,
    User,
)

CATEGORIAS = ("produccion", "calidad", "bobina", "parada", "incidencia", "estado")

_TITULOS_ACCION = {
    "start": "Inicio de línea",
    "pause": "Pausa",
    "resume": "Reanudación",
    "finish": "Línea terminada",
    "stopped": "Parada",
    "setup_start": "Inicio de preparación",
    "setup_finish": "Fin de preparación",
    "close_shift": "Cierre de turno",
}

_MOTIVOS_MERMA = {
    "fin_bobina": "fin de bobina",
    "cierre_turno": "cierre de turno",
}


def _num(valor) -> float:
    return float(valor) if valor is not None else 0.0


def _aware(ts: datetime | None) -> datetime | None:
    if ts is None:
        return None
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


def _fmt(valor: float, decimales: int = 1) -> str:
    texto = f"{valor:.{decimales}f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto


def _evento(
    id_: str,
    ts: datetime,
    categoria: str,
    titulo: str,
    detalle: str = "",
    quien: str | None = None,
    cantidad: float | None = None,
    unidad: str | None = None,
) -> dict:
    return {
        "id": id_,
        "timestamp": _aware(ts).isoformat(),
        "categoria": categoria,
        "titulo": titulo,
        "detalle": detalle,
        "quien": quien,
        "cantidad": cantidad,
        "unidad": unidad,
    }


def _evento_de_log(log: ProductionLog) -> dict:
    meta = dict(log.metadata_ or {})
    quien = log.operator.name if log.operator is not None else None
    cantidad = _num(log.quantity)
    bobina = meta.get("activeCoilCode")
    razon = meta.get("reason")
    detalle: list[str] = []

    if log.action == "produce":
        if bobina:
            detalle.append(f"bobina {bobina}")
        if meta.get("consumedAmount"):
            detalle.append(f"{_fmt(_num(meta['consumedAmount']), 2)} kg consumidos")
        if meta.get("efficiency") is not None:
            detalle.append(f"{_fmt(_num(meta['efficiency']), 1)} uds/h")
        if meta.get("observaciones"):
            detalle.append(str(meta["observaciones"]))
        return _evento(
            f"log-{log.id}", log.timestamp, "produccion", "Producción", " · ".join(detalle),
            quien, cantidad, "uds",
        )

    if log.action == "scrap":
        if razon in _MOTIVOS_MERMA:
            base = f"Merma de bobina {bobina}" if bobina else "Merma de bobina"
            detalle.append(_MOTIVOS_MERMA[razon])
            if meta.get("merma_cost") is not None:
                detalle.append(f"{_fmt(_num(meta['merma_cost']), 2)} €")
            return _evento(
                f"log-{log.id}", log.timestamp, "bobina", base, " · ".join(detalle),
                quien, cantidad, "kg",
            )
        return _evento(
            f"log-{log.id}", log.timestamp, "produccion", "Chatarra", "", quien, cantidad, "kg"
        )

    if log.action == "finish" and razon == "retirar_pico":
        titulo = f"Pico retirado de la bobina {bobina}" if bobina else "Pico retirado"
        return _evento(
            f"log-{log.id}", log.timestamp, "bobina", titulo,
            "devuelto a Retales", quien, cantidad, "kg",
        )

    if log.action == "quality_check":
        estado = meta.get("status")
        if meta.get("manufacturingModel"):
            detalle.append(str(meta["manufacturingModel"]))
        if meta.get("measurementsCount") is not None:
            detalle.append(f"{meta['measurementsCount']} mediciones")
        titulo = "Autocontrol de calidad" + (f": {estado}" if estado else "")
        return _evento(
            f"log-{log.id}", log.timestamp, "calidad", titulo, " · ".join(detalle), quien
        )

    titulo = _TITULOS_ACCION.get(log.action, log.action)
    if meta.get("reason"):
        detalle.append(f"motivo: {meta['reason']}")
    return _evento(f"log-{log.id}", log.timestamp, "estado", titulo, " · ".join(detalle), quien)


def ficha_orden(db: Session, tenant_id, order_id) -> dict | None:
    """Ficha completa de la orden, o None si no existe o es de otro tenant."""
    orden = db.get(Order, order_id)
    if orden is None or orden.tenant_id != tenant_id:
        return None

    lineas = list(
        db.scalars(
            select(OrderLine).where(OrderLine.order_id == orden.id).order_by(OrderLine.linea_numero)
        ).all()
    )
    logs = list(
        db.scalars(
            select(ProductionLog)
            .where(ProductionLog.tenant_id == tenant_id, ProductionLog.order_id == orden.id)
            .options(joinedload(ProductionLog.operator))
        ).all()
    )
    consumos = list(
        db.scalars(
            select(MaterialConsumo).where(
                MaterialConsumo.tenant_id == tenant_id, MaterialConsumo.order_id == orden.id
            )
        ).all()
    )
    paradas = list(
        db.scalars(
            select(Parada).where(Parada.tenant_id == tenant_id, Parada.order_id == orden.id)
        ).all()
    )
    incidencias = list(
        db.scalars(
            select(Incidencia).where(
                Incidencia.tenant_id == tenant_id, Incidencia.order_id == orden.id
            )
        ).all()
    )
    # Vinculación de bobinas: queda en el kardex (MaterialTransaction), que es lo que
    # escribe siempre el flujo de planta al vincular.
    vinculos = list(
        db.scalars(
            select(MaterialTransaction).where(
                MaterialTransaction.tenant_id == tenant_id,
                MaterialTransaction.orden_id == orden.id,
                MaterialTransaction.tipo == "salida_produccion",
                MaterialTransaction.motivo.contains("Bobina vinculada"),
            )
        ).all()
    )

    ids_usuarios = (
        {p.operario_id for p in paradas}
        | {i.operario_id for i in incidencias}
        | {v.realizado_por for v in vinculos if v.realizado_por}
    )
    nombres = {
        u.id: u.name
        for u in db.scalars(select(User).where(User.id.in_(ids_usuarios))).all()
    } if ids_usuarios else {}

    # Bobinas implicadas: las que consumieron material y las vinculadas
    ids_bobinas = {c.stock_item_id for c in consumos if c.stock_item_id} | {
        v.stock_item_id for v in vinculos
    }
    bobinas = {
        b.id: b
        for b in db.scalars(select(StockItem).where(StockItem.id.in_(ids_bobinas))).all()
        if b.tenant_id == tenant_id
    } if ids_bobinas else {}
    ids_creadores = {b.creada_por_user_id for b in bobinas.values() if b.creada_por_user_id} | {
        b.verificada_por_user_id for b in bobinas.values() if b.verificada_por_user_id
    }
    ids_creadores -= set(nombres)
    if ids_creadores:
        nombres.update(
            {u.id: u.name for u in db.scalars(select(User).where(User.id.in_(ids_creadores))).all()}
        )

    # ---------------- Resumen ----------------
    ultima = lineas[-1] if lineas else None
    piezas_producidas = _num(ultima.produced_quantity) if ultima else 0.0
    piezas_objetivo = _num(ultima.total_quantity) if ultima else 0.0

    merma_kg = sum(_num(lg.quantity) for lg in logs if lg.action == "scrap")

    kg_por_bobina: dict = defaultdict(lambda: {"kg": 0.0, "lote": None, "coil_id": None})
    for c in consumos:
        if c.unit != "kg":
            continue
        clave = c.stock_item_id or f"sin-bobina-{c.lote}"
        fila = kg_por_bobina[clave]
        fila["kg"] += _num(c.consumed_quantity)
        fila["lote"] = c.lote
        fila["stock_item_id"] = str(c.stock_item_id) if c.stock_item_id else None
    por_bobina = []
    for clave, fila in kg_por_bobina.items():
        b = bobinas.get(clave) if not isinstance(clave, str) else None
        por_bobina.append(
            {
                "stock_item_id": fila.get("stock_item_id"),
                "coil_id": b.coil_id if b else None,
                "lote": b.lote if b else fila["lote"],
                "kg": round(fila["kg"], 2),
                "origen": b.origen if b else None,
                "pendiente_verificacion": bool(b.pendiente_verificacion) if b else False,
            }
        )
    por_bobina.sort(key=lambda f: -f["kg"])

    personas_map: dict = {}
    for lg in logs:
        if lg.operator is None:
            continue
        p = personas_map.setdefault(
            lg.operator.id, {"id": str(lg.operator.id), "nombre": lg.operator.name,
                             "eventos": 0, "piezas": 0.0}
        )
        p["eventos"] += 1
        if lg.action == "produce":
            p["piezas"] += _num(lg.quantity)
    personas = sorted(personas_map.values(), key=lambda p: -p["eventos"])

    ahora = datetime.now(UTC)
    paradas_cerradas_min = 0.0
    paradas_abiertas = 0
    for p in paradas:
        if p.fin is not None:
            paradas_cerradas_min += max((_aware(p.fin) - _aware(p.inicio)).total_seconds(), 0) / 60
        else:
            paradas_abiertas += 1

    eficiencias = [
        float(m["efficiency"])
        for m in (dict(lg.metadata_ or {}) for lg in logs if lg.action == "produce")
        if m.get("efficiency") is not None
    ]

    resumen = {
        "numero": orden.numero,
        "estado": orden.estado,
        "cliente": orden.cliente,
        "piezas_producidas": round(piezas_producidas, 2),
        "piezas_objetivo": round(piezas_objetivo, 2),
        "merma_kg": round(merma_kg, 2),
        "kg_consumidos": round(sum(f["kg"] for f in por_bobina), 2),
        "kg_por_bobina": por_bobina,
        "personas": personas,
        "paradas_minutos": round(paradas_cerradas_min, 1),
        "paradas_abiertas": paradas_abiertas,
        "incidencias": len(incidencias),
        "eficiencia_media_uds_h": round(sum(eficiencias) / len(eficiencias), 1)
        if eficiencias
        else None,
        "lineas": [
            {
                "numero": ln.linea_numero,
                "puesto": ln.workstation_id,
                "estado": ln.estado,
                "producidas": _num(ln.produced_quantity),
                "total": _num(ln.total_quantity),
            }
            for ln in lineas
        ],
        "generada_en": ahora.isoformat(),
    }

    # ---------------- Línea de tiempo ----------------
    eventos: list[dict] = [_evento_de_log(lg) for lg in logs]

    eventos.append(
        _evento(
            f"orden-{orden.id}", orden.created_at, "estado", "Orden creada",
            f"cliente {orden.cliente}" if orden.cliente else "",
        )
    )

    for v in vinculos:
        b = bobinas.get(v.stock_item_id)
        codigo = b.coil_id if b else "?"
        eventos.append(
            _evento(
                f"vinculo-{v.id}", v.created_at, "bobina", f"Bobina {codigo} vinculada",
                f"carga de {_fmt(_num(v.cantidad), 1)} kg a la orden",
                nombres.get(v.realizado_por),
            )
        )

    for b in bobinas.values():
        if b.origen == "alta_manual":
            quien = nombres.get(b.creada_por_user_id)
            donde = b.alta_ubicacion or "ubicación sin indicar"
            estado = "pendiente de verificar" if b.pendiente_verificacion else "verificada"
            eventos.append(
                _evento(
                    f"alta-{b.id}", b.created_at, "bobina",
                    f"Bobina {b.coil_id} dada de alta a mano",
                    f"en {donde} · {estado}", quien, _num(b.cantidad_inicial), "kg",
                )
            )
        if b.verificada_en is not None:
            eventos.append(
                _evento(
                    f"verif-{b.id}", b.verificada_en, "bobina",
                    f"Bobina {b.coil_id} verificada", "", nombres.get(b.verificada_por_user_id),
                )
            )

    for p in paradas:
        quien = nombres.get(p.operario_id)
        detalle = [f"motivo: {p.motivo}"]
        if p.nota:
            detalle.append(p.nota)
        if p.fin is not None:
            minutos = max((_aware(p.fin) - _aware(p.inicio)).total_seconds(), 0) / 60
            detalle.append(f"duró {_fmt(minutos, 0)} min")
        else:
            detalle.append("sigue abierta")
        eventos.append(
            _evento(f"parada-{p.id}", p.inicio, "parada", f"Parada en {p.puesto}",
                    " · ".join(detalle), quien)
        )

    for i in incidencias:
        detalle = [i.descripcion]
        if i.estado:
            detalle.append(f"estado: {i.estado}")
        eventos.append(
            _evento(f"inc-{i.id}", i.created_at, "incidencia", f"Incidencia ({i.tipo})",
                    " · ".join(detalle), nombres.get(i.operario_id))
        )

    eventos.sort(key=lambda e: e["timestamp"], reverse=True)
    return {"resumen": resumen, "linea_tiempo": eventos, "categorias": list(CATEGORIAS)}

