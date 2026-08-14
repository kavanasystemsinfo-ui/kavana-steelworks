# ADR-003: Feature Flags por plan (módulos activables) con JSONB

Estado: Aceptado
Fecha: 2026-08-14
Autor: Jorge Adán (KAVANA Systems)
Patrón de referencia: ADR-002 de kavana-manufacturing (feature flags JSONB)

## Contexto

Jorge quiere que Steelworks sea un sistema configurable por **planes**
(básico, pro, industrial) en el que cada módulo se active o desactive según
las necesidades reales de cada planta. No todas las plantas necesitan el
mismo nivel de automatización: unas quieren que el sistema haga casi todo
(auto-vinculación de bobinas, sugerencias FIFO) y otras prefieren control
manual.

Esto aplica a todo el flujo de planta: recepción de materiales, vinculación
de bobinas, consumo FIFO, picos, control de calidad, trazabilidad.

## Decisión

Replicar el patrón ya probado en kavana-manufacturing:

1. **Tabla `tenant_features`** con JSONB: cada tenant tiene su mapa de
   features activas.
2. **Dependency de FastAPI** (`require_feature`) que comprueba la feature en
   cada endpoint, equivalente al FeatureGuard de NestJS del v3.
3. **Planes predefinidos** (básico, pro, industrial) como perfiles de
   features que se aplican al crear el tenant. El plan es un punto de
   partida: un tenant pro puede activar features concretas de industrial
   (override individual).

## Diseño

### Tabla

```sql
CREATE TABLE tenant_features (
    tenant_id UUID PRIMARY KEY REFERENCES tenants(id),
    features JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Catálogo de features (v1)

| Feature | Básico | Pro | Industrial | Qué controla |
|---|---|---|---|---|
| `receiving_simple` | ✅ | ✅ | ✅ | Registro de bobina al llegar (sin albarán) |
| `receiving_asn` | ❌ | ❌ | ✅ | Aviso previo del proveedor (albarán) |
| `receiving_quality_check` | ❌ | ❌ | ✅ | Cuarentena → inspección → liberación |
| `auto_link_coil` | ❌ | ✅ | ✅ | Auto-vinculación de bobina al puesto |
| `fifo_bubble` | ❌ | ✅ | ✅ | Burbuja de vinculación (modo auditoría) |
| `fifo_suggestions` | ❌ | ✅ | ✅ | Sugerencia de picos/bobinas al operario |
| `pico_suggestion` | ❌ | ✅ | ✅ | Aviso "existen picos, ¿usar uno?" |
| `coste_real` | ❌ | ✅ | ✅ | Coste real de compra por lote |
| `coste_estandar` | ✅ | ✅ | ✅ | Coste estándar del material |
| `oee_kpis` | ❌ | ✅ | ✅ | OEE y KPIs |
| `traceability_full` | ❌ | ❌ | ✅ | Trazabilidad ISO 9001 completa (heat number, certificados) |
| `kardex_audit` | ✅ | ✅ | ✅ | Kardex inmutable (siempre activo, obligatorio) |

### Implementación backend (FastAPI)

```python
# app/core/features.py
FEATURES_DEFAULT = {
    "receiving_simple": True,
    "receiving_asn": False,
    "receiving_quality_check": False,
    "auto_link_coil": False,
    "fifo_bubble": False,
    "fifo_suggestions": False,
    "pico_suggestion": False,
    "coste_real": False,
    "coste_estandar": True,
    "oee_kpis": False,
    "traceability_full": False,
    "kardex_audit": True,  # obligatorio
}

PLANES = {
    "basico": {**FEATURES_DEFAULT},
    "pro": {
        **FEATURES_DEFAULT,
        "auto_link_coil": True,
        "fifo_bubble": True,
        "fifo_suggestions": True,
        "pico_suggestion": True,
        "coste_real": True,
        "oee_kpis": True,
    },
    "industrial": {
        **FEATURES_DEFAULT,
        "receiving_asn": True,
        "receiving_quality_check": True,
        "auto_link_coil": True,
        "fifo_bubble": True,
        "fifo_suggestions": True,
        "pico_suggestion": True,
        "coste_real": True,
        "oee_kpis": True,
        "traceability_full": True,
    },
}

def require_feature(feature: str):
    """Dependency de FastAPI: 403 si el tenant no tiene la feature."""
    def checker(
        tenant_id: UUID = Depends(get_current_tenant),
        db: Session = Depends(get_db),
    ) -> None:
        flags = get_tenant_features(db, tenant_id)
        if not flags.get(feature, False):
            raise HTTPException(
                status_code=403,
                detail=f"Feature '{feature}' no habilitada para este tenant",
            )
    return checker
```

## Consecuencias

- **Positivas**: una sola instalación sirve a plantas de cualquier tamaño;
  el plan se cambia sin deploy; el sistema se afina a las necesidades reales
  de cada planta (visión Jorge); patrón ya probado en el v3.
- **Negativas**: cada endpoint nuevo debe declarar su feature; el catálogo
  hay que mantenerlo documentado.
- **Regla YAGNI**: `kardex_audit` y `receiving_simple` son obligatorios en
  todos los planes (no se pueden desactivar: romperían la trazabilidad y el
  flujo mínimo).

## Referencias

- Patrón original: `kavana-manufacturing/docs/adr/002-feature-flags-jsonb.md`
- Specs relacionadas: 06 (recepción), 01 (inventario), anexo A (flujo operario)
