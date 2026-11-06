"""Auditoría T-029: hallazgos reproducibles de las PR #49–#52 (Steelworks).

Cada test de este fichero describe el comportamiento CORRECTO y por tanto
FALLA en main a fecha de la auditoría (2026-11-06). No tocan app/: solo
reproducen el defecto.

Hallazgos:
  H1  GET /incidencias/upload-session/{id} y .../photo se sirven sin token.
  H2  Esos mismos endpoints no filtran por tenant: con el session_id de otra
      empresa devuelven estado y foto (IDOR entre tenants).
  H3  unlink_coil no comprueba el tenant de la orden (oráculo de existencia
      entre tenants; create_retal sí lo comprueba).
  H4  create_retal/medir_bobina aceptan una medición SUPERIOR al saldo del
      sistema y suben el stock: material ya consumido y costeado reaparece.
  H5  link_coil no es atómico: el paso "misma máquina" llama a unlink_coil,
      que hace commit; un fallo posterior deja la bobina desvinculada de las
      dos órdenes (commit parcial).
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import incidencias as inc_router
from tests.helpers import (
    make_material,
    make_order,
    make_order_line,
    make_stock_item,
    make_tenant,
    make_user,
)

PNG_DEMO = b"\x89PNG\r\n\x1a\n" + b"data-de-prueba"


def _override(db_session):
    def _gen():
        yield db_session

    return _gen


@pytest.fixture()
def otra(db_session):
    return make_tenant(db_session, name="Otra Empresa")


# ── H1/H2: sesiones de subida de fotos sin auth y sin tenant ──────────────


def _sesion_de(db_session, tenant, user):
    from app.services.incidencia_uploads import adjuntar_foto, crear_sesion

    sesion = crear_sesion(db_session, tenant_id=tenant.id, operario_id=user.id)
    adjuntar_foto(db_session, session_id=sesion.session_id, buf=PNG_DEMO)
    return sesion


def test_h1_estado_de_sesion_exige_token(db_session, tenant, user):
    """El estado de una sesión (y su foto en data URL) no puede ser público."""
    sesion = _sesion_de(db_session, tenant, user)
    app.dependency_overrides[inc_router.get_db] = _override(db_session)
    try:
        anonimo = TestClient(app)  # sin Authorization
        r = anonimo.get(f"/api/v1/incidencias/upload-session/{sesion.session_id}")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code in (401, 403), (
        f"sin token devolvió {r.status_code}: {r.text[:200]}"
    )


def test_h1_foto_de_sesion_exige_token(db_session, tenant, user):
    sesion = _sesion_de(db_session, tenant, user)
    app.dependency_overrides[inc_router.get_db] = _override(db_session)
    try:
        anonimo = TestClient(app)
        r = anonimo.get(f"/api/v1/incidencias/upload-session/{sesion.session_id}/photo")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code in (401, 403), (
        f"la foto se sirve sin token (HTTP {r.status_code}, {len(r.content)} bytes)"
    )


def test_h2_sesion_de_otra_empresa_da_404(db_session, tenant, user, otra):
    """Un token válido de la empresa A no puede leer la sesión de la empresa B."""
    from tests.helpers import authed_client_for

    user_b = make_user(db_session, otra, email="op-b@test.local", role="operator")
    sesion_b = _sesion_de(db_session, otra, user_b)

    app.dependency_overrides[inc_router.get_db] = _override(db_session)
    try:
        client_a = authed_client_for(db_session, user)
        r = client_a.get(f"/api/v1/incidencias/upload-session/{sesion_b.session_id}")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 404, (
        f"token de otra empresa leyó la sesión: HTTP {r.status_code} {r.text[:200]}"
    )


# ── H3: unlink_coil no comprueba el tenant de la orden ────────────────────


def test_h3_unlink_rechaza_orden_de_otra_empresa(db_session, tenant, user, otra):
    from app.services.inventory import link_coil, unlink_coil

    material = make_material(db_session, tenant, code="PROPIO", cost=2.0)
    bobina = make_stock_item(db_session, tenant, material, cantidad=100, lote="L-P")
    orden = make_order(db_session, tenant, numero="OP-PROPIA")
    linea = make_order_line(db_session, orden, workstation="LINEA-1")
    link_coil(
        db_session, tenant.id, user.id,
        stock_item_id=bobina.id, order_id=orden.id, line_id=linea.id,
    )

    orden_ajena = make_order(db_session, otra, numero="OP-AJENA")
    linea_ajena = make_order_line(db_session, orden_ajena, workstation="LINEA-1")

    with pytest.raises(ValueError, match="no existe"):
        unlink_coil(
            db_session, tenant.id, user.id,
            stock_item_id=bobina.id, order_id=orden_ajena.id, line_id=linea_ajena.id,
        )


# ── H4: medir por encima del sistema crea material ────────────────────────


def _montada(db_session, tenant, peso=100.0):
    material = make_material(db_session, tenant, code="M-MED", cost=2.0)
    bobina = make_stock_item(
        db_session, tenant, material, cantidad=peso, lote="L-MED", ancho=122, espesor=0.5
    )
    orden = make_order(db_session, tenant, numero="OP-MED")
    linea = make_order_line(db_session, orden, workstation="LINEA-1")
    linea.active_coil_id = bobina.id
    linea.active_coil_code = bobina.coil_id
    db_session.commit()
    return bobina, orden, linea


def test_h4_create_retal_no_inventa_kilos(db_session, tenant, user, monkeypatch):
    """Si el metro da MÁS kg que el saldo del sistema, la bobina no engorda.

    La medición nunca puede crear material: o se acota al saldo, o se rechaza
    con un error, o se registra la reversión explícita del consumo ya apuntado.
    Subir el stock en silencio descuadra inventario y coste a la vez.
    """
    from app.services import coil_math
    from app.services.inventory import create_retal

    bobina, orden, linea = _montada(db_session, tenant, peso=100.0)
    # El FIFO ya consumió 30 kg (y la orden los tiene costeados en su línea).
    bobina.cantidad_disponible = Decimal("70")
    db_session.commit()

    # El operario mide con el metro y le salen los 100 kg del inicio.
    monkeypatch.setattr(coil_math, "peso_desde_radio_mm", lambda **_: 100.0)

    create_retal(
        db_session, tenant.id, user.id,
        stock_item_id=bobina.id, radio_mm=50.0, order_id=orden.id, line_id=linea.id,
    )

    db_session.refresh(bobina)
    assert bobina.cantidad_disponible <= Decimal("70"), (
        "la medición resucitó kilos: el stock pasó de 70 a "
        f"{bobina.cantidad_disponible} kg sin asiento de reversión del consumo"
    )


def test_h4_medir_bobina_no_inventa_kilos(db_session, tenant, user, monkeypatch):
    from app.services import coil_math
    from app.services.medicion import medir_bobina

    bobina, orden, linea = _montada(db_session, tenant, peso=100.0)
    bobina.cantidad_disponible = Decimal("70")
    db_session.commit()

    monkeypatch.setattr(coil_math, "peso_desde_radio_mm", lambda **_: 100.0)

    medir_bobina(
        db_session, tenant.id, user.id,
        stock_item_id=bobina.id, radio_mm=50.0, order_id=orden.id, line_id=linea.id,
    )

    db_session.refresh(bobina)
    assert bobina.cantidad_disponible <= Decimal("70"), (
        "el cierre de turno resucitó kilos: el stock pasó de 70 a "
        f"{bobina.cantidad_disponible} kg"
    )


# ── H5: link_coil no es atómico (commit dentro de unlink_coil) ────────────


def test_h5_link_coil_no_deja_la_bobina_suelta_si_falla(db_session, tenant, user, monkeypatch):
    """Misma máquina, cambio de orden: o queda vinculada a la nueva, o a la vieja.

    Hoy link_coil llama a unlink_coil (que hace commit) y después sigue; si
    algo falla en medio, la bobina queda desvinculada de las dos órdenes y el
    reembolso ya está confirmado.
    """
    from app.services import inventory

    material = make_material(db_session, tenant, code="M-ATOM", cost=2.0)
    bobina = make_stock_item(db_session, tenant, material, cantidad=800, lote="L-ATOM")
    orden_a = make_order(db_session, tenant, numero="OP-A")
    linea_a = make_order_line(db_session, orden_a, workstation="LINEA-1")
    orden_b = make_order(db_session, tenant, numero="OP-B")
    linea_b = make_order_line(db_session, orden_b, workstation="LINEA-1")

    inventory.link_coil(
        db_session, tenant.id, user.id,
        stock_item_id=bobina.id, order_id=orden_a.id, line_id=linea_a.id,
    )

    llamadas = {"n": 0}
    original = inventory.validar_material_compatible

    def _falla_en_la_segunda(db, bob, linea):
        llamadas["n"] += 1
        if llamadas["n"] >= 2:
            raise RuntimeError("fallo tras el commit interno de unlink_coil")
        return original(db, bob, linea)

    monkeypatch.setattr(inventory, "validar_material_compatible", _falla_en_la_segunda)

    with pytest.raises(RuntimeError):
        inventory.link_coil(
            db_session, tenant.id, user.id,
            stock_item_id=bobina.id, order_id=orden_b.id, line_id=linea_b.id,
        )

    db_session.expire_all()
    db_session.refresh(linea_a)
    assert linea_a.active_coil_id == bobina.id, (
        "commit parcial: la bobina quedó desvinculada de la orden A y no llegó "
        "a vincularse a la B"
    )
