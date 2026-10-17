# ADR-020: Selección de puesto de trabajo, cola de órdenes y vínculo de material en el panel del operario

Estado: Aceptado
Fecha: 2026-10-17
Autor: Jorge Adán (KAVANA Systems)

## Contexto

Pulido del registro de órdenes guiado por el repo legacy `kavanasystems`
(`SelectWorkstation.jsx` → `OrderQueueCompact.jsx` → `PreparationMaterialsTab.jsx`).
En `kavana-steelworks` el operario aterrizaba directamente en el panel de la orden
usando su `default_workstation_code`, sin poder elegir puesto ni ver la cola:

- `GET /admin/workstations` exigía rol supervisor/admin: el operario recibía 403 y
  no podía poblar ninguna pantalla de selección de puesto.
- `GET /orders/available` filtraba solo por `default_workstation_code`, así que un
  operario que rota de línea no podía ver ni elegir las órdenes de otro puesto.
- El error de stock insuficiente decía "faltan N unidades", sin unidad real (el
  material se mide en kg), confuso para el operario.

## Decisión

1. **Lectura de puestos abierta al operario**: `PlantaReadDep` pasa a incluir
   `"operator"` además de supervisor/admin. El alta/baja de puestos sigue en
   `AdminDep`, de modo que el operario solo lee.
2. **`GET /orders/available?workstation=CODE`**: nuevo parámetro opcional. Si se
   envía, se valida contra la tabla `Workstation` del tenant (404/400 si no existe)
   y se filtra por ese código; si se omite, se mantiene el comportamiento previo
   (`default_workstation_code`). No se muta el usuario, evitando efectos laterales
   sobre `default_workstation_code`.
3. **Flujo de 3 pasos en `OperarioPage`**: selección de puesto → cola de órdenes del
   puesto → panel de la orden (dentro del cual se vincula la materia prima). Estado
   en la URL `?ws=&order=` vía `history.replaceState`. Auto-salto cuando hay un único
   puesto y/o una única orden. Botones "Cambiar orden" y "Cambiar puesto".
4. **Efectos asíncronos cancelables**: los efectos que cargan workstations y el
   detalle de orden usan una bandera `cancelled` en el cleanup, de modo que una
   respuesta obsoleta (el usuario cambió de puesto/orden antes de que llegara no
   resuelva) no pueda sobrescribir la vista actual. `cambiarOrden`/`cambiarPuesto`
   limpian los parámetros de URL correspondientes.
5. **Mensaje de stock** de "unidades" a "kg de material" en `consume_stock_fifo`.

## Consecuencias

- El panel funciona con independencia del listado supervisor y respeta la rotación
  de puestos del operario.
- El flujo queda alineado con el legacy, reduciendo deuda de producto y facilitando
  la demo a reclutadores.
- La validación del parámetro `workstation` cierra la puerta a filtrar por un puesto
  inexistente o de otro tenant.
- Alternativas descartadas: cambiar el `default_workstation_code` del usuario al
  seleccionar puesto (efecto lateral persistente) y usar el listado supervisor
  (403 para el operario).

## Alcance

Backend: `routers/admin.py`, `routers/orders.py`, `services/inventory.py`.
Frontend: `lib/api.ts`, `pages/OperarioPage.tsx`.
Tests: `tests/test_flujo_puesto_orden.py` (nuevo), `tests/test_admin_router.py`,
`frontend/src/test/OperarioPage.test.tsx`.
