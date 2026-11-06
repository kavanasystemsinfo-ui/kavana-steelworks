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
    ("PERF-1", "Perfiladora 1", "Perfilado", "#2980b9", "50", "quantity", "150"),
    ("PERF-2", "Perfiladora 2", "Perfilado", "#3498db", "50", "quantity", "120"),
    ("LASER-1", "Corte láser", "Corte", "#f39c12", "48", "quantity", "60"),
    ("PUNZ-1", "Punzonadora", "Punzonado", "#8e44ad", "46", "quantity", "40"),
    ("PLEG-1", "Plegadora CNC", "Doblado", "#2c3e50", "47", "quantity", "30"),
    ("SOLD-1", "Soldadura MIG/MAG", "Soldadura", "#e74c3c", "42", "timer", "25"),
    ("ARMA-1", "Armado y punteado", "Ensamble", "#1abc9c", "36", "quantity", "12"),
    ("ESME-1", "Esmerilado y terminación", "Terminación", "#16a085", "34", "quantity", "20"),
]

# Puestos de siembras anteriores: se desactivan, no se borran
PUESTOS_ANTIGUOS = (
    "CORTE-1", "DOBL-1", "SOL-1", "GALV-1", "MONT-1", "MONT-2", "LINEA-1", "LINEA-2", "LINEA-3",
)

# Mañana (A, 06-14), tarde (B, 14-22) y noche (C, 22-06) de cada puesto
OPERARIOS = {
    "PERF-1": ("Juan Hernández Aguilar", "Antonio Ruiz Ferrer", "Manuel Soler Iglesias"),
    "PERF-2": ("Francisco Navarro Gil", "José Luis Moreno Prats", "Pedro Cano Valero"),
    "LASER-1": ("Javier Ortega Molina", "Miguel Ángel Serrano Pons", "Rafael Domínguez Lara"),
    "PUNZ-1": ("David Castillo Ramos", "Carlos Jiménez Sanz", "Sergio Marín Blasco"),
    "PLEG-1": ("Alberto Vidal Climent", "Fernando Gómez Olmos", "Raúl Peña Escrivá"),
    "SOLD-1": ("Pablo Herrero Cuesta", "Jorge Alonso Beltrán", "Andrés Medina Soria"),
    "ARMA-1": ("Luis Romero Giner", "Enrique Torres Millán", "Ismael Vega Cortés"),
    "ESME-1": ("Vicente Campos Roca", "Alejandro Gallego Ibáñez", "Óscar Santos Mora"),
}

TURNOS = ("A", "B", "C")


def _slug(nombre: str) -> str:
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
            if db.scalar(select(User).where(User.email == email)) is None:
                db.add(
                    User(
                        tenant_id=tenant_id, email=email, name=nombre,
                        password_hash=hash_password("kavana"), role="operator",
                    )
                )
                cambios["operarios"] += 1
    db.flush()
    return cambios


# Recetas que recorren los 8 puestos (como RECETAS_FLUJO, con los puestos nuevos)
RECETAS_PLANTA = [
    ("OP-EST-2801", "Metálicas del Sur S.A.", "EST-PORTICO", "MONTANTE-P50",
     "FLEJE-D265-18", "3.0", "80", ["PERF-1", "PUNZ-1", "PLEG-1", "ARMA-1"]),
    ("OP-EST-2802", "Almacenes Rodrigo e Hijos S.A.", "EST-TITAN", "LARGUERO-E27",
     "FLEJE-D265-18", "2.7", "60", ["PERF-2", "PLEG-1", "SOLD-1", "ESME-1"]),
    ("OP-EST-2803", "Distribuciones Valencianas S.L.", "EST-VOLADIZO", "COLUMNA-CNT",
     "PERFIL-U100", "4.0", "40", ["LASER-1", "SOLD-1", "ESME-1", "ARMA-1"]),
    ("OP-EST-2804", "Logística y Montajes del Mediterráneo S.L.", "EST-ALTILLO", "VIGA-SIGMA",
     "ACERO-S355", "2.7", "12", ["LASER-1", "PUNZ-1", "PLEG-1", "SOLD-1"]),
]
