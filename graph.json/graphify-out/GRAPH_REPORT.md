# Graph Report - graph.json  (2026-10-13)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1579 nodes · 4154 edges · 71 communities (58 shown, 13 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 99 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `713f7716`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_quality.py
- routers/admin.py
- services/incidencias.py
- services/assistant.py
- models/__init__.py
- Tenant
- receiving.py
- consume_stock_fifo
- test_qa_websockets.py
- routers/incidencias.py
- stock.py
- make_order_line
- test_incidencias.py
- main.py
- test_websockets.py
- record_production
- test_admin_router.py
- sqlalchemy
- OperarioPage.tsx
- pytest
- EventBroker
- sequences.py
- App.tsx
- AdminPage.tsx
- ws.py
- log_event
- package.json
- User
- make_stock_item
- qa_OperarioPage.test.tsx
- make_material
- make_user
- login
- test_auth_roles.py
- SupervisorPage.test.tsx
- compilerOptions
- test_orders_router.py
- calcular_oee
- e2e_admin.py
- api.ts
- compilerOptions
- Settings
- helpers.py
- trace.py
- login
- get_order
- routers/production.py
- devDependencies
- ws_manager.py
- react
- test_health.py
- MobilePhotoUpload.tsx
- features.py
- dependencies
- services
- conftest.py
- _override_get_db
- scripts
- .oxlintrc.json
- c4a9f2e7d1b3_add_real_time_order_lines.py
- SecurityHeadersMiddleware
- roles_tenant
- tsconfig.json
- docker-entrypoint.sh
- frontend/vercel.json
- kavana-steelworks

## God Nodes (most connected - your core abstractions)
1. `User` - 83 edges
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

## Communities (71 total, 13 thin omitted)

### Community 0 - "test_quality.py"
Cohesion: 0.06
Nodes (34): QualityRecord, get_current_user(), get_quality_models(), get_quality_records(), get_reminder_state(), MeasurementIn, MeasurementOut, ModelOut (+26 more)

### Community 1 - "routers/admin.py"
Cohesion: 0.07
Nodes (33): create_user(), create_workstation(), deactivate_user(), deactivate_workstation(), get_current_user(), get_sequences(), get_tenant(), list_roles() (+25 more)

### Community 2 - "services/incidencias.py"
Cohesion: 0.06
Nodes (30): IncidenciaHistorial, IncidenciaUploadSession, adjuntar_foto(), _buscar_por_session_id(), _caducada(), crear_sesion(), finalizar(), obtener_foto() (+22 more)

### Community 3 - "services/assistant.py"
Cohesion: 0.05
Nodes (34): ask_tecnico(), ask_usuario(), Pregunta, _responder(), stats(), buscar(), cargar_corpus(), construir_indice() (+26 more)

### Community 4 - "models/__init__.py"
Cohesion: 0.11
Nodes (11): Base, Sequence, TenantRole, Workstation, WorkstationGroup, TimestampMixin, UUIDMixin, CoilLink (+3 more)

### Community 5 - "Tenant"
Cohesion: 0.08
Nodes (19): Material, StockItem, Order, OrderLine, ManufacturingModel, Tenant, ProductionLog, verify_password() (+11 more)

### Community 6 - "receiving.py"
Cohesion: 0.07
Nodes (15): _client_loop(), _drain(), _heartbeat(), ws_events(), build_label(), move_coil(), receive_coil(), _system_user() (+7 more)

### Community 7 - "consume_stock_fifo"
Cohesion: 0.10
Nodes (19): MaterialConsumo, MaterialTransaction, consume_stock_fifo(), create_retal(), _elegibles_fifo(), retirar_pico(), validar_material_compatible(), main() (+11 more)

### Community 8 - "test_qa_websockets.py"
Cohesion: 0.07
Nodes (25): _conectar(), _crear_usuario(), _espera_hasta(), _FakeTenant, _recibe_con_timeout(), test_qa_callback_roto_no_impide_el_push_al_cliente_ws(), test_qa_desconexion_brusca_a_media_conexion_limpia_sin_excepcion(), test_qa_evento_publicado_en_ventana_consume_subscribe_no_llega() (+17 more)

### Community 9 - "routers/incidencias.py"
Cohesion: 0.10
Nodes (16): actualizar_incidencia(), crear_incidencia(), crear_sesion_subida(), _enforce_upload_rate_limit(), estado_sesion_subida(), foto_sesion_subida(), get_current_user(), IncidenciaIn (+8 more)

### Community 10 - "stock.py"
Cohesion: 0.10
Nodes (21): require_roles(), fin_bobina(), FinBobinaRequest, get_current_user(), link(), LinkCoilRequest, list_materials(), list_stock() (+13 more)

