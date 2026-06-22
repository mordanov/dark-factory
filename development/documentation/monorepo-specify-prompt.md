# /speckit.specify — Dark Factory Monorepo Unification

## Prompt (copy-paste into Claude Code)

```
/speckit.specify

Unify five existing Dark Factory services into a single monorepo with
centralised infrastructure. Read all context files before generating the spec.

## Context files (read in this order)

@.specify/memory/constitution.md          ← non-negotiable constraints
@.specify/memory/service-map.md           ← current state of each service
@../user-input-manager/README.md          ← Prompt Studio architecture
@../ticket-manager/README.md              ← Ticket Manager architecture
@../orchestrator/README.md                ← Orchestrator architecture
@../context-distiller/README.md           ← ContextDistiller architecture (if exists)
@../agent-tools/README.md                 ← Agent Tools architecture (if exists)

Do not go above the ../ directory level. Do not read unrelated projects.

## What to specify

### 1. Monorepo scaffold
Create the directory structure defined in the constitution under
`dark-factory/` as the monorepo root. Move each service into
`services/{service-name}/`. Do not rename or reorganise files inside services.

### 2. Centralised infrastructure (`infra/`)
- `docker-compose.yml` — all five services + postgres + mongo + nginx
  as defined in the Service Registry table in the constitution.
  Each service has a healthcheck. Postgres and Mongo have healthchecks.
  Services depend_on their databases with condition: service_healthy.
- `docker-compose.override.yml` — expose individual service ports for
  local development (8001-8005 mapped to host).
- `postgres/init/01_create_databases.sql` — creates all four PG databases
  and their dedicated users from env vars.
- `nginx/Dockerfile` + `nginx.conf.template` — envsubst-based nginx with:
  - One server block per frontend service (UIM, TM)
  - DNS name from env var (UIM_HOST, TM_HOST)
  - /.well-known/acme-challenge/ location in every server block
  - SSL stanza and HTTP→HTTPS redirect (commented, certbot-ready)
  - Proxy to backend API under /api/ path
  - Shared snippet files: ssl.conf, proxy.conf
- `nginx/snippets/` — reusable nginx config fragments
- `.env.example` — every variable commented, grouped as per constitution
- `.pre-commit-config.yaml` — ruff lint + ruff-format for all Python
- `pyproject.toml` — canonical Python versions table + ruff config
- `package.json` — canonical frontend versions (reference, no workspaces)
- `CLAUDE.md` — monorepo map: services, ports, databases, sibling project paths

### 3. Auth adapter (all five backends)
Add `src/core/auth_adapter.py` to each Python backend service.
The adapter reads AUTH_MODE from settings:
- `local`: validates JWT with existing SECRET_KEY logic (no behaviour change)
- `keycloak`: validates against KEYCLOAK_JWKS_URL (stub implementation —
  raise NotImplementedError with a clear message)
Update the FastAPI bearer dependency in each service to call the adapter
instead of the current inline verify function.
Do not change login endpoints, user CRUD, or token generation.

### 4. user-input-manager frontend — Zustand migration
Replace React Context auth state with a Zustand store:
- Create `src/store/auth.ts` (same pattern as ticket-manager's Zustand store)
- Remove `src/context/AuthContext.tsx`
- Access tokens stored in memory only — remove all localStorage token writes
- Refresh tokens may remain in localStorage (only used for session restoration)
- Update all components that currently import from AuthContext to use the store
- Keep all existing behaviour; this is a state management refactor only

### 5. Frontend test runner standardisation
For both user-input-manager and ticket-manager frontends:
- Ensure Vitest is the test runner (remove Jest if present)
- Ensure coverage threshold is 80% lines/functions in vite.config.ts
- Do not rewrite existing tests; only update runner config if needed

### 6. Integration tests (`integration-tests/`)
Implement two scenarios exactly as specified in the constitution:

**Scenario A — UIM → TM ticket creation**
File: `integration-tests/tests/test_scenario_a.py`
Uses real HTTP calls against running services. Mocks OpenAI via
OPENAI_BASE_URL pointing to a WireMock or respx stub server.

**Scenario C — Orchestrator done → ContextDistiller → memory**
File: `integration-tests/tests/test_scenario_c.py`
Polls job status with timeout. Asserts project memory is written and readable.

Shared fixtures in `integration-tests/conftest.py`:
- One httpx.AsyncClient per service (base_url from env vars)
- Authenticated clients (login once, reuse token per test session)
- LLM mock server fixture

`integration-tests/docker-compose.test.yml`:
- Extends `infra/docker-compose.yml`
- Adds LLM mock service (WireMock or a minimal FastAPI stub)
- Overrides OPENAI_BASE_URL for all services to point to the mock

`integration-tests/requirements.txt`:
- pytest==8.3.4
- pytest-asyncio==0.24.0
- httpx==0.28.0
- pyyaml==6.0.2

## Constraints (from constitution — enforce all)

- Python 3.12 in every backend Dockerfile
- Canonical library versions from pyproject.toml in every requirements.txt
- No service reads another service's database
- No access tokens in localStorage in any frontend
- Auth adapter in place in all backends; AUTH_MODE=local behaviour unchanged
- Nginx config uses envsubst; no hardcoded DNS names
- Integration tests use real services; only LLM is mocked
- No reorganisation of files inside services beyond what is listed above

## Out of scope for this spec

- Keycloak integration (auth adapter stub only)
- Adding Spanish locale to user-input-manager
- context-distiller implementation (separate spec exists)
- agent-tools implementation (separate spec exists)
- SSL certificate provisioning (nginx is certbot-ready but not configured)
- Any new features in existing services beyond the items listed above
```

