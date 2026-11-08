"""Router de stock-items: recepción de bobinas (Materias Primas, spec 06)."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import autenticar, require_roles
from app.models import Material, User
from app.services import receiving as receiving_service

router = APIRouter(prefix="/api/v1/stock-items", tags=["stock"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbDep = Annotated[Session, Depends(get_db)]


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: DbDep = None,
) -> User:
    """Dependencia local: usuario autenticado vía Bearer (usa el DbDep del router)."""
    return autenticar(db, authorization)



class ReceiveCoilRequest(BaseModel):
    # Obsoleto: se ignora. El tenant sale siempre del token del usuario.
    tenant_id: uuid.UUID | None = None
    material_id: uuid.UUID
    lote: str = Field(max_length=255)
    coil_id: str | None = Field(default=None, max_length=255)
    peso: Decimal = Field(gt=0)
    width_mm: Decimal | None = Field(default=None, ge=0)
    thickness_mm: Decimal | None = Field(default=None, ge=0)
    coste_real: Decimal | None = Field(default=None, ge=0)
    ubicacion: str | None = Field(default=None, max_length=255)
    heat_number: str | None = Field(default=None, max_length=255)
    grado_acero: str | None = Field(default=None, max_length=255)
    supplier_coil_id: str | None = Field(default=None, max_length=255)


class ReceiveCoilResponse(BaseModel):
    id: uuid.UUID
    lote: str
    coil_id: str | None
    estado: str
    peso: Decimal
    ubicacion: str | None
    costo_method: str

    class Config:
        from_attributes = True


@router.post("", response_model=ReceiveCoilResponse)
def receive(
    body: ReceiveCoilRequest,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "materials")),
    ] = None,
):
    """Registra una bobina entrante (entrada directa a producción)."""
    try:
        bobina = receiving_service.receive_coil(
            db,
            current_user.tenant_id,
            user_id=current_user.id,
            material_id=body.material_id,
            lote=body.lote,
            coil_id=body.coil_id,
            peso=body.peso,
            width_mm=body.width_mm,
            thickness_mm=body.thickness_mm,
            coste_real=body.coste_real,
            ubicacion=body.ubicacion,
            heat_number=body.heat_number,
            grado_acero=body.grado_acero,
            supplier_coil_id=body.supplier_coil_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ReceiveCoilResponse(
        id=bobina.id,
        lote=bobina.lote,
        coil_id=bobina.coil_id,
        estado=bobina.estado,
        peso=bobina.cantidad_disponible,
        ubicacion=bobina.ubicacion,
        costo_method=bobina.costing_method,
    )


class StockItemOut(BaseModel):
    id: uuid.UUID
    lote: str
    coil_id: str | None
    material_id: uuid.UUID
    cantidad_disponible: Decimal
    estado: str
    ubicacion: str | None
    fecha_entrada: datetime | None

    class Config:
        from_attributes = True


class MaterialOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    cost_per_unit: Decimal | None
    unit: str | None
    stock_current: Decimal | None
    dimension_ancho_mm: Decimal | None
    dimension_espesor_mm: Decimal | None

    class Config:
        from_attributes = True


@router.get("/materials", response_model=list[MaterialOut])
def list_materials(
    db: DbDep,
    current_user: Annotated[User, Depends(get_current_user)] = None,
):
    """Lista materiales activos del tenant (para el formulario de recepción)."""
    return (
        db.query(Material)
        .filter(
            Material.tenant_id == current_user.tenant_id,
            Material.is_active == True,  # noqa: E712
        )
        .all()
    )


class PicoSugerencia(BaseModel):
    """Pico/retal disponible en almacén (sugerencia de uso, idea Jorge)."""

    stock_item_id: uuid.UUID
    lote: str
    coil_id: str | None
    material_code: str
    peso_kg: Decimal
    ubicacion: str | None
    fecha_entrada: datetime | None


@router.get("/picos", response_model=list[PicoSugerencia])
def sugerencias_picos(
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator")),
    ] = None,
):
    """Picos y retales en almacén para aconsejar su uso antes de abrir
    bobina nueva. Sugerencia visible, nunca imposición (decisión Jorge)."""
    from app.models import StockItem

    items = (
        db.query(StockItem)
        .filter(
            StockItem.tenant_id == current_user.tenant_id,
            StockItem.estado.in_(["pico", "retal"]),
            StockItem.ubicacion == "Retales",  # solo picos retirados al almacén
        )
        .order_by(StockItem.fecha_entrada.asc())
        .all()
    )
    return [
        PicoSugerencia(
            stock_item_id=i.id,
            lote=i.lote,
            coil_id=i.coil_id,
            material_code=i.material.code if i.material else "?",
            peso_kg=i.cantidad_disponible,
            ubicacion=i.ubicacion,
            fecha_entrada=i.fecha_entrada,
        )
        for i in items
    ]


@router.get("/picos-por-material")
def picos_por_material(
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor")),
    ] = None,
):
    """Picos acumulados por material (visión del supervisor): cuántos hay, cuántos
    kilos suman y desde cuándo, para decidir cuándo gastarlos."""
    from sqlalchemy import select

    from app.models import StockItem

    ahora = datetime.now(UTC)
    picos = db.scalars(
        select(StockItem)
        .where(
            StockItem.tenant_id == current_user.tenant_id,
            StockItem.estado == "pico",
            StockItem.cantidad_disponible > 0,
        )
        .order_by(StockItem.fecha_entrada.asc())
    ).all()

    def dias(p) -> int | None:
        if p.fecha_entrada is None:
            return None
        entrada = p.fecha_entrada if p.fecha_entrada.tzinfo else p.fecha_entrada.replace(tzinfo=UTC)
        return max((ahora - entrada).days, 0)

    grupos: dict = {}
    for p in picos:
        g = grupos.setdefault(
            p.material_id,
            {
                "material_id": str(p.material_id),
                "material_code": p.material.code if p.material else "?",
                "material_name": p.material.name if p.material else "",
                "picos": 0,
                "kg_total": 0.0,
                "mas_antiguo_dias": None,
                "items": [],
            },
        )
        d = dias(p)
        g["picos"] += 1
        g["kg_total"] += float(p.cantidad_disponible)
        if d is not None and (g["mas_antiguo_dias"] is None or d > g["mas_antiguo_dias"]):
            g["mas_antiguo_dias"] = d
        g["items"].append(
            {
                "id": str(p.id),
                "coil_id": p.coil_id,
                "lote": p.lote,
                "peso_kg": float(p.cantidad_disponible),
                "ubicacion": p.ubicacion,
                "antiguedad_dias": d,
            }
        )
    resultado = list(grupos.values())
    for g in resultado:
        g["kg_total"] = round(g["kg_total"], 2)
    resultado.sort(key=lambda g: -g["kg_total"])
    return resultado


@router.get("/scan", response_model=dict | None)
def scan_coil(
    coil_id: str | None = None,
    lote: str | None = None,
    db: DbDep = None,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator")),
    ] = None,
):
    """Escaneo de bobina (flujo operario): busca por coil_id o lote.

    Modo automático: devuelve material, dimensiones y peso. Modo manual:
    el operario ajusta peso y lote desde la etiqueta física.
    """
    from app.services.inventory import find_coil

    try:
        return find_coil(db, current_user.tenant_id, coil_id=coil_id, lote=lote)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class LinkCoilRequest(BaseModel):
    stock_item_id: uuid.UUID
    order_id: uuid.UUID
    line_id: uuid.UUID
    # D-019: si se elige una bobina nueva habiendo picos, se indica por qué (un toque)
    motivo_salto_pico: Literal["pico_corto", "pico_danado", "no_localizado", "otro"] | None = None


@router.post("/link")
def link(
    body: LinkCoilRequest,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator")),
    ] = None,
):
    """Vincula la bobina a la orden (cobro BULK por adelantado).

    Picos primero (D-019): si se elige una bobina nueva habiendo picos del mismo
    material, no se impide, pero hay que indicar el motivo y queda registrado."""
    from app.models import OrderLine, StockItem
    from app.services.inventory import MOTIVOS_SALTO_PICO, link_coil, picos_pendientes
    from app.services.traceability import log_event

    bobina = db.get(StockItem, body.stock_item_id)
    linea = db.get(OrderLine, body.line_id)
    picos = []
    if (
        bobina is not None
        and bobina.tenant_id == current_user.tenant_id
        and linea is not None
        and linea.order_id == body.order_id
    ):
        picos = picos_pendientes(db, current_user.tenant_id, linea, bobina)
        if picos and body.motivo_salto_pico is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "codigo": "MOTIVO_PICO_REQUERIDO",
                    "mensaje": (
                        "Hay picos de este material. Indica por qué eliges una bobina nueva."
                    ),
                    "picos": [
                        {"coil_id": p.coil_id or p.lote, "peso_kg": float(p.cantidad_disponible)}
                        for p in picos
                    ],
                },
            )
    codigos_picos = [p.coil_id or p.lote for p in picos]
    codigo_bobina = (bobina.coil_id or bobina.lote) if bobina is not None else None

    try:
        resultado = link_coil(
            db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            stock_item_id=body.stock_item_id,
            order_id=body.order_id,
            line_id=body.line_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if picos and body.motivo_salto_pico is not None:
        log_event(
            db,
            tenant_id=current_user.tenant_id,
            order_id=body.order_id,
            line_id=body.line_id,
            operator_id=current_user.id,
            action="setup_start",
            quantity=0,
            metadata={
                "reason": "salto_pico",
                "motivo": body.motivo_salto_pico,
                "motivo_texto": MOTIVOS_SALTO_PICO[body.motivo_salto_pico],
                "picos_omitidos": codigos_picos,
                "activeCoilCode": codigo_bobina,
            },
        )
    return resultado


class FinBobinaRequest(BaseModel):
    stock_item_id: uuid.UUID
    order_id: uuid.UUID
    line_id: uuid.UUID
    radio_mm: float = Field(ge=0)



class UnlinkCoilRequest(BaseModel):
    stock_item_id: uuid.UUID
    order_id: uuid.UUID
    line_id: uuid.UUID


@router.post("/unlink")
def unlink(
    body: UnlinkCoilRequest,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator")),
    ] = None,
):
    """Desvincula la bobina de la linea (reembolso de lo no consumido)."""
    from app.services.inventory import unlink_coil

    try:
        return unlink_coil(
            db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            stock_item_id=body.stock_item_id,
            order_id=body.order_id,
            line_id=body.line_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/fin-bobina")
def fin_bobina(
    body: FinBobinaRequest,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator")),
    ] = None,
):
    """Fin de bobina: el operario mide los milímetros de radio restantes
    y el sistema convierte a kg con la fórmula v2 (Densidad Calibrada Kavana)."""
    from app.services.inventory import create_retal

    try:
        return create_retal(
            db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            stock_item_id=body.stock_item_id,
            radio_mm=body.radio_mm,
            order_id=body.order_id,
            line_id=body.line_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/disponibles")
def bobinas_disponibles(
    line_id: uuid.UUID,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator")),
    ] = None,
):
    """Bobinas que el operario puede vincular sin saberse el código (legacy
    MaterialScanner). Si la orden pide un material, solo ese material (el
    sistema no deja vincular otro); si no, las que están en su puesto.
    Primero lo que ya está en la máquina (también montada en otra orden de
    este puesto: se pasa a esta sin medir), luego picos y después FIFO. Fuera
    las montadas en otra máquina."""
    from sqlalchemy import select

    from app.models import Order, OrderLine, StockItem
    from app.services.inventory import ficha_bobina

    linea = db.get(OrderLine, line_id)
    orden = db.get(Order, linea.order_id) if linea else None
    if linea is None or orden is None or orden.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Línea no encontrada")

    puesto = linea.workstation_id
    montadas_fuera = select(OrderLine.active_coil_id).where(
        OrderLine.active_coil_id.is_not(None),
        OrderLine.id != linea.id,
        OrderLine.workstation_id.is_distinct_from(puesto),
    )
    consulta = select(StockItem).where(
        StockItem.tenant_id == current_user.tenant_id,
        StockItem.estado.in_(("activo", "pico")),
        StockItem.cantidad_disponible > 0,
        StockItem.id.not_in(montadas_fuera),
    )
    if linea.material_id is not None:
        consulta = consulta.where(StockItem.material_id == linea.material_id)
    else:
        consulta = consulta.where(StockItem.ubicacion == puesto)
    bobinas = db.scalars(consulta).all()

    def en_puesto(b) -> bool:
        return b.ubicacion == puesto or b.id == linea.active_coil_id

    def prioridad(b):
        return (not en_puesto(b), b.estado != "pico", b.fecha_entrada)

    ahora = datetime.now(UTC)

    def antiguedad_dias(b) -> int | None:
        if b.fecha_entrada is None:
            return None
        entrada = b.fecha_entrada
        if entrada.tzinfo is None:
            entrada = entrada.replace(tzinfo=UTC)
        return max((ahora - entrada).days, 0)

    return [
        {**ficha_bobina(db, b), "en_puesto": en_puesto(b), "antiguedad_dias": antiguedad_dias(b)}
        for b in sorted(bobinas, key=prioridad)[:8]
    ]


class MedirBobinaRequest(BaseModel):
    stock_item_id: uuid.UUID
    order_id: uuid.UUID
    line_id: uuid.UUID
    radio_mm: float = Field(ge=0)


@router.get("/mediciones-pendientes")
def mediciones_pendientes(
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator")),
    ] = None,
):
    """Bobinas montadas que el operario debe medir antes de cerrar su turno."""
    from app.services.medicion import mediciones_pendientes as pendientes

    return pendientes(db, current_user.tenant_id, current_user.id)


@router.post("/medir")
def medir(
    body: MedirBobinaRequest,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator")),
    ] = None,
):
    """Cierre de turno: mide el radio, apunta la chatarra y deja la bobina montada."""
    from app.services.medicion import medir_bobina

    try:
        return medir_bobina(
            db,
            current_user.tenant_id,
            current_user.id,
            stock_item_id=body.stock_item_id,
            radio_mm=body.radio_mm,
            order_id=body.order_id,
            line_id=body.line_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{stock_item_id}/prevision-medida")
def prevision_medida(
    stock_item_id: uuid.UUID,
    radio_mm: Annotated[float, Query(ge=0)],
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator")),
    ] = None,
):
    """Kg que quedan y merma que se apuntaría para unos mm de carne, sin
    guardar nada: el operario lo ve mientras teclea, antes de confirmar."""
    from app.services.medicion import prever_medida

    try:
        return prever_medida(
            db, current_user.tenant_id, stock_item_id=stock_item_id, radio_mm=radio_mm
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class AltaManualRequest(BaseModel):
    material_id: uuid.UUID
    peso_kg: Decimal = Field(gt=0)
    lote: str = Field(min_length=1, max_length=100)
    coil_id: str | None = Field(default=None, max_length=100)
    width_mm: Decimal | None = Field(default=None, gt=0)
    thickness_mm: Decimal | None = Field(default=None, gt=0)
    puesto: str | None = None


@router.post("/alta-manual")
def alta_manual(
    body: AltaManualRequest,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator")),
    ] = None,
):
    """Modo manual del operario: da de alta una bobina con los datos de la
    etiqueta del proveedor (el peso de la etiqueta es el que se carga a la
    línea al vincularla). Pasa por la misma recepción que Materias Primas.
    T-044: origen='alta_manual', pendiente_verificacion=true, trazabilidad completa."""
    from datetime import UTC, datetime

    from app.services.inventory import find_coil
    from app.services.receiving import receive_coil

    material = db.get(Material, body.material_id)
    if material is None or material.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Material no encontrado")
    codigo = body.coil_id or f"MAN-{datetime.now(UTC).strftime('%y%m%d%H%M%S')}"
    try:
        bobina = receive_coil(
            db, current_user.tenant_id, current_user.id,
            material_id=material.id,
            lote=body.lote,
            coil_id=codigo,
            peso=body.peso_kg,
            width_mm=body.width_mm,
            thickness_mm=body.thickness_mm,
            coste_real=material.cost_per_unit,
            ubicacion=body.puesto,
            origen="alta_manual",
            creada_por_user_id=current_user.id,
        )
        # receive_coil ya emite el evento alta_manual_bobina con alta_ubicacion
        # Marcar como pendiente de verificación (receive_coil ya pone origen/creada_por_user_id)
        bobina.alta_ubicacion = body.puesto
        bobina.pendiente_verificacion = True
        db.commit()
        db.refresh(bobina)
        return find_coil(db, current_user.tenant_id, coil_id=bobina.coil_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class RetirarPicoRequest(BaseModel):
    stock_item_id: uuid.UUID
    order_id: uuid.UUID | None = None
    line_id: uuid.UUID | None = None


@router.post("/retirar")
def retirar(
    body: RetirarPicoRequest,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "operator")),
    ] = None,
):
    """Botón 'Retirar': segunda opción del fin de bobina (visión Jorge).

    Devuelve el pico al inventario (ubicación 'Retales'). Aparecerá después
    como material SUGERIDO cuando una orden use ese material. Es distinto
    del fin de bobina, que deja el pico en la máquina.
    """
    from app.services.inventory import retirar_pico

    try:
        return retirar_pico(
            db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            stock_item_id=body.stock_item_id,
            order_id=body.order_id,
            line_id=body.line_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class VerificarBobinaRequest(BaseModel):
    pass  # solo body vacío, el user sale del token


@router.post("/{stock_item_id}/verificar")
def verificar_bobina(
    stock_item_id: uuid.UUID,
    body: VerificarBobinaRequest,
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "supervisor", "admin")),
    ] = None,
):
    """Marca una bobina de alta_manual como verificada (rol supervisor o admin).
    Filtra por tenant_id para aislamiento multi-tenant."""
    from datetime import UTC, datetime

    from app.models import StockItem

    bobina = db.get(StockItem, stock_item_id)
    if bobina is None or bobina.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Bobina no encontrada")

    if bobina.origen != "alta_manual":
        raise HTTPException(
            status_code=400, detail="Solo se pueden verificar bobinas de alta manual"
        )

    if not bobina.pendiente_verificacion:
        raise HTTPException(status_code=400, detail="La bobina ya está verificada")

    bobina.pendiente_verificacion = False
    bobina.verificada_por_user_id = current_user.id
    bobina.verificada_en = datetime.now(UTC)
    db.commit()
    db.refresh(bobina)

    # Evento de trazabilidad: verificación de alta manual
    from app.services.events import broker
    broker.publish(
        tenant_id=current_user.tenant_id,
        tipo="verificacion_alta_manual",
        data={
            "coil_id": bobina.coil_id,
            "lote": bobina.lote,
            "verificada_por_user_id": str(current_user.id),
            "verificada_por_nombre": current_user.name,
            "verificada_en": bobina.verificada_en.isoformat(),
        },
    )

    return {
        "success": True,
        "bobina_id": str(bobina.id),
        "verificada_por": current_user.name,
        "verificada_en": bobina.verificada_en.isoformat(),
    }


@router.get("", response_model=list[StockItemOut])
def list_stock(
    db: DbDep,
    current_user: Annotated[
        User,
        Depends(require_roles(get_current_user, "materials")),
    ] = None,
):
    """Lista bobinas (para el panel de Materias Primas)."""
    from app.models import StockItem

    return (
        db.query(StockItem)
        .filter(StockItem.tenant_id == current_user.tenant_id)
        .order_by(StockItem.fecha_entrada.desc())
        .limit(100)
        .all()
    )
