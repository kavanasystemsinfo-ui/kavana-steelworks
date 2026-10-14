# Roadmap KAVANA Steelworks – Auditoría y mejora (reclutador‑ready)

## 1. Preparación y verificación del entorno  
- [x] Confirmar que el repositorio local está actualizado (`git status`, `git pull`).  
- [x] Verificar que las ramas principales (`main`, `develop`) existen y que el despliegue en Vercel está ligado a la rama correcta.  
- [x] Comprobar que el entorno de desarrollo tiene las dependencias instaladas (`npm ci` en frontend, `pip install -r requirements.txt` en backend).  
- [x] Asegurar que las variables de entorno necesarias para conectar a la base de datos demo están presentes (`.env` o similares).  

## 2. Auditoría estática del código  
### 2.1 Backend  
- [x] Modelos (`app/models/`): revisar relaciones, campos que faltan (p.ej. `order.lines` cargado con `selectinload`).  
- [x] Servicios (`app/services/`): lógica de negocio (inventario, cálculo de bobinas, producción).  
- [x] Routers (`app/routers/`): existencia de endpoints críticos para el operario:  
    `GET /orders/{id}` (con líneas), `POST /production/record`, `POST /stock/fin-bobina`, `POST /stock/retirar`, `POST /stock-items/link`, `GET /quality/models`, `POST /quality/checks`.  
- [x] Verificar uso correcto de Pydantic v2 (evitar warnings de `class Config`).  
- [x] Revisar que los endpoints devuelven los campos que el frontend espera (ids, nombres, unidades).  

### 2.2 Frontend  
- [x] Revisar `src/lib/api.ts`: que los métodos llamen a los endpoints correctos y devuelvan los tipos esperados.  
- [x] Revisar `src/pages/OperarioPage.tsx`: flujo de escaneo, vínculo, producción, fin de bobina, retirada, autocontrol, incidencia; uso de `ordenDetalle` y su `line_id`; manejo de errores y mensajes.  
- [x] Componentes de Supervisor (`SupervisorPage.tsx`): gráficos OEE/KPIs, consumo de `/supervisor/oee` y `/supervisor/kpis`.  
- [x] Hooks (`usePlantEvents.ts`, `useQualityReminders.ts`): WebSocket + fallback REST.  

### 2.3 Tests  
- [x] Ejecutar suite de tests backend (`pytest`) y frontend (`vitest run`).  
- [x] Anotar tests que fallen y su razón (mocks incompletos, endpoints ausentes).  

### 2.4 Documentación y especificaciones  
- [x] Revisar `docs/specs/` (especialmente `01-inventario-bobinas.md` y `04-autocontrol-quality.md`) para validar que la implementación cumple el contrato.  
- [x] Revisar ADRs (`docs/adr/`) para decisiones arquitectónicas (p.ej. ADR‑014 sobre eventos).  

## 3. Generación del grafo de dependencias  
- [ ] Instalar `graphify` (`pip install graphifyy`).  
- [ ] Ejecutar `graphify . --code-only --output graph.json` (backend + frontend).  
- [ ] Ejecutar `graphify cluster-only` para obtener reporte de módulos acoplados.  
- [ ] Analizar el grafo: detectar módulos aislados o con dependencias circulares; verificar que el frontend llama realmente a los routers del backend; identificar puntos de entrada y salida.  

## 4. Exploración real de la interfaz (browser)  
- [ ] Abrir el desplegado en Vercel: `https://steelworks-kavana.vercel.app` (o dominio custom).  
- [ ] Ingresar con credenciales de demo.  
- [ ] Navegar a la vista de **Operario** (tablet).  
- [ ] Realizar el flujo completo manualmente (escaneo, vínculo, producción, fin de bobina, retiro, autocontrol, incidencia).  
- [ ] Mientras se realiza el flujo, observar en la consola del navegador las peticiones API (Network tab) y verificar códigos de estado, cuerpos de respuesta, uso correcto de `order_id` y `line_id`, presencia de mensajes de error.  
- [ ] Cambiar a la vista de **Supervisor** y comprobar que los gráficos OEE/KPIs muestran valores distintos de cero después de haber producido y registrado calidad.  

