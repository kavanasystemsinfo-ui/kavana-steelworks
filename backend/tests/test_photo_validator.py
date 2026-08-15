"""Tests de validación de fotos por magic bytes (portado de kavana-manufacturing).

La validación NO confía en el mimetype declarado por el cliente: comprueba
los bytes reales del archivo (PNG, JPEG, WebP, GIF) y el tamaño (10MB).
"""

from app.services.photo_validator import MAX_FOTO_BYTES, detectar_tipo_imagen, validar_foto


def test_detectar_png():
    buf = b"\x89PNG\r\n\x1a\n" + b"resto"
    assert detectar_tipo_imagen(buf) == "png"


def test_detectar_jpeg():
    assert detectar_tipo_imagen(b"\xff\xd8\xff\xe0" + b"x" * 10) == "jpeg"


def test_detectar_webp():
    # RIFF <4 bytes tamaño> WEBP
    buf = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"vp8 "
    assert detectar_tipo_imagen(buf) == "webp"


def test_detectar_gif():
    assert detectar_tipo_imagen(b"GIF87a" + b"x" * 10) == "gif"
    assert detectar_tipo_imagen(b"GIF89a" + b"x" * 10) == "gif"


def test_detectar_rechaza_no_imagen():
    assert detectar_tipo_imagen(b"hello world") is None
    assert detectar_tipo_imagen(b"\x00\x01\x02\x03\x04\x05") is None
    assert detectar_tipo_imagen(b"") is None
    assert detectar_tipo_imagen(b"abc") is None  # menos de 6 bytes


def test_validar_foto_ok_devuelve_mime_y_size():
    buf = b"\x89PNG\r\n\x1a\n" + b"data"
    r = validar_foto(buf)
    assert r["ok"] is True
    assert r["mime"] == "image/png"
    assert r["size"] == len(buf)


def test_validar_foto_vacia():
    r = validar_foto(b"")
    assert r["ok"] is False
    assert "archivo" in r["reason"].lower()


def test_validar_foto_none():
    r = validar_foto(None)
    assert r["ok"] is False


def test_validar_foto_demasiado_grande():
    r = validar_foto(b"\xff\xd8\xff" + b"0" * (MAX_FOTO_BYTES + 1))
    assert r["ok"] is False
    assert "tamaño" in r["reason"].lower()


def test_validar_foto_rechaza_texto():
    r = validar_foto(b"esto no es una imagen, es texto plano")
    assert r["ok"] is False
    assert "imágenes" in r["reason"]
