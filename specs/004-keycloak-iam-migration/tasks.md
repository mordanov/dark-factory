# Tasks: Keycloak IAM Migration

**Input**: Design documents from `specs/004-keycloak-iam-migration/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Organization**: Tasks are grouped by user story and phase. US1–US4 map to spec.md priorities.
All 6 backends receive the same auth pattern changes (parallel within each phase).
Phases 1–2 are blocking prerequisites; Phases 3–7 can proceed in parallel once Phase 2 is done.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no cross-task dependencies within the phase)
- **[Story]**: US1 = SSO Login, US2 = Admin via Keycloak, US3 = Service-to-Service, US4 = Data Integrity

---

## Phase 1: Setup — New Infrastructure Files

**Purpose**: New infrastructure files required by all user stories. No service changes yet.

- [ ] T001 [P] Create `infra/keycloak/realm-export.json` — full realm definition with `${VAR}` placeholders: realm settings, 2 realm roles (user, administrator), 9 client registrations (uim-frontend, tm-frontend, oauth2-proxy, orchestrator, context-distiller, agent-dispatcher, agent-tools, user-input-manager, ticket-manager), Google IdP placeholder (`enabled: false`), bootstrap admin user; all secrets as `${KC_*_CLIENT_SECRET}` variables (see contracts/keycloak-realm.md)
- [ ] T002 [P] Create `infra/keycloak/substitute-env.sh` — `envsubst < realm-export.json > realm.json`, chmod +x, set -e
- [ ] T003 [P] Create `infra/oauth2-proxy/config.cfg` — provider=keycloak-oidc, oidc_issuer_url=http://keycloak:8080/realms/dark-factory, skip_jwt_bearer_tokens=true, set_xauthrequest=true, email_domains=[*], cookie_name=_oauth2_proxy_df (see contracts/nginx-auth.md)
- [ ] T004 Add `keycloak` and `oauth2-proxy` service definitions to `infra/docker-compose.yml`; add `depends_on: keycloak: condition: service_healthy` to all 6 application services; Keycloak healthcheck polls `http://localhost:8080/realms/dark-factory` with interval:15s retries:20 start_period:60s; Keycloak entrypoint runs substitute-env.sh before kc.sh start (see contracts/keycloak-realm.md for full yaml)
- [ ] T005 [P] Add keycloak database to `infra/postgres/init/01_create_databases.sql`: CREATE DATABASE keycloak; CREATE USER keycloak_user; GRANT ALL PRIVILEGES ON DATABASE keycloak; ALTER DATABASE keycloak OWNER TO keycloak_user
- [ ] T006 [P] Rewrite auth-related sections of `infra/.env.example`: remove UIM_SECRET_KEY, TM_SECRET_KEY, TM_REFRESH_SECRET, ORCH_SECRET_KEY, DISTILLER_SECRET_KEY, AGENT_TOOLS_SECRET_KEY, DISPATCHER_SECRET_KEY, TM_SERVICE_EMAIL, TM_SERVICE_PASSWORD, UIM_ADMIN_EMAIL, UIM_ADMIN_PASSWORD, TM_ADMIN_EMAIL, TM_ADMIN_PASSWORD; add KC_BOOTSTRAP_ADMIN_USERNAME/EMAIL/PASSWORD, KC_DB_USERNAME/PASSWORD, KC_HOSTNAME, OAUTH2_PROXY_CLIENT_SECRET, OAUTH2_PROXY_COOKIE_SECRET, KC_*_CLIENT_SECRET (one per service), GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, UIM_FRONTEND_URL, TM_FRONTEND_URL, VITE_KEYCLOAK_URL/REALM, VITE_UIM_CLIENT_ID, VITE_TM_CLIENT_ID (see contracts/keycloak-realm.md)

---

## Phase 2: Foundational — Backend Auth Patterns (All Services)

**Purpose**: `KeycloakValidator`, `UserClaims`, config changes, and test fixtures that ALL user stories depend on.

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete.

