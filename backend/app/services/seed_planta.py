"""Planta realista de la demo: 8 puestos y 3 operarios por puesto (mañana, tarde, noche).

Idempotente y sin borrar nada: los puestos antiguos se desactivan (su historia se
conserva) y los nuevos se crean o se renombran. El simulador registra cada trabajo a
nombre del operario del puesto y del turno (`operario_de`).
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, Workstation, WorkstationGroup

# (código, nombre, grupo, color, coste/hora, método de registro, piezas/hora nominal)
PUESTOS_PLANTA = [
    ("P-313", "Perfiladora 313 (travesaños)", "Perfilado", "#2980b9", "50", "quantity", "150"),
    ("P-K300", "Perfiladora K300 (puntales y pilares)", "Perfilado", "#3498db", "52",
     "quantity", "120"),
    ("L-3015", "Láser 3015", "Corte", "#f39c12", "48", "quantity", "60"),
    ("PU-80", "Punzonadora PU-80", "Punzonado", "#8e44ad", "46", "quantity", "40"),
    ("PL-220", "Plegadora PL-220", "Doblado", "#2c3e50", "47", "quantity", "30"),
    ("RB-1", "Robot de soldadura", "Soldadura", "#e74c3c", "42", "timer", "25"),
    ("AR-1", "Estación de armado", "Ensamble", "#1abc9c", "36", "quantity", "12"),
    ("ES-2", "Esmeriladora E-2", "Terminación", "#16a085", "34", "quantity", "20"),
]

# Puestos de siembras anteriores: se desactivan, no se borran
PUESTOS_ANTIGUOS = (
    "CORTE-1", "PUNZ-1", "DOBL-1", "SOL-1", "GALV-1", "MONT-1", "MONT-2",
    "PERF-1", "PERF-2", "LASER-1", "PLEG-1", "SOLD-1", "ESME-1",
    "PERF-313", "PERF-K300", "LASER-3015", "PUNZ-80", "PLEG-220", "ROBOT-1", "ARMA-1", "ESME-2",
    "LINEA-1", "LINEA-2", "LINEA-3",
)

# Mañana (A, 06-14), tarde (B, 14-22) y noche (C, 22-06) de cada puesto
OPERARIOS = {
    "P-313": ("Juan Hernández Aguilar", "Antonio Ruiz Ferrer", "Manuel Soler Iglesias"),
    "P-K300": ("Francisco Navarro Gil", "José Luis Moreno Prats", "Pedro Cano Valero"),
    "L-3015": ("Javier Ortega Molina", "Miguel Ángel Serrano Pons", "Rafael Domínguez Lara"),
    "PU-80": ("David Castillo Ramos", "Carlos Jiménez Sanz", "Sergio Marín Blasco"),
    "PL-220": ("Alberto Vidal Climent", "Fernando Gómez Olmos", "Raúl Peña Escrivá"),
    "RB-1": ("Pablo Herrero Cuesta", "Jorge Alonso Beltrán", "Andrés Medina Soria"),
    "AR-1": ("Luis Romero Giner", "Enrique Torres Millán", "Ismael Vega Cortés"),
    "ES-2": ("Vicente Campos Roca", "Alejandro Gallego Ibáñez", "Óscar Santos Mora"),
}

# La cuenta del botón "Operario" de la demo es ya un operario real de la plantilla
EMAIL_FIJO = {"Juan Hernández Aguilar": "operario@demo.local"}

# El resto de cuentas demo también con nombre de persona (el correo no cambia)
NOMBRES_CUENTAS = {
    "supervisor@demo.local": "Ramón Gil Tormo",
    "materias@demo.local": "Tomás Beltrán Roig",
    "admin@demo.local": "Víctor Almagro Pons",
}

TURNOS = ("A", "B", "C")


def _slug(nombre: str) -> str:
    if nombre in EMAIL_FIJO:
        return EMAIL_FIJO[nombre]
    tabla = str.maketrans("áéíóúñ", "aeioun")
    return ".".join(nombre.lower().translate(tabla).split()[:2]) + "@demo.local"


def email_operario(puesto: str, turno: str) -> str | None:
    """Correo del operario del puesto en ese turno (A, B o C), o None si no tiene plantilla."""
    nombres = OPERARIOS.get(puesto)
    return _slug(nombres[TURNOS.index(turno)]) if nombres else None


def turno_de(momento: datetime) -> str:
    from app.services.shifts import TZ_PLANTA

    hora = momento.astimezone(TZ_PLANTA).hour
    return "A" if 6 <= hora < 14 else "B" if 14 <= hora < 22 else "C"


def operario_de(
    cache: dict[str, User], db: Session, tenant_id, puesto: str, momento: datetime
) -> User | None:
    """Operario del puesto en el turno de `momento`; None si el puesto no tiene plantilla."""
    email = email_operario(puesto, turno_de(momento))
    if email is None:
        return None
    if email not in cache:
        usuario = db.scalar(
            select(User).where(
                User.tenant_id == tenant_id, User.email == email, User.is_active.is_(True)
            )
        )
        if usuario is None:
            return None
        cache[email] = usuario
    return cache[email]


def asegurar_planta_realista(db: Session, tenant_id) -> dict:
    """Crea los 8 puestos y los 24 operarios, y desactiva los puestos antiguos."""
    from app.services.auth import hash_password

    cambios = {"puestos": 0, "operarios": 0, "desactivados": 0}
    grupos: dict[str, WorkstationGroup] = {}
    for code, nombre, grupo, color, coste, metodo, ritmo in PUESTOS_PLANTA:
        if grupo not in grupos:
            g = db.scalar(
                select(WorkstationGroup).where(
                    WorkstationGroup.tenant_id == tenant_id, WorkstationGroup.name == grupo
                )
            )
            if g is None:
                g = WorkstationGroup(tenant_id=tenant_id, name=grupo, color=color)
                db.add(g)
                db.flush()
            grupos[grupo] = g
        puesto = db.scalar(
            select(Workstation).where(
                Workstation.tenant_id == tenant_id, Workstation.code == code
            )
        )
        if puesto is None:
            db.add(
                Workstation(
                    tenant_id=tenant_id, group_id=grupos[grupo].id, code=code, name=nombre,
                    color=color, hourly_cost=Decimal(coste), registration_method=metodo,
                    piezas_hora_nominal=Decimal(ritmo), is_active=True,
                )
            )
            cambios["puestos"] += 1
        else:
            puesto.name = nombre
            puesto.group_id = grupos[grupo].id
            if puesto.piezas_hora_nominal is None:
                puesto.piezas_hora_nominal = Decimal(ritmo)
            if not puesto.is_active:
                puesto.is_active = True

    for code in PUESTOS_ANTIGUOS:
        antiguo = db.scalar(
            select(Workstation).where(
                Workstation.tenant_id == tenant_id, Workstation.code == code
            )
        )
        if antiguo is not None and antiguo.is_active:
            antiguo.is_active = False
            cambios["desactivados"] += 1

    for nombres in OPERARIOS.values():
        for nombre in nombres:
            email = _slug(nombre)
            usuario = db.scalar(select(User).where(User.email == email))
            if usuario is None:
                db.add(
                    User(
                        tenant_id=tenant_id, email=email, name=nombre,
                        password_hash=hash_password("kavana"), role="operator",
                    )
                )
                cambios["operarios"] += 1
            else:
                usuario.name = nombre
    for email, nombre in NOMBRES_CUENTAS.items():
        cuenta = db.scalar(select(User).where(User.email == email))
        if cuenta is not None:
            cuenta.name = nombre
    db.flush()
    cambios["ordenes_cerradas"] = _cerrar_ordenes_de_puestos_antiguos(db, tenant_id)
    cambios["bobinas_movidas_almacen"] = _mover_bobinas_puestos_antiguos_a_almacen(db, tenant_id)
    return cambios


def _mover_bobinas_puestos_antiguos_a_almacen(db: Session, tenant_id) -> int:
    """Mueve bobinas libres (no montadas en ninguna línea) que estén en puestos antiguos a ALMACEN.

    Es idempotente: solo mueve las que no están ya en ALMACEN y no están montadas.
    Usa move_coil del servicio de recepción para registrar el traslado en Kardex.
    """
    from app.models import OrderLine, StockItem, Workstation
    from app.services.receiving import move_coil

    # Códigos de puestos desactivados
    inactivos = {
        w.code
        for w in db.scalars(
            select(Workstation).where(
                Workstation.tenant_id == tenant_id, Workstation.is_active.is_(False)
            )
        )
    }
    if not inactivos:
        return 0

    # Bobinas activas montadas en líneas (no se pueden mover)
    montadas = {
        ln.active_coil_id
        for ln in db.scalars(
            select(OrderLine).where(OrderLine.active_coil_id.is_not(None))
        )
    }

    # Bobinas en ubicaciones de puestos antiguos que no están montadas
    bobinas_a_mover = db.scalars(
        select(StockItem).where(
            StockItem.tenant_id == tenant_id,
            StockItem.estado == "activo",
            StockItem.ubicacion.in_(inactivos),
            StockItem.id.not_in(montadas),
        )
    ).all()

    if not bobinas_a_mover:
        return 0

    # Usuario system para el movimiento
    from app.services.receiving import _system_user
    user_id = _system_user(db, tenant_id)

    movidas = 0
    for bobina in bobinas_a_mover:
        try:
            move_coil(db, tenant_id, user_id, stock_item_id=bobina.id, nueva_ubicacion="ALMACEN")
            movidas += 1
        except ValueError:
            db.rollback()
            # Si falla una, seguimos con las demás
            continue
    return movidas


# Recetas que recorren los 8 puestos (como RECETAS_FLUJO, con los puestos nuevos)
RECETAS_PLANTA = [
    ("OP-EST-2811", "Metálicas del Sur S.A.", "EST-PORTICO", "MONTANTE-P50",
     "FLEJE-D265-18", "3.0", "80", ["P-313", "PU-80", "PL-220", "AR-1"]),
    ("OP-EST-2812", "Almacenes Rodrigo e Hijos S.A.", "EST-TITAN", "LARGUERO-E27",
     "FLEJE-D265-18", "2.7", "60", ["P-K300", "PL-220", "RB-1", "ES-2"]),
    ("OP-EST-2813", "Distribuciones Valencianas S.L.", "EST-VOLADIZO", "COLUMNA-CNT",
     "PERFIL-U100", "4.0", "40", ["L-3015", "RB-1", "ES-2", "AR-1"]),
    ("OP-EST-2814", "Logística y Montajes del Mediterráneo S.L.", "EST-ALTILLO", "VIGA-SIGMA",
     "ACERO-S355", "2.7", "12", ["L-3015", "PU-80", "PL-220", "RB-1"]),
]


def _cerrar_ordenes_de_puestos_antiguos(db: Session, tenant_id) -> int:
    """Cancela (estado reversible, sin borrar) las órdenes activas que solo usan puestos
    desactivados y suelta sus bobinas, para que el simulador no siga fichando en ellos."""
    from app.models import Order
    from app.services.inventory import unlink_coil

    inactivos = {
        w.code
        for w in db.scalars(
            select(Workstation).where(
                Workstation.tenant_id == tenant_id, Workstation.is_active.is_(False)
            )
        )
    }
    quien = db.scalar(
        select(User).where(User.tenant_id == tenant_id, User.email == "operario@demo.local")
    )
    cerradas = 0
    for orden in db.scalars(
        select(Order).where(Order.tenant_id == tenant_id, Order.estado == "active")
    ):
        lineas = list(orden.lines)
        if not lineas or not all(ln.workstation_id in inactivos for ln in lineas):
            continue
        for ln in lineas:
            if ln.active_coil_id is not None and quien is not None:
                try:
                    unlink_coil(
                        db, tenant_id, quien.id,
                        stock_item_id=ln.active_coil_id, order_id=orden.id, line_id=ln.id,
                    )
                except ValueError:
                    db.rollback()
                    return cerradas
            if ln.estado != "completed":
                ln.estado = "pending"
        orden.estado = "cancelled"
        cerradas += 1
    db.flush()
    return cerradas

