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
        # Asegurar campos de spec 07 (despliegues pre-migración)
        if not existente.slug:
            existente.slug = "demo"
            db.commit()
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
        # Puestos demo (spec 07)
        _asegurar_workstations_demo(db, existente.id)
        # Roles del sistema con permisos (spec 07)
        _asegurar_roles_demo(db, existente.id)
        return {"created": False, "tenant": str(existente.id)}

    tenant = Tenant(
        name="Demo Aceros",
        slug="demo",
        status="active",
        is_active=True,
        auth={"login_method": "username_password", "require_line_number": True},
        theme={
            "colors": {"primary": "#e56b2e", "header": {"type": "solid", "solidColor": "#050505"}},
            "branding": {"companyName": "Demo Aceros", "logoUrl": ""},
        },
        finances={
            "overhead_hourly_cost": 0,
            "operator_categories": [
                {"id": "peon_especialista", "name": "Peón Especialista", "hourlyCost": 15},
                {"id": "oficial_3", "name": "Oficial 3ª", "hourlyCost": 18},
                {"id": "oficial_2", "name": "Oficial 2ª", "hourlyCost": 21},
                {"id": "oficial_1", "name": "Oficial 1ª", "hourlyCost": 25},
            ],
        },
        sequences_config={
            "order": {"prefix": "OP-{MM}{YY}-", "padding": 3},
            "lot": {"prefix": "LT-{DD}{MM}{YY}-", "padding": 3},
        },
    )
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
    # Puestos demo (spec 07)
    _asegurar_workstations_demo(db, tenant.id)
    # Roles del sistema con permisos (spec 07)
    _asegurar_roles_demo(db, tenant.id)

    db.commit()
    return {"created": True, "tenant": str(tenant.id)}


def _asegurar_workstations_demo(db: Session, tenant_id) -> None:
    """Crea los puestos demo LINEA-1..3 si no existen (spec 07, idempotente)."""
    from app.models import Workstation

    puestos = [
        ("LINEA-1", "Línea 1 - Corte", "#3498db", "quantity", 45),
        ("LINEA-2", "Línea 2 - Corte", "#2ecc71", "quantity", 45),
        ("LINEA-3", "Línea 3 - Conformado", "#e67e22", "quantity", 40),
    ]
    for code, name, color, metodo, coste in puestos:
        existe = db.scalar(
            select(Workstation).where(
                Workstation.tenant_id == tenant_id, Workstation.code == code
            )
        )
        if existe is None:
            db.add(
                Workstation(
                    tenant_id=tenant_id,
                    code=code,
                    name=name,
                    color=color,
                    hourly_cost=Decimal(coste),
                    registration_method=metodo,
                    is_active=True,
                )
            )
    db.commit()


def _asegurar_roles_demo(db: Session, tenant_id) -> None:
    """Crea los roles del sistema con permisos (spec 07, idempotente).

    La matriz replica la Fase 6 y añade los permisos de administración:
    admin tiene TODOS los permisos del catálogo.
    """
    from app.models import TenantRole
    from app.models.admin import PERMISOS_ADMIN, PERMISOS_CATALOGO

    roles = [
        (
            "operator",
            "Operario",
            [
                p
                for p in PERMISOS_CATALOGO
                if p.startswith(
                    (
                        "stock.scan",
                        "stock.link",
                        "stock.finish",
                        "production.",
                        "quality.check",
                        "incidencia.create",
                    )
                )
            ],
        ),
        (
            "materials",
            "Materias Primas",
            [
                p
                for p in PERMISOS_CATALOGO
                if p.startswith(("stock.receive", "stock.list"))
            ],
        ),
        (
            "supervisor",
            "Supervisor",
            [
                p
                for p in PERMISOS_CATALOGO
                if p.startswith(
                    ("oee.", "trace.", "orders.", "incidencia.manage", "quality.read")
                )
            ],
        ),
        ("admin", "Admin", PERMISOS_ADMIN),
    ]
    for role_key, name, permisos in roles:
        existe = db.scalar(
            select(TenantRole).where(
                TenantRole.tenant_id == tenant_id, TenantRole.role_key == role_key
            )
        )
        if existe is None:
            db.add(
                TenantRole(
                    tenant_id=tenant_id,
                    role_key=role_key,
                    name=name,
                    permissions=permisos,
                    is_system=True,
                )
            )
        else:
            existe.name = name
            if role_key == "admin":
                existe.permissions = PERMISOS_ADMIN
    db.commit()
