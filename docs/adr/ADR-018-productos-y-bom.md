# ADR-018: Catálogo de productos terminados y BOM

- Estado: Aceptado
- Fecha: 2026-10-15
- Autor: Jorge Adán (KAVANA Systems)

## Contexto

El dominio de Steelworks se modeló alrededor de la fabricación de piezas:
`manufacturing_models` (piezas con su plan de calidad), `order_lines` que
fabrican un modelo por línea y consumen un material. Eso cubre la planta, pero
no responde a "qué estoy vendiendo": en una empresa de estanterías se venden
**productos terminados** (un Rack Pórtico, un Mástil Voladizo) que se
ensamblan a partir de varias piezas y de material directo (tornillería,
malla).

`order_lines.product_id` llevaba existiendo desde la migración inicial como
columna huérfana sin FK ni modelo asociado: la intención existía, el catálogo
no. Además, la demo desplegada mostraba datos de una acería genérica
("Demo Aceros") cuando el caso de uso real de referencia es un fabricante de
estanterías industriales.

La restricción es la de siempre (ADR-017): coste cero, todo por migración y
seed idempotente en el entrypoint, sin servicios nuevos.

## Decisión

### 1. Tablas `products` y `product_components` (BOM)

- `products`: catálogo de producto terminado por tenant (`code` único por
  tenant, `name`, `description`, `is_active`).
- `product_components`: lista de materiales (BOM) del producto. Cada fila
  apunta a **exactamente uno** de:
  - `manufacturing_model_id` → pieza fabricada en planta, o
  - `material_id` → material directo comprado (tornillería, malla…),
  garantizado por el CHECK `ck_component_xor` a nivel de base de datos.
  Además `quantity`, `unit` y `position`.
- `order_lines.product_id` pasa de columna suelta a FK real sobre
  `products.id`. En producción la columna está 100 % NULL (verificado antes
  de escribir la migración), así que la adición de la FK no puede fallar.

Las órdenes **siguen fabricando piezas** (`modelo_id`) por línea: el BOM da
contexto de ensamblaje y permite consultar qué lleva un producto y estimar
demandas, sin tocar el flujo de producción, consumo ni calidad.

### 2. Seed del catálogo de estanterías

`app/services/seed_estanterias.py`, idempotente, invocado en el entrypoint
tras `seed_demo`:

- Renombra el tenant a **"Kavana Estanterías"** (slug `demo` intacto, es la
  identidad estable: `seed_demo` pasa a buscar por slug, no por name, para no
  duplicar el tenant en cada arranque).
- 10 productos con nombres propios (Pórtico, Callejón, Desliz, Corcel,
  Gravedad, Reversa, Titán, Pluma, Voladizo, Altillo) y su BOM (piezas +
  materiales directos), referenciando el catálogo Mecalux como fuente de
  estructura.
- 14 piezas (`manufacturing_models`) con plan de autocontroles, 8 materias
  primas nuevas con 12 lotes/bobinas de stock y kardex de entrada, grupos de
  trabajo = procesos (Corte, Punzonado, Doblado, Soldadura, Galvanizado,
  Montaje) con 7 puestos nuevos (LINEA-1..3 intactos), 3 órdenes nuevas (2
  activas, 1 completada) y su histórico: `production_logs`,
  `material_consumos`, kardex de salida, `quality_records` y una incidencia
  resuelta.

Los datos siguen siendo ficticios y marcados como demo (SECURITY.md).

### 3. Verificación

- Tests TDD: `tests/test_products.py` (modelos, XOR, unicidad por tenant,
  cascada) y `tests/test_seed_estanterias.py` (rename, 10 productos con BOM,
  piezas con plan, stock, grupos/puestos, órdenes, idempotencia, encadenado
  con `seed_demo`).
- La migración se valida en CI con `alembic upgrade head --sql` (offline);
  los tests usan SQLite con `create_all`, por eso el CHECK y la FK se
  comprueban también en los tests de modelos.

## Alternativas evaluadas

| Alternativa | A favor | En contra | Veredicto |
|---|---|---|---|
| `products` + `product_components` con CHECK XOR (ELEGIDA) | BOM explícita, integridad en BD, consulta directa | Dos tablas y una migración más | Elegida: es el mínimo que modela la realidad sin tocar el flujo de producción |
| BOM como JSON en `products` | Sin tabla extra | Sin integridad referencial, imposible de consultar/joinar, imposible de FK desde `order_lines` | Descartada: el resto del esquema es relacional con CHECKs reales (ADR-002) |
| Cambiar `order_lines` para fabricar el producto directamente | Un modelo menos | Rompe producción, consumo, calidad y trazabilidad; las líneas fabrican piezas físicas, no ensamblajes | Descartada: fuera de alcance y de momento innecesario (YAGNI) |
| Renombrar tenant con migración SQL | El rename quedaría en el historial de esquema | El name es datos, no esquema; los datos de tenant los gobierna el seed | Descartado: se hace en el seed idempotente |
| Crear tablas de procesos/rutas nuevas | Modelaría el enrutado completo | Las piezas ya se fabrican en puestos concretos vía `order_lines.workstation_id`; añadir rutas es otro módulo | Descartado (YAGNI): los grupos de puesto cubren la visualización de procesos |

## Consecuencias

- La demo pasa a parecer una empresa de estanterías con catálogo real, BOM e
  histórico de producción, sin cambiar ningún endpoint del API.
- `order_lines.product_id` queda cableado: futuras líneas pueden declarar el
  producto que se fabrica (visible en el API por la serialización existente).
- El lookup por slug en `seed_demo` elimina la dependencia del nombre del
  tenant en todo el código de arranque; los e2e que buscaban por name pasan a
  buscar por slug.
- Mantener la BOM sincronizada con las piezas es responsabilidad del seed:
  si se cambia una pieza sin actualizar la BOM, la estimación de demanda
  diverge. Se asume explícitamente porque no hay sistema de gestión de
  cambios de producto en el alcance.
