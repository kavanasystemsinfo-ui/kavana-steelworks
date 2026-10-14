# Graph Report - graph.json  (2026-10-13)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1570 nodes · 4147 edges · 66 communities (57 shown, 9 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 99 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `713f7716`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_quality.py
- test_admin_router.py
- services/assistant.py
- models/__init__.py
- make_order_line
- User
- pytest
- main.py
- log_event
- receiving.py
- test_incidencias.py
- test_qa_websockets.py
- routers/incidencias.py
- seed_demo.py
- test_auth_roles.py
- App.tsx
- sqlalchemy
- get_current_user
- test_websockets.py
- package.json
- record_production
- api.ts
- OperarioPage.test.tsx
- incidencia_uploads.py
- EventBroker
- sequences.py
- login
- OperarioPage.tsx
- DbDep
- routers/admin.py
- link_coil
- SupervisorPage.test.tsx
- compilerOptions
- test_tenant_isolation.py
- test_photo_validator.py
- compilerOptions
- Settings
- services/incidencias.py
- test_link_coil.py
- update_user
- test_oee_kpis.py
- devDependencies
- login
- ws_manager.py
- react
- get_order_trace
- features.py
- make_model
- list_orders
- record_production
- get_kpis
- dependencies
- services
- env.py
- find_coil
- _override_get_db
- scripts
- estado_sesion_subida
- .oxlintrc.json
- create_user
- MateriasPrimasPage.tsx
- SecurityHeadersMiddleware
- tsconfig.json
- docker-entrypoint.sh
- frontend/vercel.json
- kavana-steelworks

## God Nodes (most connected - your core abstractions)
1. `User` - 86 edges
2. `make_order_line()` - 68 edges
3. `make_order()` - 66 edges
4. `Base` - 60 edges
5. `make_material()` - 56 edges
6. `make_stock_item()` - 43 edges
7. `link_coil()` - 36 edges
8. `TimestampMixin` - 33 edges
9. `UUIDMixin` - 33 edges
10. `login()` - 33 edges

## Surprising Connections (you probably didn't know these)
- `main()` --uses--> `QualityRecord`  [INFERRED]
  backend/e2e_quality.py → backend/app/models/quality.py
- `test_registrar_autocontrol_aplica_largo_dinamico_de_la_orden()` --uses--> `QualityRecord`  [INFERRED]
  backend/tests/test_quality.py → backend/app/models/quality.py
- `test_registrar_autocontrol_crea_record_y_log()` --uses--> `QualityRecord`  [INFERRED]
  backend/tests/test_quality.py → backend/app/models/quality.py
- `Incidencia` --uses--> `User`  [INFERRED]
  backend/app/models/incidencia.py → backend/app/models/tenant.py
- `finalizar()` --uses--> `Incidencia`  [INFERRED]
  backend/app/services/incidencia_uploads.py → backend/app/models/incidencia.py

## Import Cycles
- None detected.

## Communities (66 total, 9 thin omitted)

### Community 0 - "test_quality.py"
Cohesion: 0.06
Nodes (34): QualityRecord, get_current_user(), get_quality_models(), get_quality_records(), get_reminder_state(), MeasurementIn, MeasurementOut, ModelOut (+26 more)

### Community 1 - "test_admin_router.py"
Cohesion: 0.05
Nodes (47): TenantRole, test_flujo_admin(), bobina(), db_session(), tenant(), user(), auth_headers_for(), make_tenant() (+39 more)

### Community 2 - "services/assistant.py"
Cohesion: 0.05
Nodes (34): ask_tecnico(), ask_usuario(), Pregunta, _responder(), stats(), buscar(), cargar_corpus(), construir_indice() (+26 more)

### Community 3 - "models/__init__.py"
Cohesion: 0.11
Nodes (9): Sequence, WorkstationGroup, TimestampMixin, UUIDMixin, CoilLink, IncidenciaHistorial, QualityMeasurement, QualityPlanCheck (+1 more)

### Community 4 - "make_order_line"
Cohesion: 0.11
Nodes (25): sugerencias_picos(), consume_stock_fifo(), main(), main(), main(), main(), link_coil(), make_material() (+17 more)

### Community 5 - "User"
Cohesion: 0.09
Nodes (17): Base, Material, StockItem, Tenant, User, MaterialConsumo, MaterialTransaction, _elegibles_fifo() (+9 more)

### Community 6 - "pytest"
Cohesion: 0.08
Nodes (20): peso_desde_radio_mm(), create_retal(), retirar_pico(), test_densidad_calibrada_kavana_por_defecto(), test_peso_ancho_estrecho(), test_peso_bobina_completa_referencia(), test_peso_radio_mitad(), test_radio_cero_peso_cero() (+12 more)

