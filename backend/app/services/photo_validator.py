"""Validación de fotos de incidencias por MAGIC BYTES (portado de kavana-manufacturing).

No confía en el mimetype declarado por el cliente (falseable). Formatos
aceptados: PNG, JPEG, WebP y GIF. Límite 10MB (el móvil/tablet comprime
antes; los 10MB son red de seguridad para cámaras sin compresión).
"""

MAX_FOTO_BYTES = 10 * 1024 * 1024  # 10MB

_MIME_POR_TIPO = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}


def detectar_tipo_imagen(buf: bytes) -> str | None:
    """Detecta el tipo real por magic bytes; None si no es imagen conocida."""
    if not buf or len(buf) < 6:
        return None

    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if len(buf) >= 8 and buf[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    # JPEG: FF D8 FF
    if buf[:3] == b"\xff\xd8\xff":
        return "jpeg"
    # WebP: 'RIFF' <size> 'WEBP'
    if len(buf) >= 12 and buf[:4] == b"RIFF" and buf[8:12] == b"WEBP":
        return "webp"
    # GIF: 'GIF87a' | 'GIF89a'
    if buf[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def validar_foto(buf: bytes | None) -> dict:
    """Devuelve {ok: True, mime, size} o {ok: False, reason}."""
    if not buf or len(buf) == 0:
        return {"ok": False, "reason": "No se ha subido ningún archivo"}
    if len(buf) > MAX_FOTO_BYTES:
        mb = MAX_FOTO_BYTES // (1024 * 1024)
        return {
            "ok": False,
            "reason": f"La imagen supera el tamaño máximo de {mb}MB",
        }
    tipo = detectar_tipo_imagen(buf)
    if tipo is None:
        return {
            "ok": False,
            "reason": "Solo se permiten imágenes (PNG, JPEG, WebP o GIF)",
        }
    return {"ok": True, "mime": _MIME_POR_TIPO[tipo], "size": len(buf)}