- [ ] T007 [P] Rewrite `services/user-input-manager/backend/src/core/auth_adapter.py` → `KeycloakValidator` with `UserClaims` dataclass; JWKS cache (300s TTL, `time.monotonic()`); `AUTH_MODE=keycloak` uses RS256 JWKS; `AUTH_MODE=local` uses HS256 with `test_jwt_secret`; `UnauthorizedError` for invalid tokens; stale JWKS cache on refresh failure + log warning (see contracts/auth-adapter.md for full interface)
- [ ] T008 [P] Rewrite `services/ticket-manager/backend/src/core/auth_adapter.py` → same `KeycloakValidator` pattern as T007
- [ ] T009 [P] Rewrite `services/orchestrator/src/core/auth_adapter.py` → same `KeycloakValidator` pattern as T007
- [ ] T010 [P] Rewrite `services/context-distiller/src/core/auth_adapter.py` → same `KeycloakValidator` pattern as T007
- [ ] T011 [P] Rewrite `services/agent-dispatcher/src/core/auth_adapter.py` → same `KeycloakValidator` pattern as T007
- [ ] T012 [P] Rewrite `services/agent-tools/src/core/auth_adapter.py` → same `KeycloakValidator` pattern as T007
- [ ] T013 [P] Update `services/user-input-manager/backend/src/core/config.py`: remove `jwt_secret_key`, `jwt_algorithm`, `access_token_expires_minutes`, `refresh_token_expires_days`, `initial_admin_email`, `initial_admin_password`, `ticket_manager_service_email`, `ticket_manager_service_password`; add `keycloak_base_url: str = "http://keycloak:8080"`, `keycloak_realm: str = "dark-factory"`, `keycloak_client_id: str = ""`, `keycloak_client_secret: str = ""`, `auth_mode: str = "keycloak"`, `test_jwt_secret: str = "test-secret-do-not-use-in-production"` (see data-model.md)
- [ ] T014 [P] Update `services/ticket-manager/backend/src/core/config.py`: remove `secret_key`, `refresh_token_secret`, `access_token_expire_minutes`, `default_admin_email`, `default_admin_password`, `default_user_email`, `default_user_password`, `ticket_manager_service_email`; add same KC vars as T013
- [ ] T015 [P] Update `services/orchestrator/src/core/config.py`: remove `jwt_secret_key`, `jwt_algorithm`, `ticket_manager_service_email`, `ticket_manager_service_password`; add KC vars; keep all other fields unchanged
- [ ] T016 [P] Update `services/context-distiller/src/core/config.py`: remove jwt vars (if present); add KC vars
- [ ] T017 [P] Update `services/agent-dispatcher/src/core/config.py`: remove `jwt_secret_key`, `jwt_algorithm`, `service_jwt_expire_hours`; add KC vars
- [ ] T018 [P] Update `services/agent-tools/src/core/config.py`: remove jwt vars (if present); add KC vars
- [ ] T019 [P] Update `services/user-input-manager/backend/tests/conftest.py`: add `user_token` fixture (HS256, realm_access.roles=["user"]), `admin_token` fixture (realm_access.roles=["user","administrator"]), `set_auth_mode` autouse fixture (`monkeypatch.setenv("AUTH_MODE","local")` + TEST_JWT_SECRET) (see contracts/auth-adapter.md test section)
- [ ] T020 [P] Update `services/ticket-manager/backend/tests/conftest.py`: same fixtures as T019
- [ ] T021 [P] Update `services/orchestrator/tests/conftest.py`: same fixtures as T019
- [ ] T022 [P] Update `services/context-distiller/tests/conftest.py`: same fixtures as T019
- [ ] T023 [P] Update `services/agent-dispatcher/tests/conftest.py`: same fixtures as T019
- [ ] T024 [P] Update `services/agent-tools/tests/conftest.py`: same fixtures as T019

**Checkpoint**: All backends have `KeycloakValidator` + updated configs + test fixtures. User story implementation can proceed.

---

## Phase 3: User Story 1 — SSO Frontend Integration (Priority: P1) 🎯 MVP

**Goal**: Both frontends use keycloak-js for authentication; users log in via Keycloak and access both apps without re-entering credentials.

**Independent Test**: Create a user in Keycloak Admin Console, open either frontend, get redirected to Keycloak login, log in, land in the app with user name displayed. Open the other frontend — no login prompt required (SSO). See quickstart.md Scenario 1.