### Community 7 - "main.py"
Cohesion: 0.07
Nodes (5): get_settings(), autenticar(), extraer_bearer(), health_live(), health_ready()

### Community 8 - "log_event"
Cohesion: 0.08
Nodes (26): ProductionLog, _acciones_validas(), get_last_active_session_start(), get_order_trace(), log_event(), authed_client(), _crear_orden(), _override_get_db() (+18 more)

### Community 9 - "receiving.py"
Cohesion: 0.07
Nodes (15): _client_loop(), _drain(), _heartbeat(), ws_events(), build_label(), move_coil(), receive_coil(), _system_user() (+7 more)

### Community 10 - "test_incidencias.py"
Cohesion: 0.12
Nodes (34): Incidencia, calcular_oee(), _clamp(), authed_client_for(), _crear_sesion(), _override_get_db(), _subir_movil(), test_crear_incidencia_con_foto_copia_y_marca_used() (+26 more)

### Community 11 - "test_qa_websockets.py"
Cohesion: 0.08
Nodes (25): _conectar(), _crear_usuario(), _espera_hasta(), _FakeTenant, _recibe_con_timeout(), test_qa_callback_roto_no_impide_el_push_al_cliente_ws(), test_qa_desconexion_brusca_a_media_conexion_limpia_sin_excepcion(), test_qa_evento_publicado_en_ventana_consume_subscribe_no_llega() (+17 more)

### Community 12 - "routers/incidencias.py"
Cohesion: 0.11
Nodes (15): require_roles(), actualizar_incidencia(), crear_incidencia(), crear_sesion_subida(), _enforce_upload_rate_limit(), get_current_user(), IncidenciaIn, IncidenciaUpdate (+7 more)

### Community 13 - "seed_demo.py"
Cohesion: 0.09
Nodes (16): Workstation, Order, OrderLine, ManufacturingModel, verify_password(), _asegurar_modelo_demo(), _asegurar_roles_demo(), _asegurar_usuarios_demo() (+8 more)

### Community 14 - "test_auth_roles.py"
Cohesion: 0.10
Nodes (23): _check_db(), auth_headers(), _client(), _override_all(), _override_get_db(), test_admin_hereda_supervisor(), test_endpoint_protegido_sin_token_devuelve_401(), test_endpoint_protegido_token_invalido_devuelve_401() (+15 more)

### Community 15 - "App.tsx"
Cohesion: 0.11
Nodes (28): App(), currentRole(), MobileUploadRoute(), RequireRole(), currentRole(), Layout(), api, getJwtPayload() (+20 more)