### Community 11 - "make_order_line"
Cohesion: 0.11
Nodes (22): make_order(), make_order_line(), test_fifo_cascada_hereda_entre_bobinas(), test_fifo_respeta_fecha_entrada_asc(), test_registra_consumos_auditoria(), test_stock_insuficiente_lanza_error(), _bobina(), _material_con_dimensiones() (+14 more)

### Community 12 - "test_incidencias.py"
Cohesion: 0.14
Nodes (31): Incidencia, authed_client_for(), _crear_sesion(), _override_get_db(), _subir_movil(), test_crear_incidencia_con_foto_copia_y_marca_used(), test_crear_incidencia_con_sesion_pendiente_no_falla(), test_crear_sesion_devuelve_pending_con_ttl() (+23 more)

### Community 13 - "main.py"
Cohesion: 0.08
Nodes (10): run_migrations_offline(), run_migrations_online(), get_settings(), get_db(), get_events(), health(), health_live(), health_ready() (+2 more)

### Community 14 - "test_websockets.py"
Cohesion: 0.10
Nodes (24): hash_password(), ws_token(), _conectar(), _FakeTenant, _override_get_db(), test_ws_conecta_y_recibe_hello_con_tenant(), test_ws_desconexion_limpia_suscripcion(), test_ws_entrega_cola_pendiente_al_conectar() (+16 more)

### Community 15 - "record_production"
Cohesion: 0.10
Nodes (13): _calcular_kg_por_pieza(), record_production(), _resolve_active_material(), _resolver_usuario(), _setup(), test_produccion_actualiza_coste_laboral(), test_produccion_auditoria_consume_por_burbuja(), test_produccion_completa_la_linea() (+5 more)

### Community 16 - "test_admin_router.py"
Cohesion: 0.11
Nodes (27): auth_headers_for(), _client(), _do(), _override_get_db(), test_create_user_email_duplicado_409(), test_create_user_valida_puesto_existente(), test_create_user_y_login_funciona(), test_create_workstation_codigo_duplicado_409() (+19 more)