- [ ] T025 [P] [US1] Create `services/user-input-manager/frontend/src/keycloak.ts` — export default `new Keycloak({ url: import.meta.env.VITE_KEYCLOAK_URL, realm: import.meta.env.VITE_KEYCLOAK_REALM, clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID })`
- [ ] T026 [P] [US1] Create `services/ticket-manager/frontend/src/keycloak.ts` — same as T025
- [ ] T027 [P] [US1] Rewrite `services/user-input-manager/frontend/src/store/authStore.ts` — Zustand store wrapping keycloak-js: `initialized: bool`, `user: {sub, email, username, isAdmin}|null`, `initialize()` calls `keycloak.init({onLoad:'login-required',pkceMethod:'S256'})`, sets `onTokenExpired` handler, `logout()` calls `keycloak.logout()`, `getToken()` calls `keycloak.updateToken(30)`, `getAuthHeader()` returns `{Authorization: Bearer <token>}` (see research.md Decision 7, contracts/auth-adapter.md)
- [ ] T028 [P] [US1] Rewrite `services/ticket-manager/frontend/src/store/authStore.ts` — same pattern as T027
- [ ] T029 [P] [US1] Create `services/user-input-manager/frontend/src/components/layout/LoadingScreen.tsx` — full-page spinner, "Connecting to Dark Factory…" text, dark background; no application content visible
- [ ] T030 [P] [US1] Create `services/ticket-manager/frontend/src/components/layout/LoadingScreen.tsx` — same as T029
- [ ] T031 [US1] Update `services/user-input-manager/frontend/src/App.tsx` — import `useAuthStore` and `LoadingScreen`; call `initialize()` in `useEffect([], [])` on mount; render `<LoadingScreen />` while `!initialized`; all routes inside `<BrowserRouter>` rendered only when initialized
- [ ] T032 [US1] Update `services/ticket-manager/frontend/src/App.tsx` — same pattern as T031
- [ ] T033 [P] [US1] Update UIM `services/user-input-manager/frontend/src/api/client.ts` — Axios request interceptor calls `await useAuthStore.getState().getAuthHeader()`; response interceptor calls `initialize()` on 401; remove old localStorage token read and old 401 handler that cleared localStorage
- [ ] T034 [P] [US1] Update TM `services/ticket-manager/frontend/src/api/client.ts` — same pattern as T033
- [ ] T035 [P] [US1] Add `VITE_KEYCLOAK_URL`, `VITE_KEYCLOAK_REALM`, `VITE_KEYCLOAK_CLIENT_ID` to `services/user-input-manager/frontend/.env.example` with values `http://localhost:8080`, `dark-factory`, `uim-frontend`
- [ ] T036 [P] [US1] Add same env vars to `services/ticket-manager/frontend/.env.example` with `client_id=tm-frontend`

**Checkpoint**: Both frontends redirect to Keycloak login; SSO works across apps; tokens in-memory only.

---

## Phase 4: User Story 1 — Backend Auth Integration & nginx

**Goal**: nginx validates Bearer tokens via oauth2-proxy; backend route handlers use `UserClaims` instead of `User` ORM; local auth endpoints removed.

**Independent Test**: `curl http://tickets.dark-factory.local/api/v1/projects` returns `{"detail":"Not authenticated"}` (401 JSON, not HTML). With valid Bearer token: returns projects list. See quickstart.md Scenario 2.