---

## Setup before running

```bash
# 1. Create the monorepo root
mkdir dark-factory && cd dark-factory

# 2. Move existing service directories in
mv ../user-input-manager services/user-input-manager
mv ../ticket-manager services/ticket-manager
mv ../orchestrator services/orchestrator
# (context-distiller and agent-tools will be created later)

# 3. Create infra and integration-tests directories
mkdir -p infra/nginx/snippets infra/postgres/init integration-tests/tests

# 4. Initialize spec-kit
specify init dark-factory-monorepo --ai claude

# 5. Place context files
cp /path/to/monorepo-constitution.md .specify/memory/constitution.md

# Create service-map.md (summary of current state)
cat > .specify/memory/service-map.md << 'EOF'
# Dark Factory — Current Service State

## user-input-manager (Prompt Studio)
- Location: services/user-input-manager/
- Backend: FastAPI, Python 3.12, PostgreSQL
- Frontend: React 18, Vite, TypeScript, Context API (→ migrate to Zustand)
- Auth: JWT, tokens in localStorage (→ migrate to memory-only)
- i18n: en, ru

## ticket-manager
- Location: services/ticket-manager/
- Backend: FastAPI, Python 3.11 (→ upgrade to 3.12), PostgreSQL 15 (→ 16)
- Frontend: React 18, Vite, TypeScript, Zustand (memory tokens ✓)
- Auth: JWT, access tokens in memory only ✓
- i18n: en, ru, es
- State: Zustand ✓ (reference implementation for other frontends)

## orchestrator
- Location: services/orchestrator/
- Backend: FastAPI, Python 3.12, PostgreSQL + MongoDB
- Frontend: none (UI lives in user-input-manager as Work Queue section)
- Auth: validates Prompt Studio JWT

## context-distiller
- Location: services/context-distiller/ (to be built)
- Backend: FastAPI, Python 3.12, PostgreSQL + MongoDB
- Frontend: none

## agent-tools
- Location: services/agent-tools/ (to be built)
- Backend: MCP server, Python 3.12
- Frontend: none
EOF

# 6. Run specify
/speckit.specify  # paste the prompt above
```
