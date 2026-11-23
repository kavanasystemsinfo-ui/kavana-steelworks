"""Caché en memoria TTL 20s por (tenant, endpoint, params) - thread-safe."""
import json
import threading
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

# Caché global: {cache_key: (timestamp, value)}
_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()
TTL_SECONDS = 20


def _make_key(tenant_id: str, endpoint: str, params: dict) -> str:
    """Clave determinística ordenada."""
    
    def default_serializer(obj):
        """Serializa objetos no-JSON a string."""
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        if hasattr(obj, '__str__'):
            return str(obj)
        return repr(obj)
    
    param_str = json.dumps(params, sort_keys=True, default=default_serializer) if params else ""
    return f"{tenant_id}:{endpoint}:{param_str}"


def cached_20s(endpoint: str):
    """Decorador para cachear respuesta 20s por tenant+endpoint+params.
    
    Uso:
        @cached_20s("turno")
        def get_turno(db, tenant_id, ahora=None):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Asumimos que el primer arg tras db es tenant_id o está en kwargs
            tenant_id = kwargs.get("tenant_id")
            if tenant_id is None and len(args) >= 2:
                tenant_id = args[1]
            if tenant_id is None:
                # Sin tenant_id, no cachear
                return func(*args, **kwargs)
            
            # Extraer params del resto de args/kwargs, EXCLUYENDO db y tenant_id
            params = {k: v for k, v in kwargs.items() if k not in ("db", "tenant_id")}
            # Args posicionales después de db y tenant_id
            if len(args) > 2:
                params["_args"] = args[2:]
            
            key = _make_key(str(tenant_id), endpoint, params)
            now = time.time()
            
            with _cache_lock:
                if key in _cache:
                    ts, value = _cache[key]
                    if now - ts < TTL_SECONDS:
                        return value
                    else:
                        del _cache[key]
            
            # No hay caché válida, ejecutar
            result = func(*args, **kwargs)
            
            with _cache_lock:
                _cache[key] = (now, result)
            
            return result
        return wrapper
    return decorator


def invalidate_tenant(tenant_id: str):
    """Invalida toda la caché de un tenant (útil tras writes)."""
    with _cache_lock:
        keys_to_del = [k for k in _cache if k.startswith(f"{tenant_id}:")]
        for k in keys_to_del:
            del _cache[k]


def clear_cache():
    """Limpia toda la caché (tests)."""
    with _cache_lock:
        _cache.clear()