- [ ] T037 [US1] Update `infra/nginx/nginx.conf.template` — add to BOTH `/api/` location blocks: `auth_request /oauth2/auth`, `auth_request_set` for user/email headers, `proxy_set_header` forwarding, `error_page 401 = @error401`; add shared `location = /oauth2/auth` (internal), `location @error401` (JSON 401 response), `location /oauth2/` (proxy to oauth2-proxy:4180) per server block; do NOT add auth_request to `/`, `/.well-known/`, `/oauth2/` locations (see contracts/nginx-auth.md)
- [ ] T038 [US1] Rewrite `services/user-input-manager/backend/src/api/dependencies.py` (or equivalent get_current_user location) — `get_current_user` returns `UserClaims` from `KeycloakValidator.verify()`; no DB lookup; `require_admin` checks `claims.is_admin`; remove old `require_role` and `_service_account_or_admin` functions
- [ ] T039 [US1] Rewrite `services/ticket-manager/backend/src/core/security.py` `get_current_user` — returns `UserClaims` from `KeycloakValidator.verify()`; remove `decode_access_token`, `verify_access_token`, `hash_password`, `verify_password`, `create_access_token`; keep `require_service_account_or_admin` signature but update to use `claims.is_admin` check
- [ ] T040 [P] [US1] Delete `services/user-input-manager/backend/src/api/v1/auth.py` (POST /auth/login and POST /auth/refresh endpoints)
- [ ] T041 [P] [US1] Delete `services/ticket-manager/backend/src/api/v1/auth.py` (POST /auth/login, /auth/token, /auth/refresh, /auth/logout endpoints)
- [ ] T042 [P] [US1] Delete `services/user-input-manager/backend/src/services/auth_service.py` (local password auth service)
- [ ] T043 [P] [US1] Remove auth and users router registrations from `services/user-input-manager/backend/src/main.py`
- [ ] T044 [P] [US1] Remove auth router registration from `services/ticket-manager/backend/src/main.py`
- [ ] T045 [US1] Update all route handlers in `services/ticket-manager/backend/src/api/v1/` that accept `current_user: User = Depends(get_current_user)` to accept `current_user: UserClaims = Depends(get_current_user)` and update field accesses (`current_user.id` → `current_user.sub`, `current_user.role == "administrator"` → `current_user.is_admin`) — scan all files under `backend/src/api/v1/`
- [ ] T046 [US1] Update all route handlers in `services/user-input-manager/backend/src/api/v1/` that accept `User` ORM from `get_current_user` to accept `UserClaims` — update all field accesses accordingly

**Checkpoint**: nginx rejects unauthenticated /api/ requests with JSON 401; backends parse UserClaims from token.

---

## Phase 5: User Story 2 — Admin Console Access (Priority: P2)

**Goal**: Admin users see a link to the Keycloak Admin Console in the sidebar. All local user management screens removed from both frontends.

**Independent Test**: Log in as a user with `administrator` role — sidebar shows "Keycloak Admin Console" link. Log in as regular user — link absent. No `/login` or `/admin` route exists in either frontend. See quickstart.md Scenario 3.

- [ ] T047 [P] [US2] Update `services/user-input-manager/frontend/src/pages/AppRoutes.tsx` — remove `/login` route, remove `RequireAuth` wrapper, remove `/admin` route (admin UI replaced by Keycloak console); all routes accessible directly (keycloak-js enforces auth at init)
- [ ] T048 [P] [US2] Update `services/ticket-manager/frontend/src/pages/AppRoutes.tsx` — same changes as T047 (remove /login, RequireAuth guards)
- [ ] T049 [P] [US2] Update UIM `services/user-input-manager/frontend/src/components/layout/Sidebar.tsx` (or NavBar/layout equivalent) — remove Admin nav item; replace `logout` handler with `useAuthStore.getState().logout()`; add conditional link to Keycloak Admin Console (`${import.meta.env.VITE_KEYCLOAK_URL}/admin/dark-factory/console`) visible only when `user?.isAdmin === true`; target="_blank"
- [ ] T050 [P] [US2] Update TM `services/ticket-manager/frontend/src/components/layout/Sidebar.tsx` — same Sidebar changes as T049
- [ ] T051 [P] [US2] Delete `services/user-input-manager/frontend/src/components/auth/LoginPage.tsx` (local login form — replaced by Keycloak)
- [ ] T052 [P] [US2] Delete `services/user-input-manager/backend/src/api/v1/users.py` (user CRUD endpoints — management now via Keycloak console) and `services/user-input-manager/backend/src/services/user_service.py`

**Checkpoint**: No local login page; admin link appears for administrator role users; no /admin route in either frontend.

---

## Phase 6: User Story 3 — Service-to-Service Authentication (Priority: P3)

**Goal**: All inter-service HTTP calls use Keycloak Client Credentials tokens. `create_service_token()` is removed from agent-dispatcher. Agents receive a Keycloak token at spawn time.

**Independent Test**: Get a service token via Client Credentials grant for `orchestrator` client; use it to call `/api/v1/projects` on TM — 200 response. See quickstart.md Scenarios 4 & 5.

