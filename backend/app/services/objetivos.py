"""Objetivos de planta por empresa (panel de mando).

Viven en ``tenant.finances["objetivos"]`` (JSON, sin migración). Lo que la
empresa no haya configurado se completa con valores de referencia, de modo que
el panel siempre tiene contra qué comparar cada indicador.
"""

from app.models import Tenant

# Valores de referencia de una planta de transformado de chapa.
# OEE ≈ disponibilidad × rendimiento × calidad (90 × 88 × 95 ≈ 75 %).
OBJETIVOS_POR_DEFECTO: dict[str, float] = {
    "oee": 75,
    "disponibilidad": 90,
    "rendimiento": 88,
    "calidad": 95,
    "chatarra_max_pct": 3,
}

# Los porcentajes no pueden pasar de 100.
_PORCENTAJES = set(OBJETIVOS_POR_DEFECTO)


def objetivos_tenant(tenant: Tenant) -> dict[str, float]:
    """Objetivos de la empresa, completados con los valores por defecto."""
    guardados = (tenant.finances or {}).get("objetivos") or {}
    return {
        clave: float(guardados.get(clave, defecto))
        for clave, defecto in OBJETIVOS_POR_DEFECTO.items()
    }


def guardar_objetivos(tenant: Tenant, cambios: dict[str, float]) -> dict[str, float]:
    """Valida y guarda los objetivos indicados; devuelve el conjunto completo.

    Solo se aceptan claves conocidas, con valores entre 0 y 100. Las claves que no
    vienen en ``cambios`` conservan su valor actual.
    """
    desconocidas = set(cambios) - set(OBJETIVOS_POR_DEFECTO)
    if desconocidas:
        raise ValueError(f"Objetivos desconocidos: {', '.join(sorted(desconocidas))}")
    for clave, valor in cambios.items():
        if valor < 0 or (clave in _PORCENTAJES and valor > 100):
            raise ValueError(f"{clave} debe estar entre 0 y 100")

    finances = dict(tenant.finances or {})
    objetivos = dict(finances.get("objetivos") or {})
    objetivos.update({clave: float(valor) for clave, valor in cambios.items()})
    finances["objetivos"] = objetivos
    # Reasignar el dict completo: SQLAlchemy no detecta mutaciones dentro de un JSON.
    tenant.finances = finances
    return objetivos_tenant(tenant)
