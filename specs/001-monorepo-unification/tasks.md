---
description: "Task list for Dark Factory Monorepo Unification"
---

# Tasks: Dark Factory Monorepo Unification

**Input**: Design documents from `specs/001-monorepo-unification/`
**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/ ✅

**Organization**: Tasks are grouped by user story to enable independent implementation
and testing of each story. No test tasks generated (not requested in spec).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)
- Include exact file paths in descriptions

---

## Phase 1: Setup — Monorepo Scaffold

**Purpose**: Move services into `services/` and create the top-level directory skeleton.
All subsequent phases depend on this structure being in place.

- [ ] T001 Move `user-input-manager/` to `services/user-input-manager/` (git mv)
- [ ] T002 Move `ticket-manager/` to `services/ticket-manager/` (git mv)
- [ ] T003 Move `orchestrator/` to `services/orchestrator/` (git mv)
- [ ] T004 Move `context-distiller/` to `services/context-distiller/` (git mv)
- [ ] T005 Move `agent-tools/` to `services/agent-tools/` (git mv)
- [ ] T006 [P] Create directory tree: `infra/nginx/snippets/` and `infra/postgres/init/`
- [ ] T007 [P] Create directory tree: `integration-tests/tests/` and `integration-tests/llm-mock/`
- [ ] T008 Create root `.gitignore` covering `infra/.env`, `**/node_modules/`, `**/__pycache__/`, `**/.pytest_cache/`, `**/.ruff_cache/`, `**/dist/`, `**/coverage/`
- [ ] T009 Create root `pyproject.toml` with `[tool.versions]` canonical Python dependency table and `[tool.ruff]` config (line-length 100, target-version py312, select E/W/I/UP)
- [ ] T010 Create root `package.json` with canonical frontend dependency versions (reference only, no workspaces)
- [ ] T011 Update `CLAUDE.md` at monorepo root with service map, ports, database names, internal URLs, and sibling project paths
- [ ] T012 Create `README.md` at monorepo root with getting started, service map, and port table

**Checkpoint**: Directory structure matches constitution layout. Services at `services/*/`.

---

## Phase 2: Foundational — Shared Infrastructure

**Purpose**: Infra files that the unified compose and integration tests depend on.
Phases 3–7 (user story streams) can begin after Phase 1; this phase runs in parallel
with stories but must complete before integration tests (Phase 6) can run.

**⚠️ CRITICAL for Phase 6**: Unified compose must be healthy before integration tests run.

