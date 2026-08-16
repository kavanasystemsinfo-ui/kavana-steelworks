"""Seed de datos demo para la demo pública de Steelworks.

Idempotente: solo crea datos si el tenant demo no existe. Se ejecuta en el
entrypoint de producción para que la demo desplegada tenga datos reales
(material, bobina, orden, operario) sin pasos manuales.

Contenido honesto: datos ficticios de demostración, sin clientes reales.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Material, Order, OrderLine, StockItem, Tenant, User
from app.models.quality import ManufacturingModel, QualityPlanCheck


def _asegurar_modelo_demo(db, tenant_id) -> None:
    """Crea el modelo de calidad demo con su plan si no existe (idempotente)."""
    from sqlalchemy import select

    existente = db.scalar(
        select(ManufacturingModel).where(
            ManufacturingModel.tenant_id == tenant_id,
            ManufacturingModel.code == "PERFIL-DEMO-001",
        )
    )
    if existente is not None:
        return
    modelo = ManufacturingModel(
        tenant_id=tenant_id,
        code="PERFIL-DEMO-001",
        name="Perfil decapado 1.2x1220",
        description="Plantilla demo: controles de calidad del perfil decapado.",
        material_code="ACERO-DC01",
        is_active=True,
    )
    db.add(modelo)
    db.flush()
    checks = [
        ("Largo Total", "numeric", "Cinta métrica", "2000", "10", "10", True),
        ("Acabado superficial", "visual", None, None, None, None, True),
        ("Espesor", "numeric", "Micrómetro", "1.2", "0.1", "0.1", True),
    ]
    for pos, (name, tipo, tool, nominal, tol_plus, tol_minus, critico) in enumerate(
        checks, start=1
    ):
        db.add(
            QualityPlanCheck(
                manufacturing_model_id=modelo.id,
                position=pos,
                name=name,
                tipo=tipo,
                tool_id=tool,
                nominal_value=Decimal(nominal) if nominal else None,
                tolerance_plus=Decimal(tol_plus) if tol_plus else None,
                tolerance_minus=Decimal(tol_minus) if tol_minus else None,
                is_critical=critico,
            )
        )
    db.commit()


def _asegurar_usuarios_demo(db: Session, tenant_id) -> None:
    """Crea/actualiza los usuarios demo por rol (idempotente).

    Contraseña de TODOS los usuarios demo: 'kavana' (credenciales fáciles,
    decisión de Jorge 2026-08-16). Emails con slug demo: <rol>@demo.local.
    Si un usuario ya existe con otro password (p.ej. el hash '!demo' de la
    demo pública anterior), se actualiza a kavana.
    """
    from app.services.auth import hash_password, verify_password

    usuarios = [
        ("operario@demo.local", "Operario Demo", "operator"),
        ("supervisor@demo.local", "Supervisor Demo", "supervisor"),
        ("materias@demo.local", "Materias Primas Demo", "materials"),
        ("admin@demo.local", "Admin Demo", "admin"),
    ]
    for email, name, role in usuarios:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            db.add(
                User(
                    tenant_id=tenant_id,
                    email=email,
                    name=name,
                    password_hash=hash_password("kavana"),
                    role=role,
                )
            )
        elif not verify_password("kavana", user.password_hash):
            user.password_hash = hash_password("kavana")
            user.role = role
    db.commit()


def seed_demo(db: Session) -> dict:
    """Crea el tenant demo con material, bobina, orden y operario si no existe.

    Idempotente: si el tenant ya existe, solo asegura que la línea demo declare
    el material (necesario para la validación de compatibilidad en despliegues
    donde el seed original creó la línea sin material_id).
    """
    existente = db.scalar(select(Tenant).where(Tenant.name == "Demo Aceros"))
    if existente is not None:
        # Asegurar material en la línea demo (validación de compatibilidad)
        linea = db.scalar(
            select(OrderLine)
            .join(Order, Order.id == OrderLine.order_id)
            .where(Order.tenant_id == existente.id, Order.numero == "OP-DEMO-001")
        )
        material = db.scalar(
            select(Material).where(
                Material.tenant_id == existente.id, Material.code == "ACERO-DC01"
            )
        )
        if linea is not None and material is not None and linea.material_id is None:
            linea.material_id = material.id
            db.commit()
        # Asegurar el modelo de calidad demo (autocontroles, spec 04)
        _asegurar_modelo_demo(db, existente.id)
        # Asegurar usuarios demo por rol (login + roles, Fase 6)
        _asegurar_usuarios_demo(db, existente.id)
        return {"created": False, "tenant": str(existente.id)}

    tenant = Tenant(name="Demo Aceros")
    db.add(tenant)
    db.flush()

    _asegurar_usuarios_demo(db, tenant.id)

    material = Material(
        tenant_id=tenant.id,
        code="ACERO-DC01",
        name="Bobina acero decapado 1.2x1220",
        stock_current=Decimal("800.00"),
        stock_minimum=Decimal("200.00"),
        cost_per_unit=Decimal("2.00"),
        dimension_ancho_mm=Decimal("1220"),
        dimension_espesor_mm=Decimal("1.2"),
        unit="kg",
    )
    db.add(material)
    db.flush()

    bobina = StockItem(
        tenant_id=tenant.id,
        material_id=material.id,
        lote="L-DEMO-001",
        coil_id="COIL-DEMO-001",
        cantidad_inicial=Decimal("800.00"),
        cantidad_disponible=Decimal("800.00"),
        unit="kg",
        width_mm=Decimal("1220"),
        thickness_mm=Decimal("1.2"),
        coste_por_unidad=Decimal("2.00"),
        costing_method="standard",
        moneda="EUR",
        fecha_entrada=datetime.now(UTC) - timedelta(days=2),
        ubicacion="ALMACEN-1",
        estado="activo",
        es_pico=False,
    )
    db.add(bobina)
    db.flush()

    order = Order(
        tenant_id=tenant.id,
        numero="OP-DEMO-001",
        estado="active",
        cliente="Cliente demo",
        fecha_entrega=datetime.now(UTC) + timedelta(days=7),
        notas="Orden de demostración pública",
    )
    db.add(order)
    db.flush()

    linea = OrderLine(
        order_id=order.id,
        linea_numero=1,
        workstation_id="LINEA-1",
        estado="pending",
        total_quantity=Decimal("50"),
        produced_quantity=Decimal("0"),
        real_time=Decimal("0"),
        meters_per_piece=Decimal("2.0"),
        material_id=material.id,  # la orden gasta ACERO-DC01 (validación de compatibilidad)
    )
    db.add(linea)

    # Modelo de calidad demo con su plan (autocontroles, spec 04)
    _asegurar_modelo_demo(db, tenant.id)

    db.commit()
    return {"created": True, "tenant": str(tenant.id)}