- [ ] T053 [P] [US3] Create `services/user-input-manager/backend/src/core/keycloak_client.py` — `KeycloakServiceClient` class with `asyncio.Lock` double-checked locking, 30s refresh buffer, `get_token()`, `async_auth_headers()`; module-level `get_kc_client()` singleton (see contracts/keycloak-service-client.md for full implementation)
- [ ] T054 [P] [US3] Create `services/ticket-manager/backend/src/core/keycloak_client.py` — same pattern as T053
- [ ] T055 [P] [US3] Create `services/orchestrator/src/core/keycloak_client.py` — same pattern as T053
- [ ] T056 [P] [US3] Create `services/context-distiller/src/core/keycloak_client.py` — same pattern as T053
- [ ] T057 [P] [US3] Create `services/agent-dispatcher/src/core/keycloak_client.py` — same pattern as T053
- [ ] T058 [P] [US3] Create `services/agent-tools/src/core/keycloak_client.py` — same pattern as T053
- [ ] T059 [US3] Rewrite `services/orchestrator/src/services/tm_client/client.py` — remove `_login()` method, remove `_token` instance variable; replace `_headers()` to call `await get_kc_client().async_auth_headers()`; remove `ticket_manager_service_email` and `ticket_manager_service_password` from usage (see contracts/keycloak-service-client.md)
- [ ] T060 [US3] Update `services/agent-dispatcher/src/services/reporter.py` — replace `create_service_token()` call with `await get_kc_client().async_auth_headers()`; headers dict becomes `{**await get_kc_client().async_auth_headers(), "Content-Type": "application/json"}`
- [ ] T061 [US3] Update `services/agent-dispatcher/src/services/context_builder.py` (or equivalent agent context generation file) — add call to `await get_kc_client().get_token()` before agent spawn; inject token into agent context under `## Service Token` section with TM base URL (see spec Part 6 for exact format)
- [ ] T062 [US3] Update UIM outbound service clients — find all `httpx` calls in `services/user-input-manager/backend/src/` that used `ticket_manager_service_email`/`ticket_manager_service_password` for authentication; replace with `await get_kc_client().async_auth_headers()`; check `services/`, `ticket_manager/client.py`, `ticket_manager/plan_client.py`
- [ ] T063 [P] [US3] Delete `services/agent-dispatcher/src/core/security.py` `create_service_token()` function; retain `verify_access_token()` if still used by inbound auth; otherwise delete the file entirely if `KeycloakValidator` fully replaces it

**Checkpoint**: Orchestrator, UIM, and Agent Dispatcher use Keycloak CC tokens for outbound calls; agents receive fresh token at spawn time.

---

## Phase 7: User Story 4 — Destructive Database Migrations (Priority: P4)

**Goal**: `users` table removed from UIM and TM databases; `user_id` columns changed to `TEXT NOT NULL` (Keycloak `sub`). All business data preserved.

**Independent Test**: After migration, all tickets/projects queryable via API. No `users` table exists in either DB. `user_id` columns hold string values (not UUIDs). See quickstart.md Scenario 6.

- [ ] T064 [P] [US4] Create Alembic migration in `services/user-input-manager/backend/alembic/versions/` — description: `"DESTRUCTIVE: drops all user data"`; upgrade: (1) add `user_id_text TEXT` to prompt_sessions, (2) `UPDATE prompt_sessions SET user_id_text = user_id::text`, (3) drop FK constraint on sessions.user_id, (4) drop users table, (5) rename/alter sessions.user_id column to TEXT NOT NULL using user_id_text values; downgrade: `raise NotImplementedError("DESTRUCTIVE: cannot undo user table removal (constitution §XXI)")` (see data-model.md for exact column inventory)
- [ ] T065 [P] [US4] Create Alembic migration in `services/ticket-manager/backend/alembic/versions/` — description: `"DESTRUCTIVE: drops all user data"`; upgrade: (1) alter `tickets.created_by_id UUID FK → TEXT NOT NULL`, (2) alter `ticket_assignments.user_id UUID FK → TEXT NOT NULL`, (3) alter `ticket_events.actor_id UUID FK → TEXT NOT NULL`, (4) alter `progress_updates.user_id UUID FK → TEXT NOT NULL`, (5) drop `refresh_tokens` table, (6) drop `users` table; downgrade: `raise NotImplementedError`
- [ ] T066 [P] [US4] Delete `User` ORM class from `services/user-input-manager/backend/src/models/models.py` and all imports of `User` in UIM backend; update `PromptSession` model: `user_id` column type from `UUID FK → users.id` to `TEXT NOT NULL`
- [ ] T067 [P] [US4] Delete `User` ORM class from `services/ticket-manager/backend/src/models/user.py` (or equivalent); update `Ticket`, `TicketAssignment`, `TicketEvent`, `ProgressUpdate` models: all `user_id`/`created_by_id`/`actor_id` columns from `UUID FK → TEXT NOT NULL`; delete `RefreshToken` model
- [ ] T068 [US4] Update UIM `SessionService` (and any other service methods) that accept `user_id: UUID` — change to `user_id: str` throughout `services/user-input-manager/backend/src/services/`; Keycloak sub is a UUID string stored as TEXT
- [ ] T069 [US4] Update TM schemas (`backend/src/schemas/`) — any response schema that embeds a `UserResponse`/`UserSummary` with DB-fetched fields should instead embed `UserClaims`-derived data (sub as `user_id`, email from claims); remove any schema that implies a DB users lookup; ensure `TicketResponse.created_by` works with TEXT user_id