- [ ] T013 [P] Create `infra/postgres/init/01_create_databases.sql` creating databases `df_user_input`, `df_ticket_manager`, `df_orchestrator`, `df_distiller` and their dedicated users from env vars; GRANT ALL PRIVILEGES per user per database
- [ ] T014 [P] Create `infra/nginx/snippets/proxy.conf` with `proxy_set_header Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, `proxy_read_timeout 60s`, `proxy_connect_timeout 10s`
- [ ] T015 [P] Create `infra/nginx/snippets/ssl.conf` with commented SSL parameter stanzas (TLSv1.2/1.3, session cache) per `contracts/nginx-routing.md`
- [ ] T016 Create `infra/nginx/nginx.conf.template` with two server blocks (`$UIM_HOST`, `$TM_HOST`): each with `/api/` proxy, `/` SPA fallback, `/.well-known/acme-challenge/` location, commented SSL stanza and HTTP→HTTPS redirect block per `contracts/nginx-routing.md`
- [ ] T017 Create `infra/nginx/Dockerfile` based on `nginx:alpine`; entrypoint runs `envsubst '$UIM_HOST $TM_HOST' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf && nginx -g 'daemon off;'`
- [ ] T018 Create `infra/docker-compose.yml` defining all 8 containers (user-input-manager, ticket-manager, orchestrator, context-distiller, agent-tools, postgres, mongo, nginx) with healthchecks, `depends_on` conditions, shared `internal` network, and build contexts pointing to `./services/*/` per `data-model.md` service registry
- [ ] T019 Create `infra/docker-compose.override.yml` exposing ports 8001–8005 on host for local development
- [ ] T020 Create `infra/.env.example` with all 10 variable groups from `data-model.md`; every variable has an inline comment with purpose, which services use it, and default value

**Checkpoint**: `docker compose -f infra/docker-compose.yml config` validates without errors.

---

## Phase 3: User Story 1 — Full Stack Starts with One Command (Priority: P1)

**Goal**: `docker compose -f infra/docker-compose.yml up --build` starts all services
with no errors and all healthchecks pass.

**Independent Test**: Run compose on a clean environment with `.env` populated.
All containers reach `healthy` within 60 seconds. Nginx serves both frontends.

### Implementation for User Story 1

- [ ] T021 [US1] Add `GET /health` endpoint to `services/user-input-manager/backend/src/api/v1/health.py` returning `{"status": "ok"}` (if not already present); register in `main.py`
- [ ] T022 [US1] Add `GET /health` endpoint to `services/ticket-manager/backend/src/api/v1/health.py` returning `{"status": "ok"}` (if not already present); register in `main.py`
- [ ] T023 [US1] Add `GET /health` endpoint to `services/orchestrator/src/api/v1/health.py` returning `{"status": "ok"}` (if not already present); register in `main.py`
- [ ] T024 [US1] Add `GET /health` endpoint to `services/context-distiller/src/api/v1/health.py` returning `{"status": "ok"}` (if not already present); register in `main.py`
- [ ] T025 [US1] Add `GET /health` endpoint to `services/agent-tools/src/api/v1/health.py` returning `{"status": "ok"}` (if not already present); register in `main.py`
- [ ] T026 [US1] Add per-service `docker-compose.yml` to `services/user-input-manager/` referencing its own postgres instance with `df_user_input` database (standalone dev mode)
- [ ] T027 [US1] Verify/update `services/ticket-manager/docker-compose.yml` for standalone dev mode with `df_ticket_manager` database
- [ ] T028 [US1] Verify/update `services/orchestrator/docker-compose.yml` for standalone dev mode (postgres + mongo)
- [ ] T029 [US1] Verify/update `services/context-distiller/docker-compose.yml` for standalone dev mode (postgres + mongo)
- [ ] T030 [US1] Verify/update `services/agent-tools/docker-compose.yml` for standalone dev mode
- [ ] T031 [US1] Verify unified compose starts cleanly: run `docker compose -f infra/docker-compose.yml up --build -d` and confirm all healthchecks pass; fix any startup errors

**Checkpoint**: `docker compose ps` shows all 8 containers healthy. Both frontends accessible via nginx.

---

## Phase 4: User Story 2 — Auth Adapter Across All Backends (Priority: P2)

**Goal**: Every backend service has `auth_adapter.py`; `AUTH_MODE=local` is byte-for-byte
identical to pre-migration behaviour; `AUTH_MODE=keycloak` returns 501.

**Independent Test**: Start any backend service in isolation with `AUTH_MODE=local`.
POST valid credentials → receive JWT. GET protected route with JWT → 200. Send tampered
JWT → 401. Set `AUTH_MODE=keycloak`, send any request → 501.

### Implementation for User Story 2

- [ ] T032 [P] [US2] Create `services/user-input-manager/backend/src/core/auth_adapter.py` implementing `AuthAdapter.verify()` wrapping existing `security.verify_access_token()` per `contracts/auth-adapter-interface.md`
- [ ] T033 [P] [US2] Create `services/ticket-manager/backend/src/core/auth_adapter.py` implementing `AuthAdapter.verify()` wrapping existing `security.verify_access_token()` per `contracts/auth-adapter-interface.md`
- [ ] T034 [P] [US2] Create `services/orchestrator/src/core/auth_adapter.py` implementing `AuthAdapter.verify()` wrapping existing `src/core/security.verify_access_token()` per `contracts/auth-adapter-interface.md`
- [ ] T035 [P] [US2] Create `services/context-distiller/src/core/auth_adapter.py` implementing `AuthAdapter.verify()` wrapping existing `src/core/security.verify_access_token()` per `contracts/auth-adapter-interface.md`
- [ ] T036 [P] [US2] Create `services/agent-tools/src/core/auth_adapter.py` implementing `AuthAdapter.verify()` wrapping existing `src/utils/auth.py` validation per `contracts/auth-adapter-interface.md`
- [ ] T037 [US2] Update `services/user-input-manager/backend/src/api/dependencies.py`: replace inline `AuthService.get_current_user()` JWT call with `AuthAdapter(settings).verify(token)`; handle `NotImplementedError` → HTTP 501
- [ ] T038 [US2] Update `services/ticket-manager/backend/src/api/dependencies.py` to use `AuthAdapter` per `contracts/auth-adapter-interface.md`
- [ ] T039 [US2] Update `services/orchestrator/src/api/dependencies.py` to use `AuthAdapter` per `contracts/auth-adapter-interface.md`
- [ ] T040 [US2] Update `services/context-distiller/src/api/dependencies.py` to use `AuthAdapter` per `contracts/auth-adapter-interface.md`
- [ ] T041 [US2] Update `services/agent-tools/src/utils/auth.py` to delegate to `AuthAdapter` per `contracts/auth-adapter-interface.md`
- [ ] T042 [US2] Upgrade `services/ticket-manager/backend/Dockerfile` base image from `python:3.11-slim` to `python:3.12-slim`; update `pyproject.toml` `requires-python = ">=3.12"`; align all dependency versions to canonical versions in root `pyproject.toml` per `research.md` R6 table (remove `mypy`, replace `pytest-asyncio==1.3.0` with canonical `0.24.0`)

**Checkpoint**: All five backend services accept and reject tokens identically to
pre-migration. `AUTH_MODE=keycloak` returns 501 on first authenticated request.

---

## Phase 5: User Story 3 — UIM Zustand Migration (Priority: P3)

**Goal**: `user-input-manager` frontend uses Zustand for auth state; no access token
in `localStorage` or `sessionStorage`; all existing UI behaviour preserved.

**Independent Test**: Open UIM in browser, log in, inspect storage — no `access_token`
key. Navigate to protected route — renders correctly. Page refresh — session restored
from `sessionStorage` refresh token. Logout — Zustand store cleared, redirected to login.

### Implementation for User Story 3

- [ ] T043 [US3] Create `services/user-input-manager/frontend/src/store/auth.ts` with Zustand store mirroring `services/ticket-manager/frontend/src/store/auth.ts` pattern: state `accessToken` (memory), `currentUser`, `refreshToken` (sessionStorage key `"rt"`), `isRestoring`; actions `login()`, `setAccessToken()`, `setRestored()`, `logout()`
- [ ] T044 [US3] Update `services/user-input-manager/frontend/src/api/client.ts`: replace `localStorage.getItem('access_token')` axios interceptor with `useAuthStore.getState().accessToken`; remove all `localStorage.setItem('access_token', ...)` calls
- [ ] T045 [US3] Update `services/user-input-manager/frontend/src/components/auth/LoginPage.tsx`: call `useAuthStore().login(accessToken, refreshToken, partialUser)` instead of `localStorage.setItem`; preserve all existing login form behaviour
- [ ] T046 [US3] Update `services/user-input-manager/frontend/src/App.tsx`: remove `<AuthProvider>` wrapper; add store restoration logic (check sessionStorage for refresh token on mount, call refresh endpoint, call `store.setAccessToken()`)
- [ ] T047 [US3] Update `services/user-input-manager/frontend/src/pages/AppRoutes.tsx`: replace `useAuth()` hook with `useAuthStore()` for `user` and `loading` / `isRestoring` state
- [ ] T048 [US3] Update `services/user-input-manager/frontend/src/components/layout/Sidebar.tsx`: replace `useAuth()` with `useAuthStore()` for user display and logout handler
- [ ] T049 [US3] Delete `services/user-input-manager/frontend/src/context/AuthContext.tsx`
- [ ] T050 [US3] Search entire `services/user-input-manager/frontend/src/` for any remaining `localStorage.getItem('access_token')`, `localStorage.setItem('access_token')`, `useAuth()` or `AuthContext` imports and remove/replace them; verify no access token in storage after login

**Checkpoint**: Browser DevTools show no `access_token` in localStorage/sessionStorage
after login. Zustand store holds the token in memory only. All protected routes work.

---

## Phase 6: User Story 4 — Integration Tests (Priority: P4)

**Goal**: Two integration test scenarios run against real services with LLM calls mocked.
Both pass. Suite completes in under 120 seconds.

**Independent Test**: Start `docker-compose.test.yml`, run `pytest integration-tests/`.
Both scenarios pass. Run with `OPENAI_API_KEY=invalid` — suite still passes (LLM mock used).

**Prerequisite**: Phase 2 (infra compose) must be complete and services must be startable.

### Implementation for User Story 4

- [ ] T051 [P] [US4] Create `integration-tests/requirements.txt` with `pytest==8.3.4`, `pytest-asyncio==0.24.0`, `httpx==0.28.0`, `pyyaml==6.0.2`
- [ ] T052 [P] [US4] Create `integration-tests/llm-mock/main.py` FastAPI stub serving `POST /v1/chat/completions` (canned response) and `GET /health` per `contracts/llm-mock-api.md`
- [ ] T053 [P] [US4] Create `integration-tests/llm-mock/requirements.txt` with `fastapi`, `uvicorn`; create `integration-tests/llm-mock/Dockerfile`
- [ ] T054 [US4] Create `integration-tests/docker-compose.test.yml` extending `infra/docker-compose.yml`: adds `llm-mock` service; overrides `OPENAI_BASE_URL=http://llm-mock:11434/v1` for orchestrator and context-distiller; recreates volumes before test run
- [ ] T055 [US4] Create `integration-tests/conftest.py` with session-scoped fixtures: `uim_client`, `tm_client`, `orch_client` as `httpx.AsyncClient`; `uim_auth_headers`, `tm_auth_headers` (login once per session); `clean_db` function-scoped fixture truncating test tables per `data-model.md` fixture model
- [ ] T056 [US4] Create `integration-tests/tests/test_scenario_a.py` implementing Scenario A (7-step UIM→TM flow per `data-model.md`): login UIM, create session, feedback loops, approve, assert TM ticket has tag `needs-estimation` and description prefix `[needs-estimation]`
- [ ] T057 [US4] Create `integration-tests/tests/test_scenario_c.py` implementing Scenario C (5-step Orchestrator→ContextDistiller flow per `data-model.md`): create done ticket in TM, trigger orchestrator job, poll until done (30s timeout), assert project memory is non-null valid YAML with required keys

**Checkpoint**: `pytest integration-tests/ -v` passes both scenarios in under 120 seconds.
Running with an invalid real API key confirms the LLM mock is serving all LLM calls.

---

## Phase 7: User Story 5 — Python Linting with Pre-Commit (Priority: P5)

**Goal**: Root-level `pre-commit run --all-files` runs ruff lint and ruff-format across
all Python files in `services/`. Per-service `.pre-commit-config.yaml` hooks also work.

**Independent Test**: Introduce a PEP-8 violation in any `services/*/` Python file.
Run `pre-commit run --all-files` from repo root — violation detected and auto-fixed.

### Implementation for User Story 5

- [ ] T058 [P] [US5] Create root-level `.pre-commit-config.yaml` with `repos: [{repo: https://github.com/astral-sh/ruff-pre-commit, rev: v0.8.3, hooks: [{id: ruff, args: [--fix]}, {id: ruff-format}]}]`; include all `services/**/*.py` paths
- [ ] T059 [P] [US5] Create `services/user-input-manager/backend/.pre-commit-config.yaml` with same ruff hooks (service-level, for standalone development)
- [ ] T060 [P] [US5] Create `services/ticket-manager/backend/.pre-commit-config.yaml` with same ruff hooks
- [ ] T061 [P] [US5] Create `services/orchestrator/.pre-commit-config.yaml` with same ruff hooks
- [ ] T062 [P] [US5] Create `services/context-distiller/.pre-commit-config.yaml` with same ruff hooks
- [ ] T063 [P] [US5] Create `services/agent-tools/.pre-commit-config.yaml` with same ruff hooks
- [ ] T064 [US5] Run `pre-commit run --all-files` from repo root; fix any ruff violations surfaced in existing Python files across all services

**Checkpoint**: `pre-commit run --all-files` exits 0 with no unfixable violations.

---

## Phase 8: User Story — Frontend Test Standardisation

**Note**: Not a numbered user story in spec.md but required by FR-009 and SC-007.
Runs in parallel with Phase 5 (Zustand migration).

**Goal**: Both frontends use Vitest with ≥ 80% coverage. No Jest config present.

- [ ] T065 [P] Update `services/user-input-manager/frontend/package.json`: pin `vitest` to `"2.1.8"`, `@vitest/coverage-v8` to `"2.1.8"`, align all canonical frontend versions per constitution Principle V
- [ ] T066 [P] Update `services/user-input-manager/frontend/vite.config.ts` test block: `coverage.thresholds` lines ≥ 80, functions ≥ 80; ensure `provider: 'v8'`; remove any Jest config
- [ ] T067 [P] Update `services/ticket-manager/frontend/vite.config.ts` test block: add `coverage.thresholds` lines ≥ 80, functions ≥ 80 if not already present (currently missing from TM vite config); verify Vitest is runner
- [ ] T068 [P] Run `npm test -- --coverage` in `services/user-input-manager/frontend/`; fix any Vitest 2.x incompatibilities surfaced by the version upgrade
- [ ] T069 [P] Run `npm test -- --coverage` in `services/ticket-manager/frontend/`; confirm coverage thresholds pass

**Checkpoint**: Both `npm test -- --coverage` runs pass with ≥ 80% lines/functions.

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Validation, documentation completeness, and final integration check.

- [ ] T070 [P] Verify `infra/.env.example` has every variable required by all 5 service configs; cross-check against each service's `src/core/config.py` or `settings.py`
- [ ] T071 [P] Add `CLAUDE.md` service map section to `services/user-input-manager/backend/CLAUDE.md` if it lacks one; add service name, port, DB name, auth adapter location
- [ ] T072 Run full Definition of Done checklist from constitution: verify all 13 items pass; document any remaining gaps as follow-up issues
- [ ] T073 Run `docker compose -f infra/docker-compose.yml down -v && docker compose -f infra/docker-compose.yml up --build` on a clean state; confirm no residual state issues
- [ ] T074 Run existing per-service unit tests in each backend to confirm zero regressions from auth adapter insertion and dependency file updates
- [ ] T075 Run existing per-service Vitest suites in both frontends to confirm zero regressions from Zustand migration and version upgrades

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Infra)**: Depends on Phase 1 (services must be at new paths) — BLOCKS Phase 6
- **Phase 3 (US1 — Full Stack)**: Depends on Phase 1 + Phase 2 completion
- **Phase 4 (US2 — Auth Adapter)**: Depends on Phase 1; runs in parallel with Phase 3
- **Phase 5 (US3 — Zustand)**: Depends on Phase 1; runs in parallel with Phases 3–4
- **Phase 6 (US4 — Integration Tests)**: Depends on Phase 2 + Phase 3 (compose must be runnable)
- **Phase 7 (US5 — Pre-Commit)**: Depends on Phase 1; runs in parallel with Phases 3–6
- **Phase 8 (Frontend Tests)**: Depends on Phase 1 + Phase 5 (Zustand migration must be done first)
- **Phase N (Polish)**: Depends on all phases complete

### User Story Dependencies

- **US1 (Full Stack)**: Depends on Phase 1 + Phase 2
- **US2 (Auth Adapter)**: Depends on Phase 1 only — can start immediately after scaffold
- **US3 (Zustand)**: Depends on Phase 1 only — can start immediately after scaffold
- **US4 (Integration Tests)**: Depends on US1 being complete (services must be composable)
- **US5 (Pre-commit)**: Depends on Phase 1 only

### Within Each Phase

- Parallel tasks ([P]) within a phase can run concurrently (different files)
- Sequential tasks in a phase must complete in order

### Parallel Opportunities

```bash
# After Phase 1 completes, launch these streams simultaneously:

# Stream A: Infra + US1
Phase 2 (T013–T020) → Phase 3 (T021–T031)

# Stream B: Auth adapters (can run fully in parallel — 5 different service dirs)
T032 [user-input-manager auth_adapter.py]
T033 [ticket-manager auth_adapter.py]
T034 [orchestrator auth_adapter.py]
T035 [context-distiller auth_adapter.py]
T036 [agent-tools auth_adapter.py]
→ then T037–T042 sequentially

# Stream C: Zustand migration
T043–T050 (sequential, single frontend codebase)

# Stream D: Frontend test standardisation (parallel with Stream C)
T065–T069

# Stream E: Pre-commit hooks (all [P], fully parallel)
T058–T064

# Stream F: Integration tests (wait for Stream A to complete first)
T051–T057
```

---

## Implementation Strategy

### MVP First (User Story 1 + User Story 2)

1. Complete Phase 1: Scaffold (T001–T012)
2. Complete Phase 2: Infra compose (T013–T020)
3. Complete Phase 3: Health endpoints + standalone compose verification (T021–T031)
4. **STOP and VALIDATE**: `docker compose -f infra/docker-compose.yml up --build` passes
5. Complete Phase 4: Auth adapters (T032–T042)
6. **STOP and VALIDATE**: AUTH_MODE=local behaviour unchanged; AUTH_MODE=keycloak returns 501

### Incremental Delivery

1. **Iteration 1**: Scaffold + Infra + US1 → Full platform starts with one command
2. **Iteration 2**: Auth Adapters → Auth seam prepared for Keycloak
3. **Iteration 3**: Zustand migration → No tokens in localStorage
4. **Iteration 4**: Integration tests → Cross-service flows validated
5. **Iteration 5**: Pre-commit + Frontend tests → Code quality enforced

### Parallel Team Strategy

With multiple developers:

1. Everyone completes Phase 1 together (scaffold, ~1 hour)
2. Then split:
   - **Dev A**: Phase 2 (infra compose) + Phase 3 (US1 — full stack)
   - **Dev B**: Phase 4 (auth adapters — all 5 services)
   - **Dev C**: Phase 5 (Zustand migration) + Phase 8 (frontend tests)
   - **Dev D**: Phase 7 (pre-commit hooks)
3. After Phase 3 complete: Dev A picks up Phase 6 (integration tests)
4. All streams converge in Phase N (polish)

---

## Notes

- [P] tasks = different files, no dependencies between them
- [Story] label maps task to specific user story for traceability
- `git mv` in Phase 1 preserves file history — use `git mv`, not `mv`
- Auth adapters (T032–T036) are all [P] — different service directories, no conflicts
- The Zustand migration (Phase 5) must complete before Frontend Test Standardisation (Phase 8) to avoid testing against the old AuthContext
- Do NOT run `pre-commit install` in CI; run `pre-commit run --all-files` directly
- Canonical dependency versions are in `pyproject.toml` `[tool.versions]` — use those, not package registry defaults