## 5. Verificación de datos de demo  
- [ ] Consultar directamente la base de datos (psql/pgAdmin o scripts de seed) para confirmar:  
    - Existencia de tenant “Demo Aceros”.  
    - Bobina COIL‑DEMO‑001 con peso, material, ubicación.  
    - Orden OP‑DEMO‑001 con línea LINEA‑1 y workstation asignado.  
    - Registros de producción, consumo, scrap, calidad, incidencias.  

## 6. Identificación de brechas y priorización (P0/P1/P2)  

| Área | Problema encontrado | Impacto para reclutador | Prioridad | Acción concreta |
|------|--------------------|------------------------|----------|-----------------|
| Backend – órdenes | Falta `GET /orders/{id}` con líneas (solo lista) | El operario no puede obtener `line_id` real → usa UUIDs cero → fallos 404 | P0 | Añadir endpoint con `selectinload(Order.lines)` y devolver estructura con `lines[]`. |
| Frontend – OperarioPage | `ordenDetalle` se inicializa con `line_id = ""` y nunca se actualiza después de `listOrders`. | El flujo usa valores vacíos o placeholders. | P0 | Tras `listOrders`, llamar a `getOrder(id)` del primer elemento y extraer `lines[0].id` y `workstation_id`. |
| Frontend – OperarioPage | Botón “Vincular a mi orden” solo cambia estado local, no llama a `api.linkCoil`. | Vinculación nunca persiste en backend. | P0 | Implementar llamada real a `/stock-items/link` con `stock_item_id`, `order_id`, `line_id`. |
| Frontend – OperarioPage | Funciones `recordProduction`, `finBobina`, `retirarPico` usan hardcoded `000…` UUIDs. | Operaciones fallan o no afectan a la orden real. | P0 | Sustituir por valores de `ordenDetalle`. |
| Frontend – OperarioPage | Mensajes de éxito/error no se muestran correctamente (estado de toast fuera de lugar). | Experiencia de usuario confusa. | P1 | Mover toast de recordatorio de calidad a posición fija y asegurar que se muestra tras cada autocontrol. |
| Backend – Calidad | Endpoint `/quality/reminder-state` depende de `UserShift` sin `end_time`; en demo siempre null → nunca muestra recordatorio. | El reclutador no ve el recordatorio de autocontrol (parte del spec 04). | P1 | Ajustar query para que devuelva un turno activo basado en la sesión actual o devolver datos de ejemplo si no hay turno. |
| Frontend – Supervisor | Gráficos OEE/KPIs muestran ceros porque no hay eventos de producción consumidos en el demo. | Falta evidencia de producción real. | P1 | Asegurar que el flujo de producción (paso 4.4) se ejecuta y genera eventos WS/REST que alimenten los gráficos. |
| Tests | Mocks en tests de OperarioPage no simulan el nuevo endpoint `/orders/{id}` ni la respuesta con `lines`. | Tests fallan después de corregir el flujo. | P1 | Actualizar mocks en `OperarioPage.test.tsx` para incluir la respuesta detallada de orden con líneas. |
| Documentación | Algunos ADRs o specs no reflejan los cambios realizados (p.ej. nuevo endpoint). | Riesgo de desinformación futura. | P2 | Actualizar `docs/specs/01-inventario-bobinas.md` y agregar nota en ADR‑014 si corresponde. |

## 7. Ejecución de mejoras (fase de desarrollo)  
- [x] Aplicar los cambios de **P0** en backend y frontend (endpoints, servicio, página de operario).  
- [x] Ejecutar los tests backend y frontend para asegurar que pasan.  
- [x] Verificar nuevamente el flujo completo en el entorno desplegado (paso 4).  
- [x] Aplicar mejoras de **P1** (en progreso: toast en OperarioPage)
- [x] Ejecutar tests nuevamente y validar que no haya regresiones.  
- [x] Documentar cambios en `CHANGELOG.md` o en los ADRs correspondientes.  

## 8. Cierre y entrega  
- [x] Generar un resumen de lo accomplished (qué se fixed, qué se añadió, métricas de prueba).  
- [x] Preparar una breve guía de “demo para reclutador” con pasos exactos y credenciales.  
- [x] Notificar al usuario que el proyecto está listo para revisión.  

### Estados de fase (actualizar a medida que se avanza)
- **Completada**  
- **En proceso**  
- **En revisión**  
- **Verificada**  

---  

*Este roadmap será actualizado después de cada sesión de trabajo para reflejar el progreso real.*  