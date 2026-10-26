"""Seed del catálogo de estanterías industriales (empresa fabricante).

Convierte la demo en una empresa real de estanterías metálicas (referencia:
catálogo Mecalux). Idempotente: si el producto EST-PORTICO ya existe solo
asegura el rename del tenant.

Contenido:
- Rename tenant "Demo Aceros" -> "Kavana Estanterías" (slug 'demo' intacto).
- Grupos de trabajo = procesos (Corte, Punzonado, Doblado, Soldadura,
  Galvanizado, Montaje) + 7 puestos nuevos; LINEA-1..3 intactos.
- Materias primas: flejes slit (galva DX51D+Z275 y decapado DC01) con
  anchos desarrollados por perfilado, más perfiles, tubo, malla y
  tornillería, con sus lotes/bobinas de stock y kardex de entrada.
- 21 piezas (ManufacturingModel) con plan de autocontroles: familia real de
  travesaños (91/101/108), largueros (135/205/212) y puntales (135/150/165).
- 12 productos terminados con BOM (piezas fabricadas + materiales directos).
- 3 órdenes nuevas (2 activas + 1 completada) con líneas ligadas a producto.
- Histórico: production_logs, material_consumos, kardex de salida,
  autocontroles (quality_records) y una incidencia resuelta.

Contenido honesto: datos ficticios de demostración, sin clientes reales.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Incidencia,
    Material,
    Order,
    OrderLine,
    Product,
    StockItem,
    Tenant,
    User,
    Workstation,
    WorkstationGroup,
)
from app.models.incidencia import IncidenciaHistorial
from app.models.quality import (
    ManufacturingModel,
    QualityMeasurement,
    QualityPlanCheck,
    QualityRecord,
)
from app.models.traceability import ProductionLog
from app.models.transaction import MaterialConsumo, MaterialTransaction

NOMBRE_TENANT = "Kavana Estanterías"

GRUPOS = [
    ("Corte", "#f39c12"),
    ("Punzonado", "#8e44ad"),
    ("Doblado", "#3498db"),
    ("Soldadura", "#e74c3c"),
    ("Galvanizado", "#27ae60"),
    ("Montaje", "#1abc9c"),
]

# (code, name, grupo, color, hourly_cost, registration_method)
PUESTOS = [
    ("CORTE-1", "Corte láser fibra", "Corte", "#f39c12", "48", "quantity"),
    ("PUNZ-1", "Punzonado de chapa", "Punzonado", "#8e44ad", "46", "quantity"),
    ("DOBL-1", "Plegadora CNC", "Doblado", "#3498db", "47", "quantity"),
    ("SOL-1", "Soldadura MIG/MAG", "Soldadura", "#e74c3c", "42", "timer"),
    ("GALV-1", "Galvanizado y pintado", "Galvanizado", "#27ae60", "40", "timer"),
    ("MONT-1", "Montaje final", "Montaje", "#1abc9c", "35", "quantity"),
    ("MONT-2", "Montaje y embalaje", "Montaje", "#16a085", "34", "quantity"),
]

# Materia prima de perfilado: flejes slit de bobina madre. Los anchos son
# el perímetro desarrollado de la sección plegada (web + 2 alas + 2 labios
# menos retracción de doblez, ~1,7 mm/doblez 90°). Travesaños: ala 30,
# labio 15. Largueros/puntales: fondo 70, labio 15.
# (code, name, unit, cost, stock_min, ancho, espesor)
MATERIALES = [
    ("FLEJE-G175-12", "Fleje galva DX51D+Z275 175x1,2", "kg", "1.42", "400", "175", "1.2"),
    ("FLEJE-G185-12", "Fleje galva DX51D+Z275 185x1,2", "kg", "1.42", "400", "185", "1.2"),
    ("FLEJE-G190-12", "Fleje galva DX51D+Z275 190x1,2", "kg", "1.42", "400", "190", "1.2"),
    ("FLEJE-G190-18", "Fleje galva DX51D+Z275 190x1,8", "kg", "1.40", "300", "190", "1.8"),
    ("FLEJE-D265-15", "Fleje decapado DC01 265x1,5", "kg", "1.23", "400", "265", "1.5"),
    ("FLEJE-D265-18", "Fleje decapado DC01 265x1,8", "kg", "1.22", "400", "265", "1.8"),
    ("FLEJE-D310-15", "Fleje decapado DC01 310x1,5", "kg", "1.23", "350", "310", "1.5"),
    ("FLEJE-D320-20", "Fleje decapado DC01 320x2,0", "kg", "1.19", "350", "320", "2.0"),
    ("FLEJE-D365-18", "Fleje decapado DC01 365x1,8", "kg", "1.20", "400", "365", "1.8"),
    ("FLEJE-D365-20", "Fleje decapado DC01 365x2,0", "kg", "1.19", "400", "365", "2.0"),
    ("FLEJE-D370-20", "Fleje decapado DC01 370x2,0", "kg", "1.19", "350", "370", "2.0"),
    ("ACERO-S355", "Bobina acero S355 3.0x1500", "kg", "1.05", "500", "1500", "3.0"),
    ("PERFIL-U100", "Perfil U acero S235 100x50x4", "m", "6.50", "100", None, None),
    ("PERFIL-L60", "Angulo L60x60x5", "m", "4.20", "80", None, None),
    ("TUBO-4020", "Tubo rectangular 40x20x2", "m", "3.80", "80", None, None),
    ("TORN-M8", "Tornillo M8x40 galvanizado", "uds", "0.08", "1000", None, None),
    ("MALLA-ES5", "Malla electrosoldada 50x50 d5", "uds", "12.50", "30", None, None),
]

# (code, lote, material_code, cantidad, unit, ancho, espesor, coste, dias, ubicacion)
LOTES = [
    (
        "COIL-S355-001", "S355-2610-01", "ACERO-S355", "2500", "kg",
        "1500", "3.0", "1.05", 30, "ALMACEN-1",
    ),
    (
        "COIL-S355-002", "S355-2610-02", "ACERO-S355", "2300", "kg",
        "1500", "3.0", "1.05", 20, "ALMACEN-1",
    ),
    (
        "COIL-S355-003", "S355-2610-03", "ACERO-S355", "1800", "kg",
        "1500", "3.0", "1.05", 10, "ALMACEN-2",
    ),
    (
        "COIL-FG175-001", "DX51D-441207", "FLEJE-G175-12", "3200", "kg",
        "175", "1.2", "1.42", 30, "ALMACEN-1",
    ),
    (
        "COIL-FG175-002", "DX51D-441315", "FLEJE-G175-12", "2400", "kg",
        "175", "1.2", "1.42", 15, "ALMACEN-2",
    ),
    (
        "COIL-FG185-001", "DX51D-441422", "FLEJE-G185-12", "2800", "kg",
        "185", "1.2", "1.42", 22, "ALMACEN-1",
    ),
    (
        "COIL-FG190-001", "DX51D-441533", "FLEJE-G190-12", "3500", "kg",
        "190", "1.2", "1.42", 26, "ALMACEN-2",
    ),
    (
        "COIL-FG190-002", "DX51D-441608", "FLEJE-G190-12", "1800", "kg",
        "190", "1.2", "1.42", 10, "ALMACEN-2",
    ),
    (
        "COIL-FG190-003", "DX51D-441719", "FLEJE-G190-18", "2600", "kg",
        "190", "1.8", "1.40", 18, "ALMACEN-1",
    ),
    (
        "COIL-FD265-001", "DC01-338915", "FLEJE-D265-15", "2600", "kg",
        "265", "1.5", "1.23", 24, "ALMACEN-2",
    ),
    (
        "COIL-FD265-002", "DC01-339044", "FLEJE-D265-18", "3100", "kg",
        "265", "1.8", "1.22", 28, "ALMACEN-1",
    ),
    (
        "COIL-FD265-003", "DC01-339166", "FLEJE-D265-18", "2200", "kg",
        "265", "1.8", "1.22", 12, "ALMACEN-2",
    ),
    (
        "COIL-FD310-001", "DC01-339271", "FLEJE-D310-15", "2400", "kg",
        "310", "1.5", "1.23", 20, "ALMACEN-1",
    ),
    (
        "COIL-FD320-001", "DC01-339388", "FLEJE-D320-20", "2800", "kg",
        "320", "2.0", "1.19", 16, "ALMACEN-2",
    ),
    (
        "COIL-FD365-001", "DC01-339492", "FLEJE-D365-18", "3400", "kg",
        "365", "1.8", "1.20", 27, "ALMACEN-1",
    ),
    (
        "COIL-FD365-002", "DC01-339517", "FLEJE-D365-18", "2000", "kg",
        "365", "1.8", "1.20", 11, "ALMACEN-2",
    ),
    (
        "COIL-FD365-003", "DC01-339633", "FLEJE-D365-20", "3600", "kg",
        "365", "2.0", "1.19", 23, "ALMACEN-1",
    ),
    (
        "COIL-FD370-001", "DC01-339750", "FLEJE-D370-20", "2500", "kg",
        "370", "2.0", "1.19", 14, "ALMACEN-2",
    ),
    ("LOTE-U100-001", "U100-2610", "PERFIL-U100", "400", "m", None, None, "6.50", 22, "EXTERIOR-1"),
    ("LOTE-L60-001", "L60-2610", "PERFIL-L60", "300", "m", None, None, "4.20", 22, "EXTERIOR-1"),
    ("LOTE-TUB-001", "TUB-2610", "TUBO-4020", "350", "m", None, None, "3.80", 15, "EXTERIOR-1"),
    ("LOTE-TORN-001", "TORN-2610", "TORN-M8", "5000", "uds", None, None, "0.08", 18, "ALMACEN-3"),
    (
        "LOTE-MALLA-001", "MALLA-2610", "MALLA-ES5", "120", "uds",
        None, None, "12.50", 18, "ALMACEN-3",
    ),
]

# (code, name, material_code, checks) donde check =
# (name, tipo, tool, nominal, tol_plus, tol_minus, is_critical)
PIEZAS = [
    ("MONTANTE-P50", "Puntal 135x1,8", "FLEJE-D265-18", [
        ("Largo Total", "numeric", "Cinta metrica", "3000", "2", "2", True),
        ("Espesor", "numeric", "Micrometro", "1.8", "0.1", "0.1", True),
        ("Ranuras punzonadas", "pass_fail", "Galga patron", None, None, None, True),
    ]),
    ("LARGUERO-E27", "Larguero 135x1,8", "FLEJE-D265-18", [
        ("Largo Total", "numeric", "Cinta metrica", "2700", "2", "2", True),
        ("Espesor", "numeric", "Micrometro", "1.8", "0.1", "0.1", True),
        ("Perforaciones testa", "pass_fail", "Galga patron", None, None, None, True),
    ]),
    ("BANDEJA-P45", "Bandeja plegada 45 mm", "ACERO-DC01", [
        ("Largo Total", "numeric", "Cinta metrica", "1200", "2", "2", True),
        ("Espesor", "numeric", "Micrometro", "1.2", "0.1", "0.1", True),
    ]),
    ("TRAVESANO-STD", "Travesaño 91x1,2", "FLEJE-G175-12", [
        ("Largo Total", "numeric", "Cinta metrica", "1200", "2", "2", True),
        ("Espesor", "numeric", "Micrometro", "1.2", "0.1", "0.1", True),
        ("Acabado zinc", "visual", None, None, None, None, False),
    ]),
    ("DIAGONAL-STD", "Barra diagonal", "PERFIL-L60", [
        ("Largo Total", "numeric", "Cinta metrica", "1800", "3", "3", True),
        ("Corte a escuadra", "pass_fail", "Escuadra 90", None, None, None, True),
    ]),
    ("ATIRANTADO-STD", "Barra atirantado", "TUBO-4020", [
        ("Largo Total", "numeric", "Cinta metrica", "1100", "3", "3", True),
        ("Soldadura de testa", "visual", None, None, None, None, True),
    ]),
    ("CARRIL-GP", "Carril driver calle GP", "ACERO-S355", [
        ("Largo Total", "numeric", "Cinta metrica", "6000", "5", "5", True),
        ("Espesor", "numeric", "Micrometro", "3.0", "0.15", "0.15", True),
        ("Perforaciones", "pass_fail", "Galga patron", None, None, None, True),
    ]),
    ("CARRO-PB", "Carro push-back", "ACERO-S355", [
        ("Ancho Total", "numeric", "Cinta metrica", "1200", "3", "3", True),
        ("Espesor", "numeric", "Micrometro", "3.0", "0.15", "0.15", True),
        ("Rodamiento", "pass_fail", "Banco pruebas", None, None, None, True),
    ]),
    ("RODILLO-DYN", "Rodillo dinamico", "ACERO-DC01", [
        ("Diametro", "numeric", "Calibrador", "60", "0.5", "0.5", True),
        ("Giro libre", "pass_fail", "Banco pruebas", None, None, None, True),
    ]),
    ("BRAZO-CNT", "Brazo voladizo", "PERFIL-L60", [
        ("Largo Total", "numeric", "Cinta metrica", "1200", "3", "3", True),
        ("Plomado", "pass_fail", "Nivel", None, None, None, True),
    ]),
    ("COLUMNA-CNT", "Columna voladizo", "PERFIL-U100", [
        ("Largo Total", "numeric", "Cinta metrica", "4000", "5", "5", True),
        ("Espesor", "numeric", "Micrometro", "4.0", "0.2", "0.2", True),
        ("Verticalidad", "pass_fail", "Nivel", None, None, None, True),
    ]),
    ("VIGA-SIGMA", "Viga sigma entreplanta", "ACERO-S355", [
        ("Largo Total", "numeric", "Cinta metrica", "2700", "3", "3", True),
        ("Espesor", "numeric", "Micrometro", "3.0", "0.15", "0.15", True),
        ("Perfilado", "visual", None, None, None, None, False),
    ]),
    ("ESCUDO-LAT", "Escudo lateral", "ACERO-DC01", [
        ("Largo Total", "numeric", "Cinta metrica", "1000", "2", "2", True),
        ("Espesor", "numeric", "Micrometro", "1.2", "0.1", "0.1", True),
    ]),
    ("ESCALERA-GR", "Escalera de mantenimiento", "PERFIL-U100", [
        ("Largo Total", "numeric", "Cinta metrica", "3000", "5", "5", True),
        ("Antideslizante", "pass_fail", "Banco pruebas", None, None, None, True),
    ]),
    ("TRAV-101", "Travesaño 101x1,2", "FLEJE-G185-12", [
        ("Largo Total", "numeric", "Cinta metrica", "1200", "2", "2", True),
        ("Espesor", "numeric", "Micrometro", "1.2", "0.1", "0.1", True),
        ("Acabado zinc", "visual", None, None, None, None, False),
    ]),
    ("TRAV-108", "Travesaño 108x1,2", "FLEJE-G190-12", [
        ("Largo Total", "numeric", "Cinta metrica", "1200", "2", "2", True),
        ("Espesor", "numeric", "Micrometro", "1.2", "0.1", "0.1", True),
        ("Acabado zinc", "visual", None, None, None, None, False),
    ]),
    ("TRAV-108P", "Travesaño 108x1,8", "FLEJE-G190-18", [
        ("Largo Total", "numeric", "Cinta metrica", "1200", "2", "2", True),
        ("Espesor", "numeric", "Micrometro", "1.8", "0.1", "0.1", True),
        ("Acabado zinc", "visual", None, None, None, None, False),
    ]),
    ("LARG-205", "Larguero 205x1,8", "FLEJE-D365-18", [
        ("Largo Total", "numeric", "Cinta metrica", "2700", "2", "2", True),
        ("Espesor", "numeric", "Micrometro", "1.8", "0.1", "0.1", True),
        ("Perforaciones testa", "pass_fail", "Galga patron", None, None, None, True),
    ]),
    ("LARG-212", "Larguero 212x2,0", "FLEJE-D370-20", [
        ("Largo Total", "numeric", "Cinta metrica", "2700", "2", "2", True),
        ("Espesor", "numeric", "Micrometro", "2.0", "0.1", "0.1", True),
        ("Perforaciones testa", "pass_fail", "Galga patron", None, None, None, True),
    ]),
    ("PUNT-150", "Puntal 150x1,5", "FLEJE-D310-15", [
        ("Largo Total", "numeric", "Cinta metrica", "3000", "2", "2", True),
        ("Espesor", "numeric", "Micrometro", "1.5", "0.1", "0.1", True),
        ("Ranuras punzonadas", "pass_fail", "Galga patron", None, None, None, True),
    ]),
    ("PUNT-165", "Puntal 165x2,0", "FLEJE-D320-20", [
        ("Largo Total", "numeric", "Cinta metrica", "4000", "3", "3", True),
        ("Espesor", "numeric", "Micrometro", "2.0", "0.1", "0.1", True),
        ("Ranuras punzonadas", "pass_fail", "Galga patron", None, None, None, True),
    ]),
]

# (code, name, description, [(tipo, code, quantity)...]) tipo: "pieza" | "material"
PRODUCTOS = [
    ("EST-PORTICO", "Rack Portico", "Estanteria convencional de palets.",
     [("pieza", "MONTANTE-P50", "8"), ("pieza", "LARGUERO-E27", "12"),
      ("pieza", "DIAGONAL-STD", "8"), ("pieza", "ATIRANTADO-STD", "4"),
      ("pieza", "TRAVESANO-STD", "4"), ("material", "TORN-M8", "64")]),
    ("EST-CALLEJON", "Callejon GP", "Drive-in con carriles de arrastre.",
     [("pieza", "MONTANTE-P50", "8"), ("pieza", "CARRIL-GP", "8"),
      ("pieza", "ESCUDO-LAT", "8"), ("pieza", "LARGUERO-E27", "4"),
      ("material", "TORN-M8", "72")]),
    ("EST-DESLIZ", "Pasillo Desliz", "Sistema movil de palets.",
     [("pieza", "MONTANTE-P50", "6"), ("pieza", "CARRO-PB", "6"),
      ("pieza", "CARRIL-GP", "12"), ("material", "TORN-M8", "48")]),
    ("EST-CORCEL", "Canal Corcel", "Pallet shuttle con carril central.",
     [("pieza", "MONTANTE-P50", "8"), ("pieza", "CARRO-PB", "8"),
      ("pieza", "CARRIL-GP", "16"), ("material", "TORN-M8", "80")]),
    ("EST-GRAVEDAD", "Pasillo Gravedad", "Almacen dinamico por gravedad.",
     [("pieza", "MONTANTE-P50", "6"), ("pieza", "RODILLO-DYN", "96"),
      ("pieza", "LARGUERO-E27", "6"), ("material", "TORN-M8", "56")]),
    ("EST-REVERSA", "Linea Reversa", "Push-back de ultima posicion.",
     [("pieza", "MONTANTE-P50", "6"), ("pieza", "CARRO-PB", "8"),
      ("pieza", "LARGUERO-E27", "12"), ("material", "TORN-M8", "56")]),
    ("EST-TITAN", "Bloque Titan", "Rack pesado para carga industrial.",
     [("pieza", "MONTANTE-P50", "6"), ("pieza", "LARGUERO-E27", "12"),
      ("pieza", "BANDEJA-P45", "24"), ("pieza", "DIAGONAL-STD", "6"),
      ("material", "TORN-M8", "72")]),
    ("EST-PLUMA", "Estante Pluma", "Balda ligeras para piezas menudas.",
     [("pieza", "MONTANTE-P50", "4"), ("pieza", "TRAVESANO-STD", "8"),
      ("pieza", "BANDEJA-P45", "12"), ("material", "TORN-M8", "40")]),
    ("EST-VOLADIZO", "Mastil Voladizo", "Cantilever para bobinas y perfiles.",
     [("pieza", "COLUMNA-CNT", "4"), ("pieza", "BRAZO-CNT", "16"),
      ("pieza", "ATIRANTADO-STD", "4"), ("material", "TORN-M8", "48")]),
    ("EST-ALTILLO", "Planta Altillo", "Entreplanta con barandilla y malla.",
     [("pieza", "VIGA-SIGMA", "8"), ("pieza", "COLUMNA-CNT", "8"),
      ("pieza", "BANDEJA-P45", "16"), ("material", "MALLA-ES5", "12"),
      ("material", "TORN-M8", "96")]),
    ("EST-MEDIA", "Estanteria Media 108", "Balda media carga con travesanos 108 galva.",
     [("pieza", "PUNT-150", "6"), ("pieza", "TRAV-108", "9"),
      ("pieza", "LARGUERO-E27", "6"), ("material", "TORN-M8", "48")]),
    ("EST-PESADA", "Rack Pesado 212", "Rack palets con largueros 212x2 y puntales 165.",
     [("pieza", "PUNT-165", "6"), ("pieza", "LARG-212", "12"),
      ("pieza", "DIAGONAL-STD", "6"), ("material", "TORN-M8", "72")]),
]


def seed_estanterias(db: Session) -> dict:
    """Siembra el catalogo de estanterias. Idempotente.

    Busca el tenant por identidad estable (ver buscar_tenant_demo en
    seed_demo): en produccion el slug es 'demo-aceros'. Si el catalogo ya
    existe solo asegura el rename del tenant.
    """
    from app.services.seed_demo import buscar_tenant_demo

    tenant = buscar_tenant_demo(db)
    if tenant is None:
        return {"created": False, "tenant": None}

    _renombrar_tenant(db, tenant)

    if db.scalar(select(Product).where(Product.code == "EST-PORTICO")) is not None:
        reparar_costes_demo(db, tenant.id)
        db.commit()
        return {"created": False, "tenant": str(tenant.id)}

    operario = db.scalar(select(User).where(User.email == "operario@demo.local"))
    materiales_user = db.scalar(select(User).where(User.email == "materias@demo.local"))

    _asegurar_grupos_y_puestos(db, tenant.id)
    materiales = _asegurar_materiales(db, tenant.id)
    _asegurar_entradas_kardex(db, tenant.id, materiales, materiales_user)
    piezas = _asegurar_piezas(db, tenant.id)
    productos = _asegurar_productos(db, tenant.id, piezas, materiales)
    ordenes = _crear_ordenes(db, tenant.id, productos, piezas, materiales, operario)
    _historico(db, tenant.id, ordenes, piezas, materiales, operario, materiales_user)

    db.commit()
    return {"created": True, "tenant": str(tenant.id)}


def _objetivo_material(mat: Material, total: Decimal, metros) -> Decimal | None:
    """Objetivo de material de la línea en la unidad del material.

    kg: kg/pieza por fórmula de densidad (ancho x espesor x largo) x piezas.
    m: metros/pieza x piezas. Sin dimensiones: None (sin estimado, no se
    inventa). Antes se sembraba el número de piezas como si fueran kg.
    """
    from app.services.production import DENSIDAD_CALIBRADA_KAVANA_KG_DM3, _calcular_kg_por_pieza

    if not metros:
        return None
    if mat.unit == "m":
        return (Decimal(str(metros)) * total).quantize(Decimal("0.0001"))
    if mat.unit != "kg":
        return None
    densidad = (mat.density_calibrada or DENSIDAD_CALIBRADA_KAVANA_KG_DM3) * 1000
    kg_pieza = _calcular_kg_por_pieza(
        ancho_mm=mat.dimension_ancho_mm,
        espesor_mm=mat.dimension_espesor_mm,
        largo_m=Decimal(str(metros)),
        densidad_kgm3=densidad,
    )
    if kg_pieza <= 0:
        return None
    return (kg_pieza * total).quantize(Decimal("0.0001"))


def reparar_costes_demo(db: Session, tenant_id) -> None:
    """Reconstruye los costes de las líneas de la demo desde sus datos reales.

    Idempotente y solo para el tenant demo. Corrige dos defectos de siembras
    anteriores (ya desplegadas):
    1. target_material_qty sembrado con el número de piezas → se recalcula.
    2. Líneas históricas sin coste (el coste se escribía a mano en la orden)
       → material desde material_consumos, tiempo desde production_logs y
       mano de obra con el €/h del puesto.
    Después hace el roll-up a la cabecera de cada orden.
    """
    from app.services.costes import actualizar_costes_orden, coste_hora_puesto

    ordenes = db.scalars(select(Order).where(Order.tenant_id == tenant_id)).all()
    for orden in ordenes:
        for linea in orden.lines:
            mat = db.get(Material, linea.material_id) if linea.material_id else None

            if (
                mat is not None
                and linea.meters_per_piece
                and linea.target_material_qty is not None
                and linea.target_material_qty == linea.total_quantity
            ):
                linea.target_material_qty = _objetivo_material(
                    mat, linea.total_quantity, linea.meters_per_piece
                )

            if (linea.real_material_cost or 0) == 0:
                consumos = db.scalars(
                    select(MaterialConsumo).where(
                        MaterialConsumo.order_line_id == linea.id,
                        MaterialConsumo.tipo.in_(("automatico", "manual", "ajuste")),
                    )
                ).all()
                if consumos:
                    if (linea.real_material_qty or 0) == 0:
                        linea.real_material_qty = sum(
                            (c.consumed_quantity for c in consumos), Decimal("0")
                        )
                    linea.real_material_cost = sum(
                        (c.total_cost for c in consumos), Decimal("0")
                    )

            if (linea.real_time or 0) == 0 and linea.estado == "completed":
                marcas = db.scalars(
                    select(ProductionLog.timestamp)
                    .where(ProductionLog.line_id == linea.id)
                    .order_by(ProductionLog.timestamp.asc())
                ).all()
                if len(marcas) >= 2:
                    minutos = (marcas[-1] - marcas[0]).total_seconds() / 60
                    linea.real_time = Decimal(str(round(minutos, 2)))

            if (linea.real_cost or 0) == 0 and (
                (linea.real_material_cost or 0) > 0 or (linea.real_time or 0) > 0
            ):
                horas = (linea.real_time or Decimal("0")) / 60
                mano_obra = (
                    horas * coste_hora_puesto(db, tenant_id, linea.workstation_id)
                ).quantize(Decimal("0.01"))
                linea.real_cost = (linea.real_material_cost or Decimal("0")) + mano_obra
        db.flush()
        actualizar_costes_orden(db, orden)
    db.flush()


def _renombrar_tenant(db: Session, tenant: Tenant) -> None:
    """Renombra el tenant y su branding (slug 'demo' intacto)."""
    if tenant.name == NOMBRE_TENANT:
        return
    tenant.name = NOMBRE_TENANT
    branding = dict(tenant.theme.get("branding") or {})
    branding["companyName"] = NOMBRE_TENANT
    theme = dict(tenant.theme)
    theme["branding"] = branding
    tenant.theme = theme
    db.commit()


def _asegurar_grupos_y_puestos(db: Session, tenant_id) -> None:
    grupos: dict[str, WorkstationGroup] = {}
    for name, color in GRUPOS:
        grupo = db.scalar(
            select(WorkstationGroup).where(
                WorkstationGroup.tenant_id == tenant_id,
                WorkstationGroup.name == name,
            )
        )
        if grupo is None:
            grupo = WorkstationGroup(tenant_id=tenant_id, name=name, color=color)
            db.add(grupo)
            db.flush()
        grupos[name] = grupo

    for code, name, grupo_name, color, coste, metodo in PUESTOS:
        existe = db.scalar(
            select(Workstation).where(
                Workstation.tenant_id == tenant_id, Workstation.code == code
            )
        )
        if existe is None:
            db.add(
                Workstation(
                    tenant_id=tenant_id,
                    group_id=grupos[grupo_name].id,
                    code=code,
                    name=name,
                    color=color,
                    hourly_cost=Decimal(coste),
                    registration_method=metodo,
                    is_active=True,
                )
            )
    db.flush()


def _asegurar_materiales(db: Session, tenant_id) -> dict[str, Material]:
    materiales: dict[str, Material] = {}
    for code, name, unit, cost, stock_min, ancho, espesor in MATERIALES:
        mat = db.scalar(
            select(Material).where(Material.tenant_id == tenant_id, Material.code == code)
        )
        if mat is None:
            mat = Material(
                tenant_id=tenant_id,
                code=code,
                name=name,
                stock_minimum=Decimal(stock_min),
                cost_per_unit=Decimal(cost),
                dimension_ancho_mm=Decimal(ancho) if ancho else None,
                dimension_espesor_mm=Decimal(espesor) if espesor else None,
                unit=unit,
                stock_current=Decimal("0"),
            )
            db.add(mat)
            db.flush()
        materiales[code] = mat

    # ACERO-DC01 ya existe (seed_demo); solo la referenciamos
    dc01 = db.scalar(
        select(Material).where(Material.tenant_id == tenant_id, Material.code == "ACERO-DC01")
    )
    materiales["ACERO-DC01"] = dc01

    for code, lote, mat_code, cantidad, unit, ancho, espesor, coste, dias, ubicacion in LOTES:
        existe = db.scalar(
            select(StockItem).where(
                StockItem.tenant_id == tenant_id, StockItem.coil_id == code
            )
        )
        if existe is None:
            mat = materiales[mat_code]
            db.add(
                StockItem(
                    tenant_id=tenant_id,
                    material_id=mat.id,
                    lote=lote,
                    coil_id=code,
                    cantidad_inicial=Decimal(cantidad),
                    cantidad_disponible=Decimal(cantidad),
                    unit=unit,
                    width_mm=Decimal(ancho) if ancho else None,
                    thickness_mm=Decimal(espesor) if espesor else None,
                    coste_por_unidad=Decimal(coste),
                    fecha_entrada=datetime.now(UTC) - timedelta(days=dias),
                    ubicacion=ubicacion,
                    estado="activo",
                    es_pico=False,
                    grado_acero=(
                        "DX51D+Z275" if mat_code.startswith("FLEJE-G")
                        else "DC01" if mat_code.startswith("FLEJE-D")
                        else mat_code.split("-")[0] if mat_code.startswith("ACERO")
                        else None
                    ),
                )
            )
    db.flush()

    # stock_current derivado: suma de lotes disponibles por material
    for mat in materiales.values():
        if mat is None:
            continue
        lotes = db.execute(
            select(StockItem.cantidad_disponible).where(StockItem.material_id == mat.id)
        ).all()
        mat.stock_current = sum((v[0] for v in lotes), Decimal("0"))
    db.flush()
    return materiales


def _asegurar_entradas_kardex(db, tenant_id, materiales, usuario) -> None:
    """Kardex de entrada_compra por cada lote (coherente con el stock)."""
    for coil_id, lote, mat_code, cantidad, *_resto in LOTES:
        mat = materiales[mat_code]
        stock = db.scalar(
            select(StockItem).where(
                StockItem.tenant_id == tenant_id, StockItem.coil_id == coil_id
            )
        )
        ya_registrada = db.scalar(
            select(MaterialTransaction).where(
                MaterialTransaction.tenant_id == tenant_id,
                MaterialTransaction.stock_item_id == stock.id,
                MaterialTransaction.tipo == "entrada_compra",
            )
        )
        if ya_registrada is not None:
            continue
        db.add(
            MaterialTransaction(
                tenant_id=tenant_id,
                material_id=mat.id,
                stock_item_id=stock.id,
                tipo="entrada_compra",
                cantidad=Decimal(cantidad),
                cantidad_anterior=Decimal("0"),
                cantidad_nueva=Decimal(cantidad),
                motivo="Recepcion de material",
                documento_referencia=f"ALB-{lote}",
                realizado_por=usuario.id if usuario else tenant_id,
            )
        )
    db.flush()


def _asegurar_piezas(db: Session, tenant_id) -> dict[str, ManufacturingModel]:
    piezas: dict[str, ManufacturingModel] = {}
    for code, name, material_code, checks in PIEZAS:
        modelo = db.scalar(
            select(ManufacturingModel).where(
                ManufacturingModel.tenant_id == tenant_id,
                ManufacturingModel.code == code,
            )
        )
        if modelo is None:
            modelo = ManufacturingModel(
                tenant_id=tenant_id,
                code=code,
                name=name,
                description=f"Pieza del catalogo de estanterias: {name}.",
                material_code=material_code,
                is_active=True,
            )
            db.add(modelo)
            db.flush()
            for pos, (nombre, tipo, tool, nominal, tp, tm, critico) in enumerate(checks, 1):
                db.add(
                    QualityPlanCheck(
                        manufacturing_model_id=modelo.id,
                        position=pos,
                        name=nombre,
                        tipo=tipo,
                        tool_id=tool,
                        nominal_value=Decimal(nominal) if nominal else None,
                        tolerance_plus=Decimal(tp) if tp else None,
                        tolerance_minus=Decimal(tm) if tm else None,
                        is_critical=critico,
                    )
                )
            db.flush()
        piezas[code] = modelo
    return piezas


def _asegurar_productos(db, tenant_id, piezas, materiales) -> dict[str, Product]:
    productos: dict[str, Product] = {}
    for code, name, desc, componentes in PRODUCTOS:
        prod = db.scalar(
            select(Product).where(Product.tenant_id == tenant_id, Product.code == code)
        )
        if prod is None:
            prod = Product(
                tenant_id=tenant_id,
                code=code,
                name=name,
                description=desc,
                is_active=True,
            )
            db.add(prod)
            db.flush()
            for pos, (tipo, ref, cantidad) in enumerate(componentes, 1):
                db.add(
                    _componente_producto(prod, tipo, ref, cantidad, pos, piezas, materiales)
                )
            db.flush()
        productos[code] = prod
    return productos


def _componente_producto(prod, tipo, ref, cantidad, pos, piezas, materiales):
    from app.models import ProductComponent

    if tipo == "pieza":
        return ProductComponent(
            product_id=prod.id,
            manufacturing_model_id=piezas[ref].id,
            quantity=Decimal(cantidad),
            unit="uds",
            position=pos,
        )
    return ProductComponent(
        product_id=prod.id,
        material_id=materiales[ref].id,
        quantity=Decimal(cantidad),
        unit=materiales[ref].unit,
        position=pos,
    )


def _crear_ordenes(db, tenant_id, productos, piezas, materiales, operario) -> dict[str, Order]:
    """2 ordenes activas + 1 completada (referencia para el historico)."""
    ordenes: dict[str, Order] = []
    definiciones = [
        ("OP-EST-2601", "active", "Ferreteria Norte S.L.", 7, [
            (1, "EST-TITAN", "LARGUERO-E27", "FLEJE-D265-18", "DOBL-1",
             "80", "30", "in_progress", "2.7"),
            (2, "EST-PORTICO", "MONTANTE-P50", "FLEJE-D265-18", "PUNZ-1",
             "120", "0", "pending", "3.0"),
        ]),
        ("OP-EST-2602", "active", "Logistica Vallecas S.A.", 14, [
            (1, "EST-VOLADIZO", "COLUMNA-CNT", "PERFIL-U100", "CORTE-1",
             "40", "0", "pending", "4.0"),
            (2, "EST-ALTILLO", "VIGA-SIGMA", "ACERO-S355", "GALV-1",
             "60", "12", "in_progress", "2.7"),
        ]),
        ("OP-EST-2600", "completed", "Almacenes Duero S.A.", -5, [
            (1, "EST-PORTICO", "MONTANTE-P50", "FLEJE-D265-18", "PUNZ-1",
             "100", "100", "completed", "3.0"),
            (2, "EST-TITAN", "LARGUERO-E27", "FLEJE-D265-18", "DOBL-1",
             "60", "60", "completed", "2.7"),
        ]),
    ]

    for numero, estado, cliente, dias_entrega, lineas in definiciones:
        orden = db.scalar(select(Order).where(Order.numero == numero))
        if orden is None:
            orden = Order(
                tenant_id=tenant_id,
                numero=numero,
                estado=estado,
                cliente=cliente,
                fecha_entrega=datetime.now(UTC) + timedelta(days=dias_entrega),
                notas="Orden del catalogo de estanterias (demo).",
            )
            db.add(orden)
            db.flush()
            for linea in lineas:
                (linea_num, prod_code, modelo_code, mat_code, puesto,
                 total, producido, estado_linea, metros) = linea
                pieza = piezas[modelo_code]
                mat = materiales[mat_code]
                db.add(
                    OrderLine(
                        order_id=orden.id,
                        linea_numero=linea_num,
                        product_id=productos[prod_code].id,
                        modelo_id=pieza.id,
                        material_id=mat.id,
                        workstation_id=puesto,
                        estado=estado_linea,
                        total_quantity=Decimal(total),
                        produced_quantity=Decimal(producido),
                        real_time=Decimal("0"),
                        meters_per_piece=Decimal(metros),
                        target_material_qty=_objetivo_material(mat, Decimal(total), metros),
                        target_material_unit=mat.unit,
                    )
                )
            db.flush()
        ordenes.append(orden)

    return {"activa_1": ordenes[0], "activa_2": ordenes[1], "completada": ordenes[2]}


def _historico(db, tenant_id, ordenes, piezas, materiales, operario, materiales_user) -> None:
    """Trazas de la orden completada: logs, consumos, kardex, calidad, incidencia."""
    orden = ordenes["completada"]
    lineas = {ln.linea_numero: ln for ln in orden.lines}
    linea_1 = lineas[1]
    linea_2 = lineas[2]

    if db.scalar(select(ProductionLog).where(ProductionLog.order_id == orden.id)) is None:
        base = datetime.now(UTC) - timedelta(days=5)
        eventos = [
            (linea_1, "start", Decimal("0"), 0),
            (linea_1, "produce", Decimal("60"), 90),
            (linea_1, "produce", Decimal("40"), 170),
            (linea_1, "finish", Decimal("100"), 190),
            (linea_2, "start", Decimal("0"), 220),
            (linea_2, "produce", Decimal("60"), 310),
            (linea_2, "finish", Decimal("60"), 330),
        ]
        for linea, accion, cantidad, minutos in eventos:
            db.add(
                ProductionLog(
                    tenant_id=tenant_id,
                    order_id=orden.id,
                    line_id=linea.id,
                    operator_id=operario.id,
                    timestamp=base + timedelta(minutes=minutos),
                    action=accion,
                    quantity=cantidad,
                    metadata_={"source": "seed", "poste": linea.workstation_id},
                    shift="manana",
                )
            )
        db.flush()

    # kg/ud = ancho_desarrollado x espesor x densidad x largo
    # puntal 265x1,8x3,0m = 11,20 kg/ud; larguero 265x1,8x2,7m = 10,08 kg/ud
    consumos = [
        (linea_1, "FLEJE-D265-18", "COIL-FD265-002", "1120", "100",
         "11.200000", "3.0"),
        (linea_2, "FLEJE-D265-18", "COIL-FD265-003", "605", "60",
         "10.080000", "2.7"),
    ]
    for linea, mat_code, coil_id, cantidad, producido, kg_pieza, metros in consumos:
        mat = materiales[mat_code]
        stock = db.scalar(
            select(StockItem).where(
                StockItem.tenant_id == tenant_id, StockItem.coil_id == coil_id
            )
        )
        ya = db.scalar(
            select(MaterialConsumo).where(
                MaterialConsumo.order_line_id == linea.id,
                MaterialConsumo.material_id == mat.id,
            )
        )
        if ya is not None:
            continue
        cantidad_dec = Decimal(cantidad)
        stock.cantidad_disponible -= cantidad_dec
        mat.stock_current = sum(
            db.execute(
                select(StockItem.cantidad_disponible).where(
                    StockItem.material_id == mat.id
                )
            ).scalars().all(),
            Decimal("0"),
        )
        total_cost = (cantidad_dec * mat.cost_per_unit).quantize(Decimal("0.01"))
        db.add(
            MaterialConsumo(
                tenant_id=tenant_id,
                order_id=orden.id,
                order_line_id=linea.id,
                workstation_id=linea.workstation_id,
                material_id=mat.id,
                stock_item_id=stock.id,
                lote=stock.lote,
                consumed_quantity=cantidad_dec,
                unit=mat.unit,
                produced_quantity=Decimal(producido),
                meters_per_piece=Decimal(metros),
                kg_por_pieza=Decimal(kg_pieza),
                calculation_method="bom_static",
                cost_per_unit=mat.cost_per_unit,
                total_cost=total_cost,
                tipo="automatico",
                observaciones="Consumo de la orden de estanterias (historico demo).",
                operator_id=operario.id,
                date=datetime.now(UTC) - timedelta(days=5),
            )
        )
        db.add(
            MaterialTransaction(
                tenant_id=tenant_id,
                material_id=mat.id,
                stock_item_id=stock.id,
                tipo="salida_produccion",
                cantidad=cantidad_dec,
                cantidad_anterior=stock.cantidad_disponible + cantidad_dec,
                cantidad_nueva=stock.cantidad_disponible,
                orden_id=orden.id,
                linea_orden_id=linea.id,
                motivo="Consumo en produccion",
                realizado_por=operario.id,
            )
        )
        db.flush()

    # Costes: se derivan de los consumos y los tiempos registrados (líneas y
    # cabecera), nunca cifras escritas a mano
    reparar_costes_demo(db, tenant_id)

    _calidad_historica(db, tenant_id, orden, piezas, materiales, operario)
    _incidencia_historica(db, tenant_id, orden, operario)


def _calidad_historica(db, tenant_id, orden, piezas, materiales, operario) -> None:
    if db.scalar(select(QualityRecord).where(QualityRecord.order_id == orden.id)) is not None:
        return
    lineas = {ln.linea_numero: ln for ln in orden.lines}
    casos = [
        (lineas[1], "MONTANTE-P50", "approved", "Largo 3001.5 mm dentro de tolerancia."),
        (lineas[2], "LARGUERO-E27", "rejected", "Estampado con rebaba en el borde."),
    ]
    for linea, modelo_code, estado, notas in casos:
        modelo = piezas[modelo_code]
        registro = QualityRecord(
            tenant_id=tenant_id,
            order_id=orden.id,
            workstation_id=linea.workstation_id,
            operator_id=operario.id,
            manufacturing_model_id=modelo.id,
            overall_status=estado,
            notes=notas,
        )
        db.add(registro)
        db.flush()
        for check in modelo.quality_plan:
            valor = check.nominal_value or Decimal("0")
            aprobado = estado == "approved"
            db.add(
                QualityMeasurement(
                    quality_record_id=registro.id,
                    check_name=check.name,
                    value_entered={"valor": str(valor), "unidad": check.tool_id or "n/a"},
                    is_passed=aprobado,
                    nominal=check.nominal_value,
                    tol_plus=check.tolerance_plus,
                    tol_minus=check.tolerance_minus,
                )
            )
    db.flush()


def _incidencia_historica(db, tenant_id, orden, operario) -> None:
    ya = db.scalar(
        select(Incidencia).where(
            Incidencia.tenant_id == tenant_id,
            Incidencia.descripcion.like("%tornillo automatico%"),
        )
    )
    if ya is not None:
        return
    ahora = datetime.now(UTC)
    incidencia = Incidencia(
        tenant_id=tenant_id,
        order_id=orden.id,
        linea_id="PUNZ-1",
        puesto="PUNZ-1",
        operario_id=operario.id,
        descripcion="Atasco en el colocado automatico de tornillo en PUNZ-1.",
        tipo="maquina",
        estado="resuelta",
        resolucion_tipo="reparacion",
        resolucion_descripcion="Se regulo el empujador y se cambio el sensor de posicion.",
        tiempo_parada_min=Decimal("25.00"),
        coste=Decimal("19.17"),
    )
    db.add(incidencia)
    db.flush()
    for estado, comentario, minutos in [
        ("abierta", "Reportado por el operario de turno.", 0),
        ("en_revision", "Supervision asignada.", 10),
        ("resuelta", "Equipo de mantenimiento lo deja operativo.", 35),
    ]:
        db.add(
            IncidenciaHistorial(
                incidencia_id=incidencia.id,
                estado=estado,
                usuario_id=operario.id,
                timestamp=ahora - timedelta(days=5) + timedelta(minutes=minutos),
                comentario=comentario,
            )
        )
    db.flush()