**Checkpoint**: Databases have no users table; all user_id columns store Keycloak sub strings; existing tickets/projects accessible.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T070 [P] Create `services/user-input-manager/backend/tests/unit/test_auth_adapter.py` — 8 tests: valid user token returns UserClaims, admin token has is_admin=True, invalid token raises UnauthorizedError, expired token raises UnauthorizedError, missing realm_access returns empty roles, keycloak mode fetches JWKS (mock httpx), JWKS cached within TTL (httpx called once), JWKS refreshed after TTL (httpx called twice) — AUTH_MODE=local for all except the JWKS tests
- [ ] T071 [P] Create `services/ticket-manager/backend/tests/unit/test_auth_adapter.py` — same 8 tests as T070
- [ ] T072 [P] Create `services/orchestrator/tests/unit/test_auth_adapter.py` — same 8 tests
- [ ] T073 [P] Create `services/context-distiller/tests/unit/test_auth_adapter.py` — same 8 tests
- [ ] T074 [P] Create `services/agent-dispatcher/tests/unit/test_auth_adapter.py` — same 8 tests
- [ ] T075 [P] Create `services/agent-tools/tests/unit/test_auth_adapter.py` — same 8 tests
- [ ] T076 [P] Create `services/orchestrator/tests/unit/test_keycloak_client.py` — 5 tests: get_token calls KC endpoint, token cached until expiry, token refreshed 30s before expiry, concurrent calls use single request (asyncio Lock), KC error raises UpstreamError (see contracts/keycloak-service-client.md)
- [ ] T077 [P] Create `services/agent-dispatcher/tests/unit/test_keycloak_client.py` — same 5 tests as T076
- [ ] T078 [P] Create `services/user-input-manager/backend/tests/unit/test_keycloak_client.py` — same 5 tests as T076
- [ ] T079 Run ruff lint + format on all changed Python files across all 6 backend services: `ruff check --fix services/*/backend/src/ services/*/src/` and `ruff format services/*/backend/src/ services/*/src/`
- [ ] T080 [P] Create `infra/KEYCLOAK.md` — first boot instructions, accessing Admin Console, creating users, assigning administrator role, enabling Google login, re-importing realm (see spec Part 9.1 for content)
- [ ] T081 [P] Verify quickstart.md Scenarios 1–8 work against a locally running `docker compose up`: SSO login, API auth, admin link, service-to-service token, agent token injection, data integrity, automated tests with AUTH_MODE=local, logout; update quickstart.md if any steps are stale

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — T001–T006 all parallel; start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion (config env vars must be known); T007–T024 all parallel
- **US1 Frontend (Phase 3)**: Depends on Phase 2 (authStore uses KC vars from config); T025–T036 all parallel
- **US1 Backend (Phase 4)**: Depends on Phase 2 (KeycloakValidator must exist for dependencies.py); T037–T046 partially parallel
- **US2 Admin (Phase 5)**: Depends on Phase 3 (authStore with `user.isAdmin` must exist for sidebar); T047–T052 all parallel
- **US3 Service Auth (Phase 6)**: Depends on Phase 2 only (config has KC vars); T053–T063 partially parallel; independent of Phase 3/4/5
- **US4 Migrations (Phase 7)**: Depends on Phase 2 only (KeycloakValidator must be ready to accept UserClaims); T064–T069 partially parallel; independent of Phase 3/4/5/6
- **Polish (Phase 8)**: Depends on all phases complete

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — no dependency on US2/US3/US4
- **US2 (P2)**: Depends on US1 Phase 3 (needs authStore with isAdmin)
- **US3 (P3)**: Can start after Phase 2 — fully independent of US1/US2/US4
- **US4 (P4)**: Can start after Phase 2 — fully independent of US1/US2/US3

### Within Each Phase

- auth_adapter rewrites: implement, then test fixtures confirm LOCAL mode works
- KeycloakServiceClient: implement before updating callers (T059–T063 depend on T053–T058)
- Destructive migrations: write migration → update ORM model → update service methods → update schemas (T064 → T066 → T068; T065 → T067 → T069)

---

## Parallel Execution Examples

### Phase 2 — All 6 services in parallel

```
T007 auth_adapter.py UIM        ─┐
T008 auth_adapter.py TM         ─┤
T009 auth_adapter.py orchestrator─┤ all in parallel (different files)
T010 auth_adapter.py distiller  ─┤
T011 auth_adapter.py dispatcher ─┤
T012 auth_adapter.py agent-tools─┘

T013 config.py UIM              ─┐
T014 config.py TM               ─┤
T015 config.py orchestrator     ─┤ all in parallel
T016 config.py distiller        ─┤
T017 config.py dispatcher       ─┤
T018 config.py agent-tools      ─┘

T019–T024 conftest.py × 6       — all in parallel
```

### Phase 3+4 — Frontend parallel with Backend

```
Phase 3 (frontend):  T025–T036 (keycloak.ts, authStore, App.tsx, LoadingScreen, client.ts)
Phase 6 (backend):   T053–T063 (keycloak_client.py × 6, update callers)
Phase 7 (migration): T064–T069 (Alembic migrations + ORM cleanup)

All three streams can proceed simultaneously after Phase 2.
```

---

## Implementation Strategy

### MVP (US1 only — SSO Login Working)

1. Phase 1 (T001–T006) — infra files
2. Phase 2 (T007–T024) — backend patterns
3. Phase 3 (T025–T036) — frontend keycloak-js
4. Phase 4 T037 only — nginx template
5. T038–T039 — backend dependencies update
6. **STOP and VALIDATE**: docker compose up; open frontend; login via Keycloak; API call with token succeeds
7. Demo/deploy if ready

### Full Incremental Delivery

1. Phase 1 + 2 → Foundation
2. Phase 3 + 4 → US1 complete (SSO + auth validation)
3. Phase 5 → US2 complete (admin console link, UI cleanup)
4. Phase 6 → US3 complete (service-to-service CC tokens)
5. Phase 7 → US4 complete (destructive migrations)
6. Phase 8 → Polish, tests, docs

### Parallel Team Strategy (3 developers after Phase 2)

- Developer A: US1 (Phase 3 frontend + Phase 4 backend + Phase 5 admin UI)
- Developer B: US3 (Phase 6 — keycloak_client.py + caller updates)
- Developer C: US4 (Phase 7 — destructive migrations + ORM cleanup)

---

## Notes

- `[P]` tasks target different files with no within-phase cross-dependencies
- `AUTH_MODE=local` enables all existing tests to pass without a real Keycloak instance
- The `UserClaims` dataclass is embedded in `auth_adapter.py` per service — not a shared library (Principle I)
- Destructive migrations (T064, T065) are irreversible by constitution §XXI; test migration in a throwaway DB before applying to a real environment
- `create_service_token()` in agent-dispatcher (T063) should be deleted only after T057 (keycloak_client.py) is confirmed working
- Check that orchestrator `tm_client/client.py` also handles token refresh correctly — old `_login()` pattern re-authenticated on 401; new pattern relies on `KeycloakServiceClient` cache; add 401 retry logic if needed
- Frontend unit tests: keycloak-js should be mocked in Vitest (`vi.mock('../keycloak')`) so tests don't need a real Keycloak server
- Google IdP in realm-export.json: `"enabled": false` — verify this field renders correctly after `substitute-env.sh` runs (static field, not a variable)
