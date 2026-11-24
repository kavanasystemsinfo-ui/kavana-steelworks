"""Caché en memoria de 20 s para los paneles del supervisor.

Se usa en los endpoints (no en los servicios): el operario que acaba de registrar algo ve
siempre datos frescos, y el supervisor, que sondea cada minuto, no repite las mismas
consultas contra Neon (cuya transferencia es limitada). Clave: (tenant, endpoint, parámetros).
"""

import threading
import time
from collections.abc import Callable
from typing import Any

TTL_SECONDS = 20
MAX_ENTRADAS = 200

_cache: dict[tuple, tuple[float, Any]] = {}
_lock = threading.Lock()


def cached_call(tenant_id, endpoint: str, params: tuple, producir: Callable[[], Any]) -> Any:
    """Devuelve el valor de `producir()`, reutilizando el de los últimos 20 s si hay."""
    clave = (str(tenant_id), endpoint, params)
    ahora = time.monotonic()
    with _lock:
        hit = _cache.get(clave)
        if hit and ahora - hit[0] < TTL_SECONDS:
            return hit[1]
    valor = producir()
    with _lock:
        _cache[clave] = (ahora, valor)
        if len(_cache) > MAX_ENTRADAS:  # caducadas primero; si no basta, las más antiguas
            for k in [k for k, (t, _) in _cache.items() if ahora - t >= TTL_SECONDS]:
                del _cache[k]
            while len(_cache) > MAX_ENTRADAS:
                del _cache[min(_cache, key=lambda k: _cache[k][0])]
    return valor


def clear_cache() -> None:
    """Vacía la caché (tests)."""
    with _lock:
        _cache.clear()