### Community 16 - "sqlalchemy"
Cohesion: 0.09
Nodes (11): upgrade(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade(), downgrade() (+3 more)

### Community 17 - "get_current_user"
Cohesion: 0.10
Nodes (19): fin_bobina(), FinBobinaRequest, get_current_user(), link(), LinkCoilRequest, list_materials(), list_stock(), MaterialOut (+11 more)

### Community 18 - "test_websockets.py"
Cohesion: 0.10
Nodes (24): hash_password(), ws_token(), _conectar(), _FakeTenant, _override_get_db(), test_ws_conecta_y_recibe_hello_con_tenant(), test_ws_desconexion_limpia_suscripcion(), test_ws_entrega_cola_pendiente_al_conectar() (+16 more)

### Community 19 - "package.json"
Cohesion: 0.07
Nodes (27): name, private, type, version, queryClient, renderPage(), rolesBody, tenantBody (+19 more)

### Community 20 - "record_production"
Cohesion: 0.10
Nodes (13): _calcular_kg_por_pieza(), record_production(), _resolve_active_material(), _resolver_usuario(), _setup(), test_produccion_actualiza_coste_laboral(), test_produccion_auditoria_consume_por_burbuja(), test_produccion_completa_la_linea() (+5 more)

### Community 21 - "api.ts"
Cohesion: 0.12
Nodes (28): IncidenciaItem, JwtPayload, KpisData, LoginResponse, OeeData, OrderItem, PlanCheck, QualityModel (+20 more)

### Community 22 - "OperarioPage.test.tsx"
Cohesion: 0.08
Nodes (12): MockWebSocket, ADR-0014, bobinaDemo, modeloDemo, renderPage(), eventoRest, eventoWs, modeloDemo (+4 more)

### Community 23 - "incidencia_uploads.py"
Cohesion: 0.15
Nodes (12): IncidenciaUploadSession, adjuntar_foto(), _buscar_por_session_id(), _caducada(), crear_sesion(), finalizar(), obtener_foto(), obtener_foto_por_id() (+4 more)

### Community 24 - "EventBroker"
Cohesion: 0.15
Nodes (10): EventBroker, test_broker_limita_cola_por_tenant(), test_broker_publica_y_recupera_eventos_por_canal(), test_broker_separa_eventos_por_tenant(), test_qa_broker_limite_200_descarta_los_mas_viejos(), test_qa_broker_subscribe_mismo_callback_no_duplica_notificacion(), test_broker_callback_que_falla_no_rompe_publish(), test_broker_publish_sin_listeners_mantiene_encolado() (+2 more)

### Community 25 - "sequences.py"
Cohesion: 0.14
Nodes (12): _config(), next_sequence(), peek_sequence(), _resolver_prefix(), test_concurrencia_secuencias(), worker(), _tenant_con_secuencias(), test_next_sequence_avanza_y_no_repite() (+4 more)

### Community 26 - "login"
Cohesion: 0.17
Nodes (13): RevokedToken, UserShift, find_user_by_email(), is_revoked(), login(), logout(), verify_token(), _make_user() (+5 more)

### Community 27 - "OperarioPage.tsx"
Cohesion: 0.13
Nodes (18): ConexionEstado, ADR-0014, UsePlantEvents, UsePlantEventsOptions, wsBaseUrl(), WsMessage, EventData, getToken() (+10 more)

### Community 28 - "DbDep"
Cohesion: 0.15
Nodes (9): get_current_user(), get_tenant(), list_roles(), list_users(), list_workstation_groups(), list_workstations(), next_sequence_endpoint(), update_role() (+1 more)

### Community 29 - "routers/admin.py"
Cohesion: 0.16
Nodes (16): get_sequences(), RoleOut, RoleUpdate, SequenceConfig, SequenceNextOut, _sequences_defaults(), SequencesConfig, TenantOut (+8 more)

### Community 30 - "link_coil"
Cohesion: 0.19
Nodes (10): link_coil(), validar_material_compatible(), _bobina(), _material_con_dimensiones(), test_link_acepta_bobina_del_mismo_material(), test_link_acepta_dimensiones_dentro_de_tolerancia(), test_link_rechaza_ancho_incompatible(), test_link_rechaza_bobina_de_otro_material() (+2 more)

### Community 31 - "SupervisorPage.test.tsx"
Cohesion: 0.12
Nodes (16): ACCIONES_TRACE, DetalleEvento(), IncidenciaItem, Kpi(), KpisData, OeeData, OrderItem, SupervisorPage() (+8 more)

### Community 32 - "compilerOptions"
Cohesion: 0.10
Nodes (19): compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection (+11 more)

### Community 33 - "test_tenant_isolation.py"
Cohesion: 0.12
Nodes (7): get_db(), get_events(), health(), client(), _override_get_db(), test_events_tenant_propio_sigue_funcionando(), test_ws_sin_token_cierra_4403()

### Community 34 - "test_photo_validator.py"
Cohesion: 0.20
Nodes (12): detectar_tipo_imagen(), validar_foto(), test_detectar_gif(), test_detectar_jpeg(), test_detectar_png(), test_detectar_rechaza_no_imagen(), test_detectar_webp(), test_validar_foto_demasiado_grande() (+4 more)

### Community 35 - "compilerOptions"
Cohesion: 0.12
Nodes (16): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection, noEmit, noFallthroughCasesInSwitch (+8 more)

### Community 36 - "Settings"
Cohesion: 0.19
Nodes (7): _normalizar_database_url(), Settings, _limpiar_env(), test_desarrollo_admite_secret_debil(), test_produccion_con_secret_corto_falla(), test_produccion_con_secret_fuerte_ok(), test_produccion_con_secret_por_defecto_falla()

### Community 37 - "services/incidencias.py"
Cohesion: 0.23
Nodes (5): actualizar_incidencia(), crear_incidencia(), listar_incidencias(), _resolver_orden_activa(), subir_foto()

### Community 38 - "test_link_coil.py"
Cohesion: 0.19
Nodes (7): _bobina(), test_link_coil_bobina_inactiva_falla(), test_link_coil_cobra_toda_la_bobina_a_la_orden(), test_link_coil_es_idempotente(), test_link_coil_no_descuenta_stock_fisico(), test_link_coil_registra_kardex_de_vinculacion(), test_link_coil_reubica_bobina_al_puesto()

### Community 39 - "update_user"
Cohesion: 0.20
Nodes (6): deactivate_user(), deactivate_workstation(), update_user(), update_workstation(), _validar_grupo(), _validar_workstation_code()

### Community 40 - "test_oee_kpis.py"
Cohesion: 0.20
Nodes (6): calcular_kpis(), _tenant_con_orden(), test_kpis_financieros(), test_kpis_sin_costes_no_divide_por_cero(), test_oee_calcula_componentes(), test_oee_cuenta_produccion_de_orden_completada()

### Community 41 - "devDependencies"
Cohesion: 0.15
Nodes (13): devDependencies, jsdom, oxlint, @testing-library/jest-dom, @testing-library/react, @testing-library/user-event, @types/node, @types/react (+5 more)

### Community 42 - "login"
Cohesion: 0.20
Nodes (5): _extraer_bearer(), login(), LoginRequest, LoginResponse, logout()

### Community 44 - "react"
Cohesion: 0.23
Nodes (7): initialLastPeriodic(), QualityReminders, REMINDER_FIRST_MIN, REMINDER_PERIODIC_MIN, useQualityReminders(), HookProbe(), react

### Community 45 - "get_order_trace"
Cohesion: 0.22
Nodes (4): get_current_user(), get_order_trace(), OperatorOut, TraceEventOut

### Community 46 - "features.py"
Cohesion: 0.31
Nodes (3): get_tenant_features(), has_feature(), set_tenant_plan()

### Community 47 - "make_model"
Cohesion: 0.36
Nodes (8): make_model(), _override_get_db(), plan_basico(), test_get_quality_models_devuelve_plan(), test_get_quality_records_filtra_por_orden(), test_registrar_autocontrol_aplica_largo_dinamico_de_la_orden(), test_registrar_autocontrol_crea_record_y_log(), test_registrar_autocontrol_rechazado_no_bloquea_produccion()

### Community 48 - "list_orders"
Cohesion: 0.25
Nodes (3): get_current_user(), list_orders(), OrderOut

### Community 49 - "record_production"
Cohesion: 0.25
Nodes (3): get_current_user(), record_production(), RecordProductionRequest

### Community 50 - "get_kpis"
Cohesion: 0.33
Nodes (3): get_current_user(), get_kpis(), get_oee()

### Community 51 - "dependencies"
Cohesion: 0.22
Nodes (9): dependencies, qrcode.react, react, react-dom, react-router-dom, tailwindcss, @tailwindcss/vite, @tanstack/react-query (+1 more)

### Community 52 - "services"
Cohesion: 0.22
Nodes (8): entrypoint, root, framework, root, rewrites, services, backend, frontend

### Community 54 - "find_coil"
Cohesion: 0.43
Nodes (4): find_coil(), test_scan_bobina_inexistente_devuelve_none(), test_scan_por_coil_id_devuelve_datos_completos(), test_scan_por_lote_funciona()

### Community 55 - "_override_get_db"
Cohesion: 0.29
Nodes (4): _override_get_db(), test_qa_endpoint_rest_de_polling_sigue_funcionando(), _ws_auth_tokens(), ws_client()

### Community 56 - "scripts"
Cohesion: 0.29
Nodes (7): scripts, build, dev, lint, preview, test, test:watch

### Community 58 - ".oxlintrc.json"
Cohesion: 0.33
Nodes (5): plugins, rules, react/only-export-components, react/rules-of-hooks, $schema

### Community 60 - "MateriasPrimasPage.tsx"
Cohesion: 0.60
Nodes (4): getTenantId(), MaterialOut, Field(), MateriasPrimasPage()

## Knowledge Gaps
- **14 isolated node(s):** `jsdom`, `oxlint`, `tailwindcss`, `@types/node`, `@types/react` (+9 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 643 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `User` to `test_quality.py`, `test_admin_router.py`, `models/__init__.py`, `make_order_line`, `main.py`, `log_event`, `receiving.py`, `test_incidencias.py`, `test_qa_websockets.py`, `routers/incidencias.py`, `seed_demo.py`, `get_current_user`, `test_websockets.py`, `record_production`, `login`, `DbDep`, `routers/admin.py`, `get_order_trace`, `list_orders`, `record_production`, `get_kpis`, `create_user`?**
  _High betweenness centrality (0.068) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `User` (e.g. with `Incidencia` and `IncidenciaHistorial`) actually correct?**
  _`User` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `jsdom`, `oxlint`, `tailwindcss` to the rest of the system?**
  _14 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `test_quality.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05754527162977867 - nodes in this community are weakly interconnected._
- **Why does `peso_desde_radio_mm()` connect `pytest` to `make_order_line`, `User`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `Base` (e.g. with `preparar_bd()` and `main()`) actually correct?**
  _`Base` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Should `test_admin_router.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05217391304347826 - nodes in this community are weakly interconnected._