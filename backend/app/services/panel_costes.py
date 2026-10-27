"""Panel de mando · vista Costes: agregación del periodo.

Une piezas que ya existen (``costes.py``, ``shifts.py`` e incidencias) en el
contrato que consumen el endpoint ``GET /supervisor/panel/costes`` y la vista
``VistaCostes`` del frontend. No crea tablas, no duplica contadores y no
inventa cifras: sin datos, los bloques salen a 0 (o ``None`` donde el contrato
lo permite, como el objetivo).

Decisiones de esta capa (no re-decidir sin migración):

- **Ventana natural en horario de planta.** ``semana`` = lunes 00:00 a lunes
  00:00, ``mes`` = día 1 a día 1, ``trimestre`` = primer día del trimestre al
  del siguiente, todos en ``TZ_PLANTA`` y convertidos a UTC para consultar.
  ``ahora`` es inyectable (por defecto ``datetime.now(UTC)``) para que los
  tests fijen el periodo sin tocar el reloj.
- **Fecha de compleción = ``Order.updated_at``.** ``Order`` no tiene
  ``completed_at`` y esta fase no admite migraciones: ``updated_at`` es el
  proxy de "completada en el periodo". Es una aproximación declarada (una
  orden completada y luego reabierta cambia de periodo), no un dato exacto.
- **€/kg solo con líneas en kg.** El material consumido se toma de
  ``real_material_qty`` de las líneas con ``target_material_unit == "kg"``; las
  líneas en metros quedan fuera del ratio (numerador y denominador se filtran
  juntos para no mezclar unidades) y se cuentan en
  ``lineas_metros_excluidas``. ``coste_total`` sí incluye todas las líneas:
  es el gasto real del periodo.
- **Chatarra sin duplicar.** El coste de la merma ya está pagado dentro del
  material cargado de la bobina, así que en el reparto el material va NETO
  (material − chatarra). Así material + mano de obra + chatarra = coste real,
  los euros cuadran con ``coste_total`` y los porcentajes suman 100 %.
- **Objetivo de €/kg desde configuración.** No existe ``objetivos.coste_kg``:
  se lee ``tenant.finances["objetivo_coste_kg"]`` (o su alias
  ``coste_kg_objetivo``) y se devuelve ``None`` si no hay valor válido.
- **Desglose del €/kg en material y transformación.** ``coste_kg.material`` es
  el material consumido (con la merma ya pagada dentro) entre los kg buenos;
  ``coste_kg.transformacion`` es el resto (mano de obra, que es lo único que
  suma al coste junto al material), calculado
  por diferencia para que ambas cifras sumen ``coste_kg.valor`` exacto. Solo
  cuenta el material de las líneas en kg, igual que el total. Es la lectura que
  separa «compré caro» de «la planta va lenta»: el material es el 80-90 % del
  coste y no lo controla la planta; la transformación sí.
- **Coste por familia de material.** ``por_familia`` agrupa las líneas en kg por
  familia derivada del código o del nombre (``familia_material``): galvanizado,
  decapado, aluminio y ``sin_clasificar``. Cada fila lleva kg, €/kg de material,
  €/kg de transformación, merma sobre el material y nº de órdenes; las familias
  sin kg no se listan. No hay columna ``familia`` en ``materials``: la
  derivación es explícita y lo no reconocido se reporta como «sin clasificar»,
  nunca se adivina.
- **Coste de paradas = incidencias creadas en la ventana**, valoradas a
  ``tiempo_parada_min / 60 × coste_hora_puesto`` del puesto de la incidencia
  (con el coste global de empresa como respaldo, igual que el resto del
  sistema).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Incidencia, Material, Order, OrderLine, Product, Tenant
from app.services.costes import coste_hora_puesto, costes_linea, costes_por_orden
from app.services.shifts import TZ_PLANTA

PERIODOS = ("semana", "mes", "trimestre")
SEMANAS_TENDENCIA = 8
TOPE_ORDENES = 10
LIMITE_CHATARRA_PCT = 5.0
LIMITE_PARADA_MIN = 60.0
UMBRAL_DESVIACION_PCT = 3.0

# Familias de material para leer el coste sin que el mix lo distorsione. Se
# derivan del código o del nombre porque `materials` no tiene columna `familia`
# (fase 8 si el maestro real no sigue una convención). Lo que no se reconoce cae
# en «sin clasificar»: es un dato honesto, no un error.
SIN_CLASIFICAR = "sin_clasificar"
ETIQUETAS_FAMILIA = {
    "galvanizado": "Galvanizado",
    "decapado": "Decapado",
    "aluminio": "Aluminio",
    SIN_CLASIFICAR: "Sin clasificar",
}

# Mismas etiquetas que el desplegable de incidencias del operario.
ETIQUETAS_TIPO_INCIDENCIA = {
    "maquina": "Máquina",
    "material": "Material",
    "seguridad": "Seguridad",
    "otro": "Otro",
}

REPARTO = (
    ("material", "Material"),
    ("mano_obra", "Mano de obra"),
    ("chatarra", "Chatarra"),
)


# --------------------------------------------------------------------------- #
# Ventanas temporales
# --------------------------------------------------------------------------- #
def _r2(valor: float | Decimal) -> float:
    return round(float(valor), 2)


def _aware_utc(momento: datetime) -> datetime:
    """Un timestamp naive se interpreta como UTC (mismo criterio que shifts)."""
    if momento.tzinfo is None:
        return momento.replace(tzinfo=UTC)
    return momento.astimezone(UTC)


def _a_utc(fecha: date) -> datetime:
    """Medianoche de esa fecha en horario de planta, expresada en UTC."""
    return datetime.combine(fecha, time.min, tzinfo=TZ_PLANTA).astimezone(UTC)


def _inicio_semana(fecha: date) -> date:
    return fecha - timedelta(days=fecha.weekday())


def _sumar_meses(fecha: date, meses: int) -> date:
    indice = fecha.year * 12 + (fecha.month - 1) + meses
    return date(indice // 12, indice % 12 + 1, 1)


def _inicio_periodo(fecha: date, periodo: str) -> date:
    if periodo == "semana":
        return _inicio_semana(fecha)
    if periodo == "mes":
        return fecha.replace(day=1)
    return date(fecha.year, ((fecha.month - 1) // 3) * 3 + 1, 1)


def _siguiente_periodo(inicio: date, periodo: str) -> date:
    if periodo == "semana":
        return inicio + timedelta(days=7)
    return _sumar_meses(inicio, 1 if periodo == "mes" else 3)


def _inicio_periodo_anterior(inicio: date, periodo: str) -> date:
    return _inicio_periodo(inicio - timedelta(days=1), periodo)


# --------------------------------------------------------------------------- #
# Carga de datos
# --------------------------------------------------------------------------- #
def _contexto(db: Session, tenant_id: uuid.UUID) -> dict:
    """Materiales, productos y filas de coste por orden (compartidos por ventanas)."""
    materiales = {
        m.id: m for m in db.scalars(select(Material).where(Material.tenant_id == tenant_id))
    }
    productos = {
        p.id: p.name for p in db.scalars(select(Product).where(Product.tenant_id == tenant_id))
    }
    filas = {f["order_id"]: f for f in costes_por_orden(db, tenant_id)}
    return {"materiales": materiales, "productos": productos, "filas": filas}


def _ordenes_completadas(
    db: Session, tenant_id: uuid.UUID, desde: datetime, hasta: datetime
) -> list[Order]:
    return list(
        db.scalars(
            select(Order)
            .where(
                Order.tenant_id == tenant_id,
                Order.estado == "completed",
                Order.updated_at >= desde,
                Order.updated_at < hasta,
            )
            .order_by(Order.updated_at.desc())
        ).all()
    )


def _lineas_por_orden(db: Session, order_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[OrderLine]]:
    if not order_ids:
        return {}
    agrupadas: dict[uuid.UUID, list[OrderLine]] = {}
    for linea in db.scalars(select(OrderLine).where(OrderLine.order_id.in_(order_ids))).all():
        agrupadas.setdefault(linea.order_id, []).append(linea)
    return agrupadas


# --------------------------------------------------------------------------- #
# Acumulados
# --------------------------------------------------------------------------- #
def _coste_kg(material: float, mano_obra: float, chatarra: float, kg: float) -> float:
    """€/kg con el material neto de chatarra (0 si no hay kg en la ventana)."""
    if kg <= 0:
        return 0.0
    return (max(material - chatarra, 0.0) + mano_obra + chatarra) / kg


def familia_material(material: Material | None) -> str:
    """Familia del material derivada de su código o de su nombre.

    No hay columna ``familia`` en ``materials``: se reconoce la convención de
    códigos del catálogo (``FLEJE-G`` galvanizado, ``FLEJE-D`` decapado,
    ``ALU`` aluminio) y las palabras del nombre (galva, DX51D, Z275, decapado,
    DC01, aluminio). Cualquier otra cosa es ``sin_clasificar``, que se reporta
    como tal en vez de adivinar.
    """
    if material is None:
        return SIN_CLASIFICAR
    codigo = (material.code or "").strip().upper()
    texto = f"{codigo} {material.name or ''}".upper()

    if codigo.startswith("ALU") or "ALUMINIO" in texto:
        return "aluminio"
    if codigo.startswith("FLEJE-G") or any(
        palabra in texto for palabra in ("GALV", "DX51", "Z275")
    ):
        return "galvanizado"
    if codigo.startswith("FLEJE-D") or any(palabra in texto for palabra in ("DECAP", "DC01")):
        return "decapado"
    return SIN_CLASIFICAR


def _acumular(lineas: list[OrderLine], materiales: dict, orden_id: uuid.UUID | None = None) -> dict:
    """Suma euros de las líneas, separando el subconjunto medido en kg.

    Las familias se acumulan solo con las líneas en kg (las mismas que forman el
    €/kg), para que sus ratios y su merma sean comparables con el total.
    """
    total = {"material": 0.0, "mano_obra": 0.0, "chatarra": 0.0}
    en_kg = {"material": 0.0, "mano_obra": 0.0, "chatarra": 0.0}
    familias: dict[str, dict] = {}
    kg = 0.0
    metros = 0
    chatarra_por_puesto: dict[str, float] = {}

    for linea in lineas:
        coste = costes_linea(linea, materiales.get(linea.material_id))
        material = float(coste["real_material"])
        mano_obra = float(coste["mano_obra"])
        chatarra = float(coste["scrap_coste"])

        total["material"] += material
        total["mano_obra"] += mano_obra
        total["chatarra"] += chatarra

        if chatarra > 0:
            puesto = linea.workstation_id or "sin puesto"
            chatarra_por_puesto[puesto] = chatarra_por_puesto.get(puesto, 0.0) + chatarra

        unidad = (linea.target_material_unit or "").strip().lower()
        if unidad == "kg":
            kg_linea = float(linea.real_material_qty or 0)
            kg += kg_linea
            en_kg["material"] += material
            en_kg["mano_obra"] += mano_obra
            en_kg["chatarra"] += chatarra

            familia = familias.setdefault(
                familia_material(materiales.get(linea.material_id)),
                {
                    "material": 0.0,
                    "mano_obra": 0.0,
                    "chatarra": 0.0,
                    "kg": 0.0,
                    "ordenes": set(),
                },
            )
            familia["material"] += material
            familia["mano_obra"] += mano_obra
            familia["chatarra"] += chatarra
            familia["kg"] += kg_linea
            if orden_id is not None:
                familia["ordenes"].add(str(orden_id))
        elif unidad == "m":
            metros += 1

    return {
        "material": total["material"],
        "mano_obra": total["mano_obra"],
        "chatarra": total["chatarra"],
        "material_kg": en_kg["material"],
        "mano_obra_kg": en_kg["mano_obra"],
        "chatarra_kg": en_kg["chatarra"],
        "kg": kg,
        "lineas_metros": metros,
        "chatarra_por_puesto": chatarra_por_puesto,
        "coste": total["material"] + total["mano_obra"],
        "coste_kg": _coste_kg(en_kg["material"], en_kg["mano_obra"], en_kg["chatarra"], kg),
        # Numerador del €/kg: evita reconstruirlo (valor × kg) al agregar semanas.
        "coste_kg_numerador": max(en_kg["material"] - en_kg["chatarra"], 0.0)
        + en_kg["mano_obra"]
        + en_kg["chatarra"],
        "familias": familias,
    }


def _reparto_pcts(valores: list[float]) -> list[float]:
    """Porcentajes redondeados a 2 decimales que suman exactamente 100."""
    total = sum(valores)
    if total <= 0:
        return [0.0 for _ in valores]
    brutos = [valor / total * 100 for valor in valores]
    pcts = [round(bruto, 2) for bruto in brutos]
    resto = round(100.0 - sum(pcts), 2)
    if resto:
        # El residuo del redondeo va al bloque mayor: el total sigue siendo 100.
        indice = max(range(len(valores)), key=lambda i: brutos[i])
        pcts[indice] = round(pcts[indice] + resto, 2)
    return pcts


def _resumen_ventana(
    db: Session, tenant_id: uuid.UUID, desde: datetime, hasta: datetime, ctx: dict
) -> dict:
    """Totales del periodo y detalle por orden completada."""
    ordenes = _ordenes_completadas(db, tenant_id, desde, hasta)
    lineas = _lineas_por_orden(db, [orden.id for orden in ordenes])

    detalle = []
    kg = 0.0
    metros = 0
    material = mano_obra = chatarra = 0.0
    material_kg = mano_obra_kg = chatarra_kg = 0.0
    familias: dict[str, dict] = {}
    estimado = comparable = 0.0
    con_estimado = 0

    for orden in ordenes:
        propias = lineas.get(orden.id, [])
        acumulado = _acumular(propias, ctx["materiales"], orden.id)
        fila = ctx["filas"].get(str(orden.id), {})

        est = fila.get("estimado_material")
        desv = fila.get("desviacion_material")
        real = fila.get("real_material_comparable") if est is not None else None
        desv_pct = (desv / est * 100) if desv is not None and est else None

        if est is not None:
            estimado += float(est)
            comparable += float(real or 0)
            con_estimado += 1

        producto = ctx["productos"].get(propias[0].product_id) if propias else None
        if not producto and propias:
            material_linea = ctx["materiales"].get(propias[0].material_id)
            producto = material_linea.code if material_linea else None

        detalle.append(
            {
                "order_id": orden.id,
                "numero": orden.numero,
                "producto": producto or "—",
                "kg": acumulado["kg"],
                "material": acumulado["material"],
                "mano_obra": acumulado["mano_obra"],
                "chatarra": acumulado["chatarra"],
                "chatarra_puesto": _puesto_mas_chatarra(acumulado["chatarra_por_puesto"]),
                "estimado": float(est) if est is not None else None,
                "real": float(real) if real is not None else None,
                "desviacion": float(desv) if desv is not None else None,
                "desv_pct": desv_pct,
            }
        )

        kg += acumulado["kg"]
        metros += acumulado["lineas_metros"]
        material += acumulado["material"]
        mano_obra += acumulado["mano_obra"]
        chatarra += acumulado["chatarra"]
        material_kg += acumulado["material_kg"]
        mano_obra_kg += acumulado["mano_obra_kg"]
        chatarra_kg += acumulado["chatarra_kg"]

        for clave, datos_familia in acumulado["familias"].items():
            destino = familias.setdefault(
                clave,
                {"material": 0.0, "mano_obra": 0.0, "chatarra": 0.0, "kg": 0.0, "ordenes": set()},
            )
            destino["material"] += datos_familia["material"]
            destino["mano_obra"] += datos_familia["mano_obra"]
            destino["chatarra"] += datos_familia["chatarra"]
            destino["kg"] += datos_familia["kg"]
            destino["ordenes"] |= datos_familia["ordenes"]

    return {
        "detalle": detalle,
        "ordenes": len(ordenes),
        "kg": kg,
        "lineas_metros": metros,
        "material": material,
        "mano_obra": mano_obra,
        "chatarra": chatarra,
        # Solo las líneas medidas en kg: es la base del €/kg y de su desglose.
        "material_kg": material_kg,
        "mano_obra_kg": mano_obra_kg,
        "familias": familias,
        "coste": material + mano_obra,
        "coste_kg": _coste_kg(material_kg, mano_obra_kg, chatarra_kg, kg),
        "desviacion": {
            "euros": comparable - estimado if con_estimado else 0.0,
            "pct": ((comparable - estimado) / estimado * 100) if estimado else 0.0,
            "ordenes_con_estimado": con_estimado,
        },
    }


def _puesto_mas_chatarra(chatarra_por_puesto: dict[str, float]) -> str | None:
    if not chatarra_por_puesto:
        return None
    return max(chatarra_por_puesto.items(), key=lambda kv: kv[1])[0]


def _por_familia(familias: dict[str, dict]) -> list[dict]:
    """Una fila por familia con kilos; las que no tienen kg no se enseñan."""
    filas = []
    for clave, datos in familias.items():
        if datos["kg"] <= 0:
            continue
        material = _r2(datos["material"] / datos["kg"])
        total = _r2((datos["material"] + datos["mano_obra"]) / datos["kg"])
        filas.append(
            {
                "familia": clave,
                "etiqueta": ETIQUETAS_FAMILIA[clave],
                "kg": _r2(datos["kg"]),
                "material": material,
                "transformacion": _r2(total - material),
                "merma_pct": (
                    _r2(datos["chatarra"] / datos["material"] * 100)
                    if datos["material"] > 0
                    else 0.0
                ),
                "ordenes": len(datos["ordenes"]),
            }
        )
    # Determinista: por kilos y, a igualdad, por etiqueta.
    filas.sort(key=lambda fila: (-fila["kg"], fila["etiqueta"]))
    return filas


# --------------------------------------------------------------------------- #
# Bloques del contrato
# --------------------------------------------------------------------------- #
def _objetivo_coste_kg(db: Session, tenant_id: uuid.UUID) -> float | None:
    """Objetivo €/kg configurado en la empresa; ``None`` si no hay valor válido."""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        return None
    finances = tenant.finances or {}
    for clave in ("objetivo_coste_kg", "coste_kg_objetivo"):
        if finances.get(clave) is None:
            continue
        try:
            valor = float(str(finances[clave]).replace(",", "."))
        except (TypeError, ValueError):
            continue
        return _r2(valor) if valor > 0 else None
    return None


def _coste_paradas(db: Session, tenant_id: uuid.UUID, desde: datetime, hasta: datetime) -> dict:
    """Paradas del periodo valoradas al €/h del puesto de cada incidencia."""
    incidencias = db.scalars(
        select(Incidencia).where(
            Incidencia.tenant_id == tenant_id,
            Incidencia.created_at >= desde,
            Incidencia.created_at < hasta,
        )
    ).all()

    coste_hora: dict[str, Decimal] = {}
    euros_por_tipo: dict[str, float] = {}
    total = Decimal("0")
    minutos = Decimal("0")

    for incidencia in incidencias:
        parada = Decimal(str(incidencia.tiempo_parada_min or 0))
        minutos += parada
        puesto = incidencia.puesto or ""
        if puesto not in coste_hora:
            coste_hora[puesto] = coste_hora_puesto(db, tenant_id, puesto or None)
        euros = parada / Decimal("60") * coste_hora[puesto]
        total += euros
        euros_por_tipo[incidencia.tipo] = euros_por_tipo.get(incidencia.tipo, 0.0) + float(euros)

    por_tipo = [
        {
            "tipo": tipo,
            "etiqueta": ETIQUETAS_TIPO_INCIDENCIA.get(tipo, tipo.title()),
            "euros": _r2(euros),
        }
        for tipo, euros in sorted(euros_por_tipo.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {
        "total": _r2(total),
        "por_tipo": por_tipo,
        "horas": _r2(minutos / Decimal("60")),
    }


def _tendencia(db: Session, tenant_id: uuid.UUID, hoy: date, ctx: dict) -> list[dict]:
    """€/kg de las 8 últimas semanas (la última es la de ``hoy``), de vieja a nueva."""
    primera = _inicio_semana(hoy) - timedelta(weeks=SEMANAS_TENDENCIA - 1)
    desde = _a_utc(primera)
    hasta = _a_utc(_inicio_semana(hoy) + timedelta(days=7))

    semanas: dict[date, dict[str, float]] = {
        primera + timedelta(weeks=i): {"coste": 0.0, "kg": 0.0} for i in range(SEMANAS_TENDENCIA)
    }

    for orden in _ordenes_completadas(db, tenant_id, desde, hasta):
        lineas = _lineas_por_orden(db, [orden.id]).get(orden.id, [])
        acumulado = _acumular(lineas, ctx["materiales"])
        semana = _inicio_semana(_aware_utc(orden.updated_at).astimezone(TZ_PLANTA).date())
        if semana not in semanas:
            continue
        semanas[semana]["kg"] += acumulado["kg"]
        semanas[semana]["coste"] += acumulado["coste_kg_numerador"]

    return [
        {
            "semana": semana.isoformat(),
            "valor": _r2(datos["coste"] / datos["kg"]) if datos["kg"] > 0 else 0.0,
        }
        for semana, datos in sorted(semanas.items())
    ]


def _causa(orden: dict, incidencias: list[Incidencia], desv_pct: float | None) -> str:
    """Causa de la desviación, por prioridad (el orden de las reglas es contrato)."""
    material = orden["material"]
    if material > 0 and orden["chatarra"] / material * 100 > LIMITE_CHATARRA_PCT:
        return f"Chatarra en {orden['chatarra_puesto'] or 'sin puesto'}"

    if incidencias:
        peor = max(incidencias, key=lambda i: float(i.tiempo_parada_min or 0))
        if float(peor.tiempo_parada_min or 0) > LIMITE_PARADA_MIN:
            return f"Paradas en {peor.puesto or 'sin puesto'}"

    if desv_pct is not None and desv_pct < 0:
        return "Mejor aprovechamiento"
    if desv_pct is not None and abs(desv_pct) < UMBRAL_DESVIACION_PCT:
        return "Dentro de lo normal"
    return "Sin causa clara"


def _incidencias_de_ordenes(
    db: Session, tenant_id: uuid.UUID, order_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[Incidencia]]:
    if not order_ids:
        return {}
    agrupadas: dict[uuid.UUID, list[Incidencia]] = {}
    for incidencia in db.scalars(
        select(Incidencia).where(
            Incidencia.tenant_id == tenant_id,
            Incidencia.order_id.in_(order_ids),
        )
    ).all():
        agrupadas.setdefault(incidencia.order_id, []).append(incidencia)
    return agrupadas


def panel_costes(
    db: Session,
    tenant_id: uuid.UUID,
    periodo: str = "mes",
    ahora: datetime | None = None,
) -> dict:
    """Vista Costes del panel de mando para el periodo natural pedido.

    ``periodo`` ∈ ``semana`` | ``mes`` | ``trimestre``. ``ahora`` (UTC) fija la
    referencia temporal; por defecto, el instante actual.
    """
    if periodo not in PERIODOS:
        raise ValueError(f"periodo debe ser uno de {PERIODOS}")

    referencia = _aware_utc(ahora or datetime.now(UTC))
    hoy = referencia.astimezone(TZ_PLANTA).date()
    inicio = _inicio_periodo(hoy, periodo)
    fin = _siguiente_periodo(inicio, periodo)
    anterior_inicio = _inicio_periodo_anterior(inicio, periodo)

    desde, hasta = _a_utc(inicio), _a_utc(fin)
    ctx = _contexto(db, tenant_id)

    actual = _resumen_ventana(db, tenant_id, desde, hasta, ctx)
    anterior = _resumen_ventana(db, tenant_id, _a_utc(anterior_inicio), desde, ctx)

    valores_reparto = [actual["material"], actual["mano_obra"], actual["chatarra"]]
    # El material del reparto va neto de chatarra para no contar dos veces la merma.
    neto = max(actual["material"] - actual["chatarra"], 0.0)
    pcts = _reparto_pcts([neto, actual["mano_obra"], actual["chatarra"]])

    candidatas = [orden for orden in actual["detalle"] if orden["desviacion"] is not None]
    candidatas.sort(key=lambda orden: abs(orden["desviacion"]), reverse=True)
    incidencias = _incidencias_de_ordenes(
        db, tenant_id, [orden["order_id"] for orden in candidatas]
    )

    # Desglose del €/kg en sus dos mitades: material (lo que se paga al proveedor,
    # con la merma ya dentro) y transformación (mano de obra). El residuo del
    # redondeo va a transformación para que las dos cifras sumen `valor` exacto.
    coste_kg_total = _r2(actual["coste_kg"])
    coste_kg_material = _r2(actual["material_kg"] / actual["kg"]) if actual["kg"] > 0 else 0.0

    return {
        "periodo": periodo,
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "coste_kg": {
            "valor": coste_kg_total,
            "periodo_anterior": _r2(anterior["coste_kg"]),
            "objetivo": _objetivo_coste_kg(db, tenant_id),
            "material": coste_kg_material,
            "transformacion": _r2(coste_kg_total - coste_kg_material),
        },
        "coste_total": _r2(actual["coste"]),
        "kg_total": _r2(actual["kg"]),
        "lineas_metros_excluidas": actual["lineas_metros"],
        "ordenes_completadas": actual["ordenes"],
        "desviacion": {
            "pct": _r2(actual["desviacion"]["pct"]),
            "euros": _r2(actual["desviacion"]["euros"]),
            "ordenes_con_estimado": actual["desviacion"]["ordenes_con_estimado"],
        },
        "chatarra": {
            "euros": _r2(actual["chatarra"]),
            "pct_material": _r2(
                actual["chatarra"] / actual["material"] * 100 if actual["material"] else 0.0
            ),
        },
        "reparto": [
            {"clave": clave, "etiqueta": etiqueta, "euros": _r2(valor), "pct": pct}
            for (clave, etiqueta), valor, pct in zip(
                REPARTO, [neto] + valores_reparto[1:], pcts, strict=True
            )
        ],
        "coste_paradas": _coste_paradas(db, tenant_id, desde, hasta),
        "por_familia": _por_familia(actual["familias"]),
        "tendencia": _tendencia(db, tenant_id, hoy, ctx),
        "ordenes": [
            {
                "order_id": str(orden["order_id"]),
                "numero": orden["numero"],
                "producto": orden["producto"],
                "kg": _r2(orden["kg"]),
                "estimado": _r2(orden["estimado"]),
                "real": _r2(orden["real"]),
                "desv_euros": _r2(orden["desviacion"]),
                "desv_pct": _r2(orden["desv_pct"]),
                "causa": _causa(orden, incidencias.get(orden["order_id"], []), orden["desv_pct"]),
            }
            for orden in candidatas[:TOPE_ORDENES]
        ],
    }