### Community 17 - "sqlalchemy"
Cohesion: 0.09
Nodes (9): upgrade(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade() (+1 more)

### Community 18 - "OperarioPage.tsx"
Cohesion: 0.09
Nodes (21): ADR-0014, ConexionEstado, ADR-0014, UsePlantEvents, UsePlantEventsOptions, wsBaseUrl(), WsMessage, EventData (+13 more)

### Community 19 - "pytest"
Cohesion: 0.11
Nodes (11): peso_desde_radio_mm(), test_densidad_calibrada_kavana_por_defecto(), test_peso_ancho_estrecho(), test_peso_bobina_completa_referencia(), test_peso_radio_mitad(), test_radio_cero_peso_cero(), test_radio_mayor_mas_peso(), test_sin_ancho_error_claro() (+3 more)

### Community 20 - "EventBroker"
Cohesion: 0.15
Nodes (10): EventBroker, test_broker_limita_cola_por_tenant(), test_broker_publica_y_recupera_eventos_por_canal(), test_broker_separa_eventos_por_tenant(), test_qa_broker_limite_200_descarta_los_mas_viejos(), test_qa_broker_subscribe_mismo_callback_no_duplica_notificacion(), test_broker_callback_que_falla_no_rompe_publish(), test_broker_publish_sin_listeners_mantiene_encolado() (+2 more)

### Community 21 - "sequences.py"
Cohesion: 0.14
Nodes (12): _config(), next_sequence(), peek_sequence(), _resolver_prefix(), test_concurrencia_secuencias(), worker(), _tenant_con_secuencias(), test_next_sequence_avanza_y_no_repite() (+4 more)

### Community 22 - "App.tsx"
Cohesion: 0.18
Nodes (20): App(), currentRole(), MobileUploadRoute(), RequireRole(), currentRole(), Layout(), api, getJwtPayload() (+12 more)

### Community 23 - "AdminPage.tsx"
Cohesion: 0.14
Nodes (23): RoleOut, SeqCfg, SequencesOut, TenantOut, UserOut, WorkstationGroupOut, WorkstationOut, AdminPage() (+15 more)

### Community 24 - "ws.py"
Cohesion: 0.10
Nodes (4): RevokedToken, client(), _override_get_db(), test_ws_sin_token_cierra_4403()

### Community 25 - "log_event"
Cohesion: 0.15
Nodes (15): _acciones_validas(), get_last_active_session_start(), get_order_trace(), log_event(), make_operator(), make_order(), test_get_last_active_session_start_con_stop_devuelve_none(), test_get_last_active_session_start_elige_resume_mas_reciente() (+7 more)

### Community 26 - "package.json"
Cohesion: 0.09
Nodes (20): name, private, type, version, queryClient, jsdom, oxlint, react-dom (+12 more)

### Community 27 - "User"
Cohesion: 0.15
Nodes (6): autenticar(), extraer_bearer(), User, get_current_user(), get_kpis(), get_oee()

### Community 28 - "make_stock_item"
Cohesion: 0.14
Nodes (13): find_coil(), main(), bobina(), make_stock_item(), test_consumo_decrementa_stock_del_material(), test_consumo_registra_kardex_con_snapshots(), test_scan_bobina_inexistente_devuelve_none(), test_scan_por_coil_id_devuelve_datos_completos() (+5 more)

### Community 29 - "qa_OperarioPage.test.tsx"
Cohesion: 0.11
Nodes (9): MockWebSocket, ADR-0014, eventoRest, eventoWs, modeloDemo, tokenDemo, ADR-0014, ADR-0014 (+1 more)

### Community 30 - "make_material"
Cohesion: 0.19
Nodes (11): link_coil(), main(), reset_schema(), make_material(), _bobina(), test_link_coil_bobina_inactiva_falla(), test_link_coil_cobra_toda_la_bobina_a_la_orden(), test_link_coil_es_idempotente() (+3 more)

### Community 31 - "make_user"
Cohesion: 0.18
Nodes (12): make_tenant(), make_user(), test_list_users_solo_del_tenant(), _cliente(), _crear_registro(), _make_model(), _override_get_db(), test_con_autocontrol_devuelve_last_check_at() (+4 more)

### Community 32 - "login"
Cohesion: 0.21
Nodes (12): UserShift, is_revoked(), login(), logout(), verify_token(), _make_user(), test_login_con_password_incorrecto_falla(), test_login_devuelve_token_de_8_horas() (+4 more)

### Community 33 - "test_auth_roles.py"
Cohesion: 0.22
Nodes (16): auth_headers(), _client(), _override_all(), _override_get_db(), test_admin_hereda_supervisor(), test_endpoint_protegido_sin_token_devuelve_401(), test_endpoint_protegido_token_invalido_devuelve_401(), test_login_es_publico() (+8 more)

### Community 34 - "SupervisorPage.test.tsx"
Cohesion: 0.12
Nodes (16): ACCIONES_TRACE, DetalleEvento(), IncidenciaItem, Kpi(), KpisData, OeeData, OrderItem, SupervisorPage() (+8 more)

### Community 35 - "compilerOptions"
Cohesion: 0.10
Nodes (19): compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection (+11 more)

### Community 36 - "test_orders_router.py"
Cohesion: 0.18
Nodes (10): authed_client(), _crear_orden(), _override_get_db(), test_list_orders_devuelve_ordenes_del_tenant(), test_list_orders_incluye_workstation_de_la_linea(), test_list_orders_sin_tenant_devuelve_vacio(), _poblar_traza(), test_get_order_trace_404_si_orden_no_existe() (+2 more)

### Community 37 - "calcular_oee"
Cohesion: 0.16
Nodes (9): calcular_kpis(), calcular_oee(), _clamp(), _tenant_con_orden(), test_kpis_financieros(), test_kpis_sin_costes_no_divide_por_cero(), test_oee_calcula_componentes(), test_oee_cuenta_produccion_de_orden_completada() (+1 more)

### Community 38 - "e2e_admin.py"
Cohesion: 0.14
Nodes (5): _pg_password(), test_flujo_admin(), _material_con_dimensiones(), reset_schema(), _override_get_db()

### Community 39 - "api.ts"
Cohesion: 0.14
Nodes (15): getTenantId(), IncidenciaItem, JwtPayload, KpisData, LoginResponse, MaterialOut, OeeData, OrderItem (+7 more)

### Community 40 - "compilerOptions"
Cohesion: 0.12
Nodes (16): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection, noEmit, noFallthroughCasesInSwitch (+8 more)

### Community 41 - "Settings"
Cohesion: 0.19
Nodes (7): _normalizar_database_url(), Settings, _limpiar_env(), test_desarrollo_admite_secret_debil(), test_produccion_con_secret_corto_falla(), test_produccion_con_secret_fuerte_ok(), test_produccion_con_secret_por_defecto_falla()

### Community 42 - "helpers.py"
Cohesion: 0.16
Nodes (5): link_coil(), test_bobina_fantasma_no_se_consume_en_auditoria(), test_bobina_prioritaria_siempre_elegible(), test_jit_move_traslada_bobina_prioritaria_al_puesto(), test_modo_simple_filtra_por_puesto()

### Community 43 - "trace.py"
Cohesion: 0.21
Nodes (4): get_current_user(), get_order_trace(), OperatorOut, TraceEventOut

### Community 44 - "login"
Cohesion: 0.18
Nodes (6): _extraer_bearer(), login(), LoginRequest, LoginResponse, logout(), find_user_by_email()

### Community 45 - "get_order"
Cohesion: 0.24
Nodes (4): get_current_user(), get_order(), list_orders(), OrderOut

### Community 46 - "routers/production.py"
Cohesion: 0.19
Nodes (3): get_current_user(), record_production(), RecordProductionRequest

### Community 47 - "devDependencies"
Cohesion: 0.15
Nodes (13): devDependencies, jsdom, oxlint, @testing-library/jest-dom, @testing-library/react, @testing-library/user-event, @types/node, @types/react (+5 more)

### Community 49 - "react"
Cohesion: 0.23
Nodes (7): initialLastPeriodic(), QualityReminders, REMINDER_FIRST_MIN, REMINDER_PERIODIC_MIN, useQualityReminders(), HookProbe(), react

### Community 50 - "test_health.py"
Cohesion: 0.27
Nodes (6): _check_db(), _client(), test_health_legacy_sigue_respondiendo(), test_health_live_no_toca_bd(), test_health_ready_con_bd_ok(), test_health_ready_sin_bd_devuelve_503()

### Community 51 - "MobilePhotoUpload.tsx"
Cohesion: 0.29
Nodes (9): MobilePhotoUpload(), PageStatus, Props, canvasToBlob(), compressImage(), computeTargetSize(), MAX_COMPRESSED_BYTES, MAX_COMPRESSED_DIMENSION (+1 more)

### Community 52 - "features.py"
Cohesion: 0.31
Nodes (3): get_tenant_features(), has_feature(), set_tenant_plan()

### Community 53 - "dependencies"
Cohesion: 0.22
Nodes (9): dependencies, qrcode.react, react, react-dom, react-router-dom, tailwindcss, @tailwindcss/vite, @tanstack/react-query (+1 more)

### Community 54 - "services"
Cohesion: 0.22
Nodes (8): entrypoint, root, framework, root, rewrites, services, backend, frontend

### Community 55 - "conftest.py"
Cohesion: 0.38
Nodes (3): db_session(), tenant(), user()

### Community 56 - "_override_get_db"
Cohesion: 0.29
Nodes (4): _override_get_db(), test_qa_endpoint_rest_de_polling_sigue_funcionando(), _ws_auth_tokens(), ws_client()

### Community 57 - "scripts"
Cohesion: 0.29
Nodes (7): scripts, build, dev, lint, preview, test, test:watch

### Community 58 - ".oxlintrc.json"
Cohesion: 0.33
Nodes (5): plugins, rules, react/only-export-components, react/rules-of-hooks, $schema

## Knowledge Gaps
- **14 isolated node(s):** `ADR-0014`, `ADR-0014`, `jsdom`, `oxlint`, `tailwindcss` (+9 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 647 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `User` to `test_quality.py`, `routers/admin.py`, `services/incidencias.py`, `models/__init__.py`, `Tenant`, `receiving.py`, `consume_stock_fifo`, `test_qa_websockets.py`, `routers/incidencias.py`, `stock.py`, `test_incidencias.py`, `test_websockets.py`, `record_production`, `ws.py`, `log_event`, `make_stock_item`, `make_material`, `make_user`, `login`, `e2e_admin.py`, `helpers.py`, `trace.py`, `login`, `routers/production.py`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `User` (e.g. with `Incidencia` and `IncidenciaHistorial`) actually correct?**
  _`User` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ADR-0014`, `ADR-0014`, `jsdom` to the rest of the system?**
  _14 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `test_quality.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05754527162977867 - nodes in this community are weakly interconnected._
- **Why does `make_order_line()` connect `make_order_line` to `test_quality.py`, `test_orders_router.py`, `Tenant`, `e2e_admin.py`, `consume_stock_fifo`, `calcular_oee`, `helpers.py`, `test_incidencias.py`, `record_production`, `make_stock_item`, `make_material`, `make_user`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `Base` (e.g. with `preparar_bd()` and `main()`) actually correct?**
  _`Base` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Should `routers/admin.py` be split into smaller, more focused modules?**
  _Cohesion score 0.0706605222734255 - nodes in this community are weakly interconnected